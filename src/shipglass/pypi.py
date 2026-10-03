"""Download exact public PyPI wheels without installing or executing them."""

from __future__ import annotations

import hashlib
import http.client
import json
import re
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from . import core

MAX_METADATA_BYTES = 1024 * 1024
NETWORK_TIMEOUT = 30
_NAME = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?")
_VERSION = re.compile(r"[0-9][A-Za-z0-9.!+_-]*")
_MANUAL = "Download two explicitly selected wheels and use shipglass compare instead."


def _normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _url(url: str, host: str) -> None:
    if not isinstance(url, str) or any(char.isspace() or ord(char) < 32 or ord(char) == 127 or char == "\\" for char in url):
        raise ValueError("Invalid PyPI download URL")
    parts = urllib.parse.urlsplit(url)
    if (parts.scheme != "https" or parts.hostname != host
            or parts.port not in (None, 443) or parts.username is not None
            or parts.password is not None or parts.fragment):
        raise ValueError(f"PyPI downloads require HTTPS {host} URLs")


class _HostRedirect(urllib.request.HTTPRedirectHandler):
    def __init__(self, host: str):
        super().__init__()
        self.host = host

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _url(newurl, self.host)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _chunks(response, limit: int, label: str):
    declared = response.headers.get("Content-Length")
    if declared is not None:
        if not re.fullmatch(r"[0-9]+", declared):
            raise ValueError("Invalid PyPI response length")
        declared = int(declared)
        if declared > limit:
            raise ValueError(f"PyPI {label} exceeds the {limit:,}-byte limit")
    total = 0
    while True:
        chunk = response.read(min(core.CHUNK_BYTES, limit - total + 1))
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise ValueError(f"PyPI {label} exceeds the {limit:,}-byte limit")
        yield chunk
    if declared is not None and total != declared:
        raise ValueError(f"PyPI {label} has an inconsistent response length")


def _universal(filename: str, package: str, version: str) -> bool:
    if not isinstance(filename, str) or not filename.endswith(".whl"):
        return False
    parts = filename[:-4].split("-")
    if len(parts) not in (5, 6) or _normalize(parts[0]) != package or parts[1] != version:
        return False
    if len(parts) == 6 and not re.fullmatch(r"[0-9][\w.]*", parts[2]):
        return False
    python, abi, platform = parts[-3:]
    return (re.fullmatch(r"py[0-9]+(?:\.py[0-9]+)*", python) is not None
            and "py3" in python.split(".") and abi == "none" and platform == "any")


def _wheel(metadata: dict, package: str, version: str) -> dict:
    if not isinstance(metadata, dict) or not isinstance(metadata.get("info"), dict) or not isinstance(metadata.get("urls"), list):
        raise ValueError("Invalid PyPI release metadata")
    info = metadata["info"]
    if (not isinstance(info.get("name"), str) or _normalize(info["name"]) != package
            or info.get("version") != version):
        raise ValueError("PyPI metadata does not match the requested package and exact published version")
    candidates, yanked = [], False
    for entry in metadata["urls"]:
        if not isinstance(entry, dict):
            raise ValueError("Invalid PyPI file metadata")
        if entry.get("packagetype") != "bdist_wheel" or not _universal(entry.get("filename"), package, version):
            continue
        if not isinstance(entry.get("yanked"), bool):
            raise ValueError("Invalid PyPI yanked status")
        if entry["yanked"]:
            yanked = True
        else:
            candidates.append(entry)
    if not candidates:
        reason = "Only yanked universal Python 3 wheels are available." if yanked else "No universal Python 3 wheel is available."
        raise ValueError(f"{reason} {_MANUAL}")
    if len(candidates) != 1:
        raise ValueError(f"Multiple universal Python 3 wheels are available. {_MANUAL}")
    return candidates[0]


def download(package: str, version: str, directory: Path) -> Path:
    """Fetch one unambiguous universal wheel and verify its published SHA-256."""
    if not isinstance(package, str) or len(package) > 256 or not _NAME.fullmatch(package):
        raise ValueError("Use a public PyPI project name, such as rich or typing-extensions")
    if not isinstance(version, str) or len(version) > 256 or not _VERSION.fullmatch(version):
        raise ValueError("Use an exact published PyPI version, such as 14.0.0; aliases and ranges are unsupported")
    package = _normalize(package)
    url = f"https://pypi.org/pypi/{package}/{urllib.parse.quote(version, safe='')}/json"
    path, complete = None, False
    try:
        opener = urllib.request.build_opener(_HostRedirect("pypi.org"))
        request = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "shipglass"})
        with opener.open(request, timeout=NETWORK_TIMEOUT) as response:
            _url(response.geturl(), "pypi.org")
            raw = b"".join(_chunks(response, MAX_METADATA_BYTES, "metadata"))
        try:
            metadata = json.loads(raw)
        except (ValueError, UnicodeError, RecursionError) as error:
            raise ValueError("Invalid PyPI release metadata") from error
        wheel = _wheel(metadata, package, version)
        archive_url = wheel.get("url")
        _url(archive_url, "files.pythonhosted.org")
        digests = wheel.get("digests")
        expected = digests.get("sha256") if isinstance(digests, dict) else None
        if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", expected):
            raise ValueError("PyPI metadata is missing a valid SHA-256 archive digest")
        size = wheel.get("size")
        if type(size) is not int or not 0 <= size <= core.MAX_ARCHIVE_BYTES:
            raise ValueError("PyPI archive size is invalid or exceeds the download limit")
        digest, total = hashlib.sha256(), 0
        opener = urllib.request.build_opener(_HostRedirect("files.pythonhosted.org"))
        request = urllib.request.Request(archive_url, headers={"User-Agent": "shipglass"})
        with opener.open(request, timeout=NETWORK_TIMEOUT) as response:
            _url(response.geturl(), "files.pythonhosted.org")
            with tempfile.NamedTemporaryFile(prefix=f"{package[:80]}-", suffix=".whl", dir=directory, delete=False) as target:
                path = Path(target.name)
                for chunk in _chunks(response, size, "archive"):
                    target.write(chunk)
                    digest.update(chunk)
                    total += len(chunk)
        if total != size:
            raise ValueError("PyPI archive size does not match the published metadata")
        if digest.hexdigest() != expected.lower():
            raise ValueError("PyPI archive digest does not match the published metadata")
        complete = True
        return path
    except urllib.error.HTTPError as error:
        if error.code == 404:
            raise ValueError(f"PyPI package or file was not found: {package}=={version}") from error
        raise OSError(f"PyPI download failed (HTTP {error.code})") from error
    except (urllib.error.URLError, http.client.HTTPException, TimeoutError) as error:
        raise OSError("Cannot download from public PyPI") from error
    finally:
        if path is not None and not complete:
            path.unlink(missing_ok=True)
