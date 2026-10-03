import gzip
import hashlib
import io
import json
from pathlib import Path
import stat
import struct
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import warnings
import zipfile
import zlib

from shipglass import core


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)

    def zip(self, name, members, date=(2025, 1, 1, 0, 0, 0)):
        path = self.root / name
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for member, content in members:
                info = zipfile.ZipInfo(member, date_time=date)
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, content)
        return path

    def tar(self, name, members, mtime=0):
        path = self.root / name
        with tarfile.open(path, "w:gz" if name.endswith((".gz", ".tgz")) else "w") as archive:
            for member, content in members:
                info = tarfile.TarInfo(member)
                info.mtime = mtime
                if member.endswith("/"):
                    info.type = tarfile.DIRTYPE
                else:
                    info.size = len(content)
                archive.addfile(info, io.BytesIO(content))
        return path

    def test_supported_formats_hash_payload_and_preserve_paths(self):
        members = [("package/", b""), ("package/main.py", b"print('hello')\n")]
        for extension in ("zip", "whl", "tar", "tgz", "tar.gz"):
            with self.subTest(extension=extension):
                path = self.zip("build." + extension, members) if extension in ("zip", "whl") else self.tar("build." + extension, members)
                result = core.scan(path)
                self.assertEqual(result["name"], path.name)
                self.assertEqual(result["archive_bytes"], path.stat().st_size)
                self.assertEqual(result["total_bytes"], len(members[1][1]))
                self.assertEqual([item["path"] for item in result["files"]], ["package/main.py"])
                self.assertEqual(result["files"][0]["sha256"], hashlib.sha256(members[1][1]).hexdigest())

    def test_compare_detects_same_size_edits_and_ignores_metadata(self):
        first = self.zip("first.zip", [("edit.txt", b"old"), ("stable.txt", b"same"), ("removed.txt", b"bye")])
        second = self.zip("second.zip", [("stable.txt", b"same"), ("edit.txt", b"new"), ("added.txt", b"hi")], date=(2026, 2, 2, 0, 0, 0))
        result = core.compare(core.scan(first), core.scan(second))
        self.assertEqual({row["path"]: row["status"] for row in result["files"]}, {"edit.txt": "changed", "stable.txt": "unchanged", "removed.txt": "removed", "added.txt": "added"})
        self.assertEqual(result["summary"], {"before_bytes": 10, "after_bytes": 9, "delta_bytes": -1, "added": 1, "removed": 1, "changed": 1, "unchanged": 1, "warning_count": 0})
        self.assertEqual(result["files"][0]["before_size"], None)
        self.assertEqual(result["files"][2]["after_size"], None)

    def test_tar_metadata_does_not_change_members(self):
        before = core.scan(self.tar("first.tar", [("./same.txt", b"content")], mtime=1))
        after = core.scan(self.tar("second.tar", [("./same.txt", b"content")], mtime=100))
        self.assertEqual(core.compare(before, after)["files"][0]["status"], "unchanged")
        self.assertEqual(before["files"][0]["path"], "./same.txt")

    def test_unsafe_paths_rejected_in_both_formats(self):
        names = ("../escape", "package/../../escape", "/absolute", "C:/drive", "C:drive", "a\\b", "a//b", "a\nname")
        for name in names:
            for kind in ("zip", "tar"):
                with self.subTest(name=name, kind=kind):
                    stored_name = name.replace("\\", "_") if kind == "zip" else name
                    path = getattr(self, kind)("bad." + kind, [(stored_name, b"x")])
                    if stored_name != name:
                        # ZipInfo normalizes native separators while writing on Windows.
                        # Patch both serialized headers so the fixture stays hostile.
                        raw = path.read_bytes()
                        self.assertEqual(raw.count(stored_name.encode()), 2)
                        raw = raw.replace(stored_name.encode(), name.encode())
                        self.assertEqual(raw.count(name.encode()), 2)
                        path.write_bytes(raw)
                        with zipfile.ZipFile(path) as archive:
                            self.assertEqual(archive.infolist()[0].orig_filename, name)
                    with self.assertRaisesRegex(ValueError, "unsafe|control"):
                        core.scan(path)

    def test_zip_nul_name_is_rejected_before_truncation(self):
        path = self.zip("nul.zip", [("badXname", b"data")])
        path.write_bytes(path.read_bytes().replace(b"badXname", b"bad\x00name"))
        with self.assertRaisesRegex(ValueError, "control"):
            core.scan(path)

    def test_duplicate_and_normalized_duplicate_paths_rejected(self):
        for names in (("same", "same"), ("same", "./same"), ("a/same", "a/./same")):
            for kind in ("zip", "tar"):
                with self.subTest(names=names, kind=kind), warnings.catch_warnings():
                    warnings.simplefilter("ignore", UserWarning)
                    path = getattr(self, kind)("duplicates." + kind, [(name, b"x") for name in names])
                    with self.assertRaisesRegex(ValueError, "duplicate"):
                        core.scan(path)

    def test_explicit_stripping_and_collisions(self):
        path = self.tar("package.tgz", [("package/", b""), ("package/a.txt", b"x")])
        self.assertEqual(core.scan(path, strip_components=1)["files"][0]["path"], "a.txt")
        path = self.zip("collision.zip", [("one/a", b"a"), ("two/a", b"b")])
        with self.assertRaisesRegex(ValueError, "duplicate"):
            core.scan(path, strip_components=1)
        for bad in (-1, 1.5, True):
            with self.assertRaises(ValueError):
                core.scan(path, strip_components=bad)
        path = self.tar("hidden.tar", [("../escape", b"a")])
        with self.assertRaisesRegex(ValueError, "unsafe"):
            core.scan(path, strip_components=3)

    def test_member_and_expanded_payload_limits(self):
        for kind in ("zip", "tar"):
            with self.subTest(kind=kind):
                path = getattr(self, kind)("large." + kind, [("dir/", b""), ("dir/a", b"x" * 2000)])
                with patch.object(core, "MAX_ENTRIES", 1), self.assertRaisesRegex(ValueError, "member limit"):
                    core.scan(path)
                with patch.object(core, "MAX_TOTAL_BYTES", 1000), self.assertRaisesRegex(ValueError, "payload limit"):
                    core.scan(path)
        with patch.object(core, "MAX_ARCHIVE_BYTES", 1), self.assertRaisesRegex(ValueError, "input limit"):
            core.scan(path)

    def test_tar_expanded_metadata_stream_limit(self):
        path = self.tar("large.tgz", [("small", b"data")])
        with patch.object(core, "MAX_TAR_STREAM_BYTES", 100), self.assertRaisesRegex(ValueError, "stream limit"):
            core.scan(path)

    def test_gzip_tar_rejects_invalid_or_missing_trailer(self):
        for extension in ("tgz", "tar.gz"):
            path = self.tar("trailer." + extension, [("file.txt", b"content")])
            original = path.read_bytes()
            self.assertEqual(core.scan(path)["files"][0]["sha256"], hashlib.sha256(b"content").hexdigest())
            for corruption in ("crc", "size", "missing"):
                with self.subTest(extension=extension, corruption=corruption):
                    data = bytearray(original)
                    if corruption == "missing":
                        del data[-8:]
                    else:
                        data[-8 if corruption == "crc" else -4] ^= 1
                    path.write_bytes(data)
                    with self.assertRaisesRegex(ValueError, "Cannot read tar.gz archive"):
                        core.scan(path)

    def test_tar_stream_limit_includes_padding_after_end_marker(self):
        payload = self.tar("base.tar", [("file.txt", b"content")]).read_bytes() + b"\0" * 65536
        for extension in ("tar", "tgz", "tar.gz"):
            with self.subTest(extension=extension):
                path = self.root / ("padded." + extension)
                path.write_bytes(payload if extension == "tar" else gzip.compress(payload))
                with patch.object(core, "MAX_TAR_STREAM_BYTES", len(payload)):
                    result = core.scan(path)
                self.assertEqual(result["total_bytes"], 7)
                self.assertEqual([item["path"] for item in result["files"]], ["file.txt"])
                with patch.object(core, "MAX_TAR_STREAM_BYTES", len(payload) - 1):
                    with self.assertRaisesRegex(ValueError, "stream limit"):
                        core.scan(path)

    def test_tar_links_are_not_dereferenced_or_disclosed(self):
        path = self.root / "links.tar"
        target = "../../private-do-not-print"
        with tarfile.open(path, "w") as archive:
            for kind, name in ((tarfile.SYMTYPE, "symbolic"), (tarfile.LNKTYPE, "hard")):
                info = tarfile.TarInfo(name)
                info.type = kind
                info.linkname = target
                archive.addfile(info)
        result = core.scan(path)
        self.assertEqual(result["total_bytes"], 0)
        self.assertEqual({item["kind"] for item in result["files"]}, {"symlink", "hardlink"})
        self.assertNotIn(target, json.dumps(result))
        for item in result["files"]:
            self.assertEqual(item["sha256"], hashlib.sha256(target.encode()).hexdigest())
            self.assertEqual([warning["code"] for warning in item["warnings"]], ["link", "link-path"])
        self.assertEqual(list(self.root.iterdir()), [path])

    def test_zip_symlink_target_is_hashed(self):
        path = self.root / "links.zip"
        with zipfile.ZipFile(path, "w") as archive:
            info = zipfile.ZipInfo("link")
            info.create_system = 3
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(info, b"missing-target")
        item = core.scan(path)["files"][0]
        self.assertEqual(item["kind"], "symlink")
        self.assertEqual(item["size"], 14)
        self.assertEqual(item["sha256"], hashlib.sha256(b"missing-target").hexdigest())

    def test_understated_zip_size_does_not_hide_expanded_data(self):
        for method in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
            with self.subTest(method=method):
                path = self.root / "understated.zip"
                with zipfile.ZipFile(path, "w", compression=method) as archive:
                    archive.writestr("large.txt", b"A" * 100_000)
                data = bytearray(path.read_bytes())
                local = data.index(b"PK\x03\x04")
                central = data.index(b"PK\x01\x02")
                for offset in (local + 14, central + 16):
                    struct.pack_into("<I", data, offset, zlib.crc32(b"A"))
                for offset in (local + 22, central + 24):
                    struct.pack_into("<I", data, offset, 1)
                path.write_bytes(data)
                with self.assertRaisesRegex(ValueError, "declared size|inconsistent payload sizes"):
                    core.scan(path)

    def test_zip_rejects_unbounded_compression_algorithms(self):
        for method in (zipfile.ZIP_BZIP2, zipfile.ZIP_LZMA):
            with self.subTest(method=method):
                path = self.root / "unsupported.zip"
                with zipfile.ZipFile(path, "w", compression=method) as archive:
                    archive.writestr("file.txt", b"A" * 100_000)
                with self.assertRaisesRegex(ValueError, "only STORE and DEFLATE"):
                    core.scan(path)

    def test_zip_hashes_large_and_empty_store_and_deflate_members(self):
        content = bytes(range(256)) * 1000
        for method in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
            with self.subTest(method=method):
                path = self.root / "bounded.zip"
                with zipfile.ZipFile(path, "w", compression=method) as archive:
                    archive.writestr("large", content)
                    archive.writestr("empty", b"")
                files = core.scan(path)["files"]
                self.assertEqual(files[0]["sha256"], hashlib.sha256(b"").hexdigest())
                self.assertEqual(files[1]["sha256"], hashlib.sha256(content).hexdigest())
                self.assertEqual(files[1]["size"], len(content))

    def test_zip_rejects_truncated_deflate_and_wrong_crc(self):
        for corruption in ("truncated", "crc"):
            with self.subTest(corruption=corruption):
                path = self.zip("corrupt.zip", [("file", b"abcdef" * 1000)])
                data = bytearray(path.read_bytes())
                local = data.index(b"PK\x03\x04")
                central = data.index(b"PK\x01\x02")
                if corruption == "truncated":
                    for offset in (local + 18, central + 20):
                        size = struct.unpack_from("<I", data, offset)[0]
                        struct.pack_into("<I", data, offset, size - 1)
                else:
                    for offset in (local + 14, central + 16):
                        struct.pack_into("<I", data, offset, 0)
                path.write_bytes(data)
                with self.assertRaisesRegex(ValueError, "truncated|CRC"):
                    core.scan(path)

    def test_zip_rejects_trailing_compressed_bytes(self):
        path = self.zip("trailing.zip", [("file", b"content")])
        data = bytearray(path.read_bytes())
        central = data.index(b"PK\x01\x02")
        data[central:central] = b"X"
        central += 1
        end = data.index(b"PK\x05\x06")
        for offset in (18, central + 20):
            size = struct.unpack_from("<I", data, offset)[0]
            struct.pack_into("<I", data, offset, size + 1)
        struct.pack_into("<I", data, end + 16, central)
        path.write_bytes(data)
        with self.assertRaisesRegex(ValueError, "trailing compressed"):
            core.scan(path)

    def test_zip_directory_count_checked_before_member_allocation(self):
        path = self.zip("many.zip", [("one", b""), ("two", b""), ("three", b"")])
        data = bytearray(path.read_bytes())
        end = data.index(b"PK\x05\x06")
        # An attacker can understate EOCD counts, so count the actual records.
        struct.pack_into("<HH", data, end + 8, 1, 1)
        path.write_bytes(data)
        with patch.object(core, "MAX_ENTRIES", 2), patch.object(core.zipfile, "ZipFile") as constructor:
            with self.assertRaisesRegex(ValueError, "member limit"):
                core.scan(path)
            constructor.assert_not_called()

    def test_zip_directory_bytes_checked_before_member_allocation(self):
        path = self.zip("long-name.zip", [("long-name" * 20, b"data")])
        with patch.object(core, "MAX_ZIP_DIRECTORY_BYTES", 100), patch.object(core.zipfile, "ZipFile") as constructor:
            with self.assertRaisesRegex(ValueError, "ZIP directory exceeds"):
                core.scan(path)
            constructor.assert_not_called()

    def test_zip64_directory_rejected_but_local_headers_supported(self):
        path = self.root / "local-zip64.zip"
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            with archive.open("file", "w", force_zip64=True) as member:
                member.write(b"content")
        self.assertEqual(core.scan(path)["files"][0]["size"], 7)
        data = bytearray(path.read_bytes())
        end = data.index(b"PK\x05\x06")
        struct.pack_into("<HH", data, end + 8, 65535, 65535)
        path.write_bytes(data)
        with self.assertRaisesRegex(ValueError, "ZIP64 central directories"):
            core.scan(path)

    def test_special_tar_files_rejected(self):
        path = self.root / "device.tar"
        with tarfile.open(path, "w") as archive:
            info = tarfile.TarInfo("device")
            info.type = tarfile.CHRTYPE
            archive.addfile(info)
        with self.assertRaisesRegex(ValueError, "special"):
            core.scan(path)

    def test_filename_warnings_are_heuristics_not_content_scanning(self):
        names = [".env", ".env.production", ".env.example", ".env.sample", ".env.template", "id_rsa", "assets/main.js.map", "pkg/__pycache__/a.pyc", ".git/config", "tests/check.py", "ordinary.txt"]
        result = core.scan(self.zip("warnings.zip", [(name, b"same") for name in names]))
        items = {item["path"]: item for item in result["files"]}
        for name in [".env", ".env.production", "id_rsa", "assets/main.js.map", "pkg/__pycache__/a.pyc", ".git/config", "tests/check.py"]:
            self.assertTrue(items[name]["warnings"], name)
        for name in [".env.example", ".env.sample", ".env.template", "ordinary.txt"]:
            self.assertEqual(items[name]["warnings"], [], name)
        report = core.compare(result, result)
        self.assertEqual(report["summary"]["warning_count"], 7)

    def test_html_looking_filenames_are_preserved_as_data(self):
        names = ['<img src=x onerror="alert(1)">.txt', "script</script>.js", "quote'&.txt"]
        result = core.scan(self.zip("names.zip", [(name, b"safe") for name in names]))
        self.assertEqual(sorted(names), [item["path"] for item in result["files"]])

    def test_invalid_inputs_raise_value_error(self):
        for path in (self.root, self.root / "missing.zip"):
            with self.assertRaisesRegex(ValueError, "archive file"):
                core.scan(path)
        for name in ("broken.zip", "broken.tar", "broken.tgz", "unknown.bin"):
            path = self.root / name
            path.write_bytes(b"not an archive")
            with self.assertRaises(ValueError):
                core.scan(path)


if __name__ == "__main__":
    unittest.main()
