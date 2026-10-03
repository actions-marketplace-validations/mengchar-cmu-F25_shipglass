"""Read release archives without extracting or executing their contents.

Limits apply independently to each archive: 50,000 members (including
directories), 1 GiB of file payload, and 1 GiB of compressed input. Tar parsing
also limits the expanded stream, including headers, to 1 GiB + 100 MiB.
ZIP directories are capped at 64 MiB before zipfile constructs member objects;
ZIP64 directory records are unsupported (ZIP64 local file headers are accepted).
Links are represented by their target hash, never followed. Tar link targets
are metadata, so their payload size is zero; ZIP links store target bytes.
"""

from __future__ import annotations

import gzip
import hashlib
import re
import stat
import struct
import tarfile
import zipfile
import zlib
from pathlib import Path
from typing import BinaryIO

MAX_ENTRIES = 50_000
MAX_TOTAL_BYTES = 1024 * 1024 * 1024
MAX_ARCHIVE_BYTES = 1024 * 1024 * 1024
MAX_TAR_STREAM_BYTES = MAX_TOTAL_BYTES + 100 * 1024 * 1024
MAX_ZIP_DIRECTORY_BYTES = 64 * 1024 * 1024
MAX_LINK_TARGET_BYTES = 4096
CHUNK_BYTES = 64 * 1024


def _warning(code: str, message: str) -> dict:
    return {"code": code, "message": message}


def _path(name: str, strip_components: int, *, directory: bool = False) -> tuple[str, str] | None:
    if not name or "\\" in name or name.startswith("/") or re.match(r"^[A-Za-z]:", name):
        raise ValueError("Archive contains an unsafe member path")
    if any(ord(char) < 32 or ord(char) == 127 for char in name):
        raise ValueError("Archive contains a control character in a member path")
    parts = name.rstrip("/").split("/")
    if ".." in parts or "" in parts:
        raise ValueError("Archive contains an unsafe member path")
    if len(parts) <= strip_components:
        return None
    parts = parts[strip_components:]
    native = "/".join(parts)
    canonical = "/".join(part for part in parts if part != ".")
    if not canonical:
        if directory:
            return None
        raise ValueError("Archive contains an empty member path")
    return native, canonical


def _filename_warnings(path: str) -> list[dict]:
    parts = path.lower().split("/")
    name = parts[-1]
    warnings = []
    if (name == ".env" or name.startswith(".env.")) and not name.endswith((".example", ".sample", ".template")):
        warnings.append(_warning("env-file", "Environment file name; review whether it belongs in a release."))
    if name in {"id_rsa", "id_dsa", "id_ecdsa", "id_ed25519"} or name.endswith((".key", ".p12", ".pfx")) or "private_key" in name or "private-key" in name:
        warnings.append(_warning("key-file", "Private-key-like file name; inspect it before publishing."))
    if name.endswith(".map"):
        warnings.append(_warning("source-map", "Source map name; review whether source maps are intended."))
    if any(part in {".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".cache"} for part in parts) or name.endswith((".pyc", ".pyo")):
        warnings.append(_warning("cache-or-vcs", "Cache or version-control path; review whether it belongs in a release."))
    if any(part in {"test", "tests", "__tests__"} for part in parts[:-1]) or name.startswith("test_") or name.endswith(("_test.py", ".test.js", ".test.ts", ".spec.js", ".spec.ts")):
        warnings.append(_warning("test-file", "Test-like path; review whether tests are intended in this release."))
    return warnings


def _link_warnings(target: bytes) -> list[dict]:
    warnings = [_warning("link", "Link target was hashed without being followed.")]
    decoded = target.decode("utf-8", errors="replace")
    if decoded.startswith(("/", "\\")) or "\\" in decoded or ".." in decoded.split("/") or re.match(r"^[A-Za-z]:", decoded):
        warnings.append(_warning("link-path", "Link target has an absolute or traversal-like path."))
    return warnings


class _Budget:
    def __init__(self) -> None:
        self.entries = 0
        self.total = 0
        self.paths: set[str] = set()
        self.original_paths: set[str] = set()

    def member(self, name: str, size: int, strip_components: int, directory: bool) -> tuple[str, str] | None:
        self.entries += 1
        if self.entries > MAX_ENTRIES:
            raise ValueError(f"Archive exceeds the {MAX_ENTRIES:,}-member limit")
        if size < 0 or size > MAX_TOTAL_BYTES - self.total:
            raise ValueError(f"Archive exceeds the {MAX_TOTAL_BYTES:,}-byte expanded payload limit")
        self.total += size
        original = _path(name, 0, directory=directory)
        if original is not None:
            if original[1] in self.original_paths:
                raise ValueError("Archive contains duplicate member paths")
            self.original_paths.add(original[1])
        path = _path(name, strip_components, directory=directory)
        if path is not None:
            if path[1] in self.paths:
                raise ValueError("Archive contains duplicate member paths")
            self.paths.add(path[1])
        return path


def _digest(stream: BinaryIO, expected_size: int, *, link: bool = False) -> tuple[str, bytes]:
    if link and expected_size > MAX_LINK_TARGET_BYTES:
        raise ValueError("Archive link target exceeds the 4,096-byte limit")
    digest = hashlib.sha256()
    actual_size = 0
    target = bytearray()
    while True:
        chunk = stream.read(min(CHUNK_BYTES, expected_size - actual_size + 1))
        if not chunk:
            break
        actual_size += len(chunk)
        if actual_size > expected_size:
            raise ValueError("Archive member expands beyond its declared size")
        digest.update(chunk)
        if link:
            target.extend(chunk)
    if actual_size != expected_size:
        raise ValueError("Archive member is truncated")
    return digest.hexdigest(), bytes(target)


class _LimitedReader:
    """Cap tar's entire expanded input, including metadata and skipped members."""

    def __init__(self, stream: BinaryIO) -> None:
        self.stream = stream
        self.total = 0

    def read(self, size: int = -1) -> bytes:
        remaining = MAX_TAR_STREAM_BYTES - self.total
        request = remaining + 1 if size < 0 else min(size, remaining + 1)
        data = self.stream.read(request)
        self.total += len(data)
        if self.total > MAX_TAR_STREAM_BYTES:
            raise ValueError("Archive exceeds the expanded tar stream limit")
        return data


def _record(path: str, size: int, sha256: str, kind: str, target: bytes = b"") -> dict:
    warnings = _filename_warnings(path)
    if kind != "file":
        warnings.extend(_link_warnings(target))
    return {"path": path, "size": size, "sha256": sha256, "kind": kind, "warnings": warnings}


def _zip_digest(archive: zipfile.ZipFile, source: BinaryIO, info: zipfile.ZipInfo, *, link: bool) -> tuple[str, bytes]:
    """Read ZIP payload directly: ZipExtFile can hide understated file sizes."""
    if info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
        raise ValueError("Unsupported ZIP compression; only STORE and DEFLATE are supported")
    if link and info.file_size > MAX_LINK_TARGET_BYTES:
        raise ValueError("Archive link target exceeds the 4,096-byte limit")
    # The public API validates local names, overlap, flags, and encryption.
    # Do not read ZipExtFile: it truncates expanded bytes to the declared size.
    with archive.open(info):
        pass
    source.seek(info.header_offset)
    header = source.read(30)
    if len(header) != 30:
        raise ValueError("ZIP local header is truncated")
    signature, _, flags, method, _, _, _, _, _, name_size, extra_size = struct.unpack("<4s5H3I2H", header)
    if signature != b"PK\x03\x04" or method != info.compress_type or flags != info.flag_bits:
        raise ValueError("ZIP local and central headers disagree")
    source.seek(name_size + extra_size, 1)
    if method == zipfile.ZIP_STORED and info.compress_size != info.file_size:
        raise ValueError("Stored ZIP member has inconsistent payload sizes")
    decompressor = zlib.decompressobj(-15) if method == zipfile.ZIP_DEFLATED else None
    digest = hashlib.sha256()
    target = bytearray()
    crc = 0
    actual_size = 0
    remaining = info.compress_size
    pending = b""
    while remaining or pending:
        if not pending:
            pending = source.read(min(CHUNK_BYTES, remaining))
            if not pending:
                raise ValueError("ZIP member compressed data is truncated")
            remaining -= len(pending)
        if decompressor is not None:
            chunk = decompressor.decompress(pending, min(CHUNK_BYTES, info.file_size - actual_size + 1))
            pending = decompressor.unconsumed_tail
        else:
            chunk, pending = pending, b""
        actual_size += len(chunk)
        if actual_size > info.file_size:
            raise ValueError("ZIP member expands beyond its declared size")
        digest.update(chunk)
        crc = zlib.crc32(chunk, crc)
        if link:
            target.extend(chunk)
        if decompressor is not None and decompressor.eof:
            if decompressor.unused_data or pending or remaining:
                raise ValueError("ZIP member has trailing compressed data")
    if decompressor is not None and not decompressor.eof:
        raise ValueError("ZIP member compressed data is truncated")
    if actual_size != info.file_size:
        raise ValueError("ZIP member does not match its declared size")
    if crc != info.CRC:
        raise ValueError("ZIP member CRC check failed")
    return digest.hexdigest(), bytes(target)


def _check_zip_directory(source: BinaryIO) -> None:
    """Bound central-directory allocations before constructing ZipFile."""
    source.seek(0, 2)
    archive_size = source.tell()
    tail_size = min(archive_size, 65535 + 22)
    source.seek(archive_size - tail_size)
    tail = source.read(tail_size)
    end = tail.rfind(b"PK\x05\x06")
    if end < 0 or len(tail) - end < 22:
        raise ValueError("ZIP end-of-directory record is missing or truncated")
    _, disk, directory_disk, disk_count, count, directory_size, directory_offset, comment_size = struct.unpack("<4s4H2IH", tail[end:end + 22])
    if end + 22 + comment_size != len(tail):
        raise ValueError("ZIP end-of-directory record has an invalid comment length")
    if disk or directory_disk or disk_count != count:
        raise ValueError("Multi-disk ZIP archives are unsupported")
    end_offset = archive_size - tail_size + end
    source.seek(max(0, end_offset - 20))
    if source.read(4) == b"PK\x06\x07" or count == 65535 or directory_size == 0xFFFFFFFF or directory_offset == 0xFFFFFFFF:
        raise ValueError("ZIP64 central directories are unsupported")
    if count > MAX_ENTRIES:
        raise ValueError(f"Archive exceeds the {MAX_ENTRIES:,}-member limit")
    if directory_size > MAX_ZIP_DIRECTORY_BYTES:
        raise ValueError(f"ZIP directory exceeds the {MAX_ZIP_DIRECTORY_BYTES:,}-byte limit")
    # ZIPs may have a prepended executable; zipfile applies the same offset shift.
    directory_start = end_offset - directory_size
    if directory_start < 0 or directory_offset > directory_start:
        raise ValueError("ZIP directory has an invalid offset")
    source.seek(directory_start)
    remaining = directory_size
    actual_count = 0
    while remaining:
        if remaining < 46:
            raise ValueError("ZIP directory entry is truncated")
        header = source.read(46)
        if len(header) != 46 or header[:4] != b"PK\x01\x02":
            raise ValueError("ZIP directory entry has an invalid header")
        name_size, extra_size, entry_comment_size = struct.unpack_from("<3H", header, 28)
        entry_size = 46 + name_size + extra_size + entry_comment_size
        if entry_size > remaining:
            raise ValueError("ZIP directory entry is truncated")
        actual_count += 1
        if actual_count > MAX_ENTRIES:
            raise ValueError(f"Archive exceeds the {MAX_ENTRIES:,}-member limit")
        source.seek(entry_size - 46, 1)
        remaining -= entry_size
    if actual_count != count:
        raise ValueError("ZIP directory member count is inconsistent")


def _scan_zip(path: Path, strip_components: int) -> list[dict]:
    files = []
    budget = _Budget()
    with path.open("rb") as source:
        _check_zip_directory(source)
    with zipfile.ZipFile(path) as archive, path.open("rb") as source:
        for info in archive.infolist():
            # orig_filename retains NULs that ZipInfo.filename silently truncates.
            member_path = budget.member(info.orig_filename, info.file_size, strip_components, info.is_dir())
            mode = info.external_attr >> 16 if info.create_system == 3 else 0
            if stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR, stat.S_IFLNK):
                raise ValueError("Archive contains an unsupported special file")
            kind = "symlink" if stat.S_ISLNK(mode) else "file"
            sha256, target = _zip_digest(archive, source, info, link=kind == "symlink")
            if member_path is None or info.is_dir():
                continue
            files.append(_record(member_path[0], info.file_size, sha256, kind, target))
    return files


def _scan_tar(path: Path, strip_components: int, compressed: bool) -> list[dict]:
    files = []
    budget = _Budget()
    opener = gzip.open if compressed else open
    with opener(path, "rb") as source:
        with tarfile.open(fileobj=_LimitedReader(source), mode="r|") as archive:
            for info in archive:
                member_path = budget.member(info.name, info.size, strip_components, info.isdir())
                if not (info.isfile() or info.isdir() or info.issym() or info.islnk()):
                    raise ValueError("Archive contains an unsupported special file")
                if member_path is None or info.isdir():
                    continue
                if info.issym() or info.islnk():
                    target = info.linkname.encode("utf-8", errors="surrogateescape")
                    if len(target) > MAX_LINK_TARGET_BYTES:
                        raise ValueError("Archive link target exceeds the 4,096-byte limit")
                    files.append(_record(member_path[0], 0, hashlib.sha256(target).hexdigest(), "symlink" if info.issym() else "hardlink", target))
                else:
                    stream = archive.extractfile(info)
                    if stream is None:
                        raise ValueError("Archive member cannot be read")
                    with stream:
                        sha256, _ = _digest(stream, info.size)
                    files.append(_record(member_path[0], info.size, sha256, "file"))
    return files


def scan(path: Path | str, strip_components: int = 0) -> dict:
    """Scan ZIP/wheel, tar, or gzip tar files; reject ambiguous/unsafe members.

    File paths remain archive-native. Explicit stripping drops leading path
    components, omits members with too few components, and checks for collisions.
    No archive contents or link targets are included in the returned report.
    """
    if not isinstance(strip_components, int) or isinstance(strip_components, bool) or strip_components < 0:
        raise ValueError("strip_components must be a non-negative integer")
    path = Path(path)
    if not path.is_file():
        raise ValueError("Input must be an archive file")
    archive_bytes = path.stat().st_size
    if archive_bytes > MAX_ARCHIVE_BYTES:
        raise ValueError(f"Archive exceeds the {MAX_ARCHIVE_BYTES:,}-byte input limit")
    name = path.name.lower()
    if name.endswith((".zip", ".whl")):
        archive_format = "zip"
    elif name.endswith((".tar.gz", ".tgz")):
        archive_format = "tar.gz"
    elif name.endswith(".tar"):
        archive_format = "tar"
    else:
        raise ValueError("Supported archive extensions: .zip, .whl, .tar, .tar.gz, .tgz")
    try:
        files = _scan_zip(path, strip_components) if archive_format == "zip" else _scan_tar(path, strip_components, archive_format == "tar.gz")
    except (OSError, EOFError, RuntimeError, NotImplementedError, zipfile.BadZipFile, tarfile.TarError, zlib.error) as error:
        raise ValueError(f"Cannot read {archive_format} archive: {type(error).__name__}") from error
    files.sort(key=lambda item: item["path"])
    return {"name": path.name, "archive_bytes": archive_bytes, "total_bytes": sum(item["size"] for item in files), "files": files, "warnings": [], "format": archive_format}


def compare(before: dict, after: dict) -> dict:
    """Compare member paths, payload hashes, and kinds; ignore archive metadata."""
    old = {item["path"]: item for item in before["files"]}
    new = {item["path"]: item for item in after["files"]}
    files = []
    counts = dict.fromkeys(("added", "removed", "changed", "unchanged"), 0)
    for path in sorted(old.keys() | new.keys()):
        left, right = old.get(path), new.get(path)
        if left is None:
            status = "added"
        elif right is None:
            status = "removed"
        elif (left["sha256"], left["kind"], left["size"]) != (right["sha256"], right["kind"], right["size"]):
            status = "changed"
        else:
            status = "unchanged"
        counts[status] += 1
        before_size = left["size"] if left is not None else None
        after_size = right["size"] if right is not None else None
        files.append({"path": path, "status": status, "before_size": before_size, "after_size": after_size, "delta": (after_size or 0) - (before_size or 0), "warnings": list((right if right is not None else left)["warnings"])})
    warnings = list(before["warnings"]) + list(after["warnings"])
    summary = {"before_bytes": before["total_bytes"], "after_bytes": after["total_bytes"], "delta_bytes": after["total_bytes"] - before["total_bytes"], **counts, "warning_count": len(warnings) + sum(len(item["warnings"]) for item in files)}
    return {"schema_version": 1, "before": before, "after": after, "summary": summary, "files": files, "warnings": warnings}
