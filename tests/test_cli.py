import contextlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from shipglass.cli import main


class CliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.report = self.root / 'report.html'
        self.data = self.root / 'report.json'
        self.markdown = self.root / 'report.md'

    def archive(self, name, files):
        path = self.root / name
        with zipfile.ZipFile(path, 'w') as archive:
            for filename, content in files.items():
                archive.writestr(filename, content)
        return path

    def run_cli(self, *args):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main([str(a) for a in args])
        return code, stdout.getvalue(), stderr.getvalue()

    def test_compare_writes_report_and_json_without_contents(self):
        first = self.archive('before.zip', {'index.js': 'old'})
        second = self.archive('after.whl', {'index.js': 'new', '.env': 'PRIVATE_TEST_VALUE_DO_NOT_EMBED'})
        code, output, _ = self.run_cli('compare', first, second, '-o', self.report, '--json', self.data)
        self.assertEqual(code, 0)
        data = json.loads(self.data.read_text())
        self.assertEqual(data['summary']['changed'], 1)
        self.assertEqual(data['summary']['added'], 1)
        self.assertIn('Report:', output)
        self.assertNotIn('PRIVATE_TEST_VALUE_DO_NOT_EMBED', self.report.read_text())
        self.assertNotIn('PRIVATE_TEST_VALUE_DO_NOT_EMBED', self.data.read_text())

    def test_growth_policy_is_strictly_greater_and_report_still_written(self):
        first = self.archive('before.zip', {'index': 'a'})
        second = self.archive('after.zip', {'index': 'abc'})
        self.assertEqual(self.run_cli('compare', first, second, '-o', self.report, '--fail-on-growth', '2')[0], 0)
        self.assertEqual(self.run_cli('compare', first, second, '-o', self.report, '--fail-on-growth', '1')[0], 1)
        self.assertTrue(self.report.exists())

    def test_removed_warning_does_not_fail_current_release(self):
        first = self.archive('before.zip', {'.env': 'fake'})
        second = self.archive('after.zip', {'index': 'ok'})
        self.assertEqual(self.run_cli('compare', first, second, '-o', self.report, '--fail-on-warnings')[0], 0)
        self.assertEqual(self.run_cli('inspect', first, '-o', self.report, '--fail-on-warnings')[0], 1)

    def test_markdown_written_even_when_growth_check_fails(self):
        first = self.archive('before.zip', {'index': 'old'})
        second = self.archive('after.zip', {'index': 'longer'})
        code, output, _ = self.run_cli('compare', first, second, '-o', self.report, '--json', self.data, '--markdown', self.markdown, '--fail-on-growth', '0')
        self.assertEqual(code, 1)
        self.assertIn('Shipglass', self.markdown.read_text(encoding='utf-8'))
        self.assertIn('Markdown:', output)
        self.assertTrue(self.report.exists())
        self.assertTrue(self.data.exists())

    def test_markdown_cannot_overwrite_archive_or_other_outputs(self):
        package = self.archive('one.zip', {'index': 'ok'})
        original = package.read_bytes()
        self.assertEqual(self.run_cli('inspect', package, '-o', self.report, '--markdown', package)[0], 2)
        self.assertEqual(package.read_bytes(), original)
        self.assertEqual(self.run_cli('inspect', package, '-o', self.report, '--json', self.data, '--markdown', self.data)[0], 2)
        self.assertFalse(self.report.exists())
        self.data.write_text('Existing report', encoding='utf-8')
        try:
            self.markdown.hardlink_to(self.data)
        except OSError:
            self.skipTest('Hard links are unavailable')
        self.assertEqual(self.run_cli('inspect', package, '-o', self.report, '--json', self.data, '--markdown', self.markdown)[0], 2)
        self.assertEqual(self.data.read_text(encoding='utf-8'), 'Existing report')

    def test_inspect_is_empty_baseline(self):
        package = self.archive('one.zip', {'package/index.js': 'hi'})
        code, _, _ = self.run_cli('inspect', package, '-o', self.report, '--json', self.data, '--strip-components', '1')
        self.assertEqual(code, 0)
        data = json.loads(self.data.read_text())
        self.assertEqual(data['summary']['before_bytes'], 0)
        self.assertEqual(data['files'][0]['path'], 'index.js')

    def test_outputs_cannot_overwrite_inputs_or_each_other(self):
        package = self.archive('one.zip', {'index': 'ok'})
        original = package.read_bytes()
        self.assertEqual(self.run_cli('inspect', package, '-o', package)[0], 2)
        self.assertEqual(package.read_bytes(), original)
        self.assertEqual(self.run_cli('inspect', package, '-o', self.report, '--json', self.report)[0], 2)
        alias = self.root / 'alias.html'
        try:
            alias.hardlink_to(package)
        except OSError:
            return
        self.assertEqual(self.run_cli('inspect', package, '-o', alias)[0], 2)
        self.assertEqual(package.read_bytes(), original)

    def test_malformed_archive_is_clean_error(self):
        package = self.root / 'broken.zip'
        package.write_text('not a zip')
        code, _, error = self.run_cli('inspect', package, '-o', self.report)
        self.assertEqual(code, 2)
        self.assertIn('ZIP end-of-directory record is missing or truncated', error)
        self.assertNotIn('Traceback', error)

    def test_terminal_display_escapes_control_characters(self):
        from shipglass.cli import _display
        self.assertEqual(_display('release\x1b[2J.zip'), r'release\x1b[2J.zip')
        self.assertEqual(_display('发布.zip'), '发布.zip')
        self.assertNotIn('\n', _display('line\nbreak'))

    def test_demo_reproducible_and_exercises_changes(self):
        code, _, _ = self.run_cli('demo', '-o', self.report, '--json', self.data)
        self.assertEqual(code, 0)
        original = self.data.read_bytes()
        data = json.loads(original)
        self.assertEqual(data['summary']['added'], 4)
        self.assertEqual(data['summary']['removed'], 1)
        self.assertEqual(data['summary']['changed'], 2)
        self.assertEqual(data['summary']['warning_count'], 4)
        self.run_cli('demo', '-o', self.report, '--json', self.data)
        self.assertEqual(self.data.read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
