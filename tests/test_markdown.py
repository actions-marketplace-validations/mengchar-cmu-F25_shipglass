import unittest

from shipglass.core import compare
from shipglass.markdown import render_markdown


def snapshot(name, files=(), warnings=()):
    return {
        "name": name,
        "archive_bytes": sum(file["size"] for file in files) + 100,
        "total_bytes": sum(file["size"] for file in files),
        "files": list(files),
        "warnings": list(warnings),
        "format": "zip",
    }


def member(path, size=1, digest="a", warnings=()):
    return {"path": path, "size": size, "sha256": digest, "kind": "file", "warnings": list(warnings)}


class MarkdownTests(unittest.TestCase):
    def test_empty_comparison_reports_zero_without_fake_changes(self):
        result = render_markdown(compare(snapshot("empty-before.zip"), snapshot("empty-after.zip")))
        self.assertIn("# Shipglass release comparison", result)
        self.assertIn("**Before:** <code>empty-before.zip</code>", result)
        self.assertIn("| Expanded | 0 B | 0 B | 0 B |", result)
        self.assertIn("| 0 | 0 | 0 | 0 |", result)
        self.assertIn("No added, removed, or changed paths.", result)
        self.assertIn("0 warnings in the after archive", result)

    def test_same_size_content_edit_is_visible(self):
        result = render_markdown(compare(
            snapshot("before.zip", [member("same-size.py", 6, "old")]),
            snapshot("after.zip", [member("same-size.py", 6, "new")]),
        ))
        self.assertIn("| <code>same-size.py</code> | changed | 6 B | 6 B | 0 B |", result)
        self.assertIn("1 modified paths have no size change", result)
        self.assertNotIn("No added, removed, or changed paths.", result)

    def test_removed_and_old_snapshot_warnings_are_excluded(self):
        old_warning = {"code": "old-only", "message": "OLD_WARNING_MUST_NOT_RENDER"}
        current_warning = {"code": "env-file", "message": "Review filename"}
        before = snapshot("before.zip", [member("old.env", warnings=[old_warning])], [old_warning])
        after = snapshot("after.zip", [member("new.env", warnings=[current_warning])])
        result = render_markdown(compare(before, after))
        self.assertIn("1 warnings in the after archive", result)
        self.assertIn("Review filename", result)
        self.assertNotIn("OLD_WARNING_MUST_NOT_RENDER", result)
        self.assertIn("Filename warnings are heuristics", result)

    def test_archive_warning_is_current_and_bounded_like_filename_warning(self):
        warning = {"code": "scan-warning", "message": "Review this archive"}
        result = render_markdown(compare(snapshot("before.zip"), snapshot("after.zip", warnings=[warning])))
        self.assertIn("1 warnings in the after archive", result)
        self.assertIn("- <code>after.zip</code>: <code>Review this archive</code>", result)

    def test_arbitrary_labels_cannot_inject_html_tables_or_markdown(self):
        name = '</code><script>bad</script>|`[link](https://bad.invalid)\n\r\t\x00\u2028\u202e'
        result = render_markdown(compare(snapshot(name), snapshot(name, [member(name)])))
        self.assertNotIn("<script>", result)
        self.assertNotIn("`", result)
        self.assertNotIn("[link]", result)
        self.assertNotIn("\x00", result)
        self.assertNotIn("\u2028", result)
        self.assertNotIn("\u202e", result)
        self.assertIn("&lt;/code&gt;&lt;script&gt;bad&lt;/script&gt;&#124;&#96;", result)
        self.assertIn("&#92;n&#92;r&#92;t&#92;u0000&#92;u2028&#92;u202e", result)
        file_row = next(line for line in result.splitlines() if " | added | " in line)
        self.assertEqual(file_row.count("|"), 6)

    def test_top_changes_are_sorted_and_same_size_omissions_are_counted(self):
        before = snapshot("before.zip", [member("same.py", 1, "old")])
        after = snapshot("after.zip", [member("same.py", 1, "new")] + [member(f"file-{i:02}.bin", i) for i in range(12)])
        result = render_markdown(compare(before, after))
        self.assertIn("Showing 10 of 13", result)
        self.assertLess(result.index("<code>file-11.bin</code>"), result.index("<code>file-10.bin</code>"))
        self.assertNotIn("<code>same.py</code>", result)
        self.assertIn("1 modified paths have no size change", result)
        self.assertIn("3 additional changed paths omitted", result)

    def test_large_comparison_is_bounded_and_does_not_render_internal_data(self):
        warning = {"code": "env-file", "message": "<" * 5000}
        files = [member(f"{i:05}-" + "|<`\n" * 100, i, "HASH_MUST_NOT_RENDER", [warning]) for i in range(50_000)]
        result = render_markdown(compare(snapshot("a" * 10_000), snapshot("b" * 10_000, files)))
        self.assertLess(len(result.encode("utf-8")), 100_000)
        self.assertIn("Showing 10 of 50,000", result)
        self.assertIn("50,000 warnings in the after archive", result)
        self.assertIn("49,990 additional warnings omitted", result)
        self.assertIn("truncated", result)
        self.assertNotIn("HASH_MUST_NOT_RENDER", result)
        self.assertNotIn("a" * 201, result)


if __name__ == "__main__":
    unittest.main()
