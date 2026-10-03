import contextlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

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

    def downloader(self, archives):
        def download(package, version, directory):
            source = archives[version]
            destination = directory / source.name
            destination.write_bytes(source.read_bytes())
            return destination
        return download

    def test_npm_writes_scoped_version_reports_and_cleans_downloads(self):
        first = self.archive('scope-package-1.0.0.zip', {'package/index.js': 'old'})
        second = self.archive('scope-package-2.0.0.zip', {'package/index.js': 'new', 'package/README.md': 'readme'})
        with mock.patch('shipglass.cli.npm.download', side_effect=self.downloader({'1.0.0': first, '2.0.0': second})) as download:
            code, output, error = self.run_cli('npm', '@scope/package', '1.0.0', '2.0.0', '-o', self.report, '--json', self.data, '--markdown', self.markdown, '--strip-components', '1')
        self.assertEqual(code, 0)
        self.assertEqual([call.args[:2] for call in download.call_args_list], [('@scope/package', '1.0.0'), ('@scope/package', '2.0.0')])
        for call in download.call_args_list:
            self.assertFalse(call.args[2].exists())
        data = json.loads(self.data.read_text())
        self.assertEqual(data['before']['name'], '@scope/package@1.0.0')
        self.assertEqual(data['after']['name'], '@scope/package@2.0.0')
        self.assertEqual(data['summary']['changed'], 1)
        self.assertEqual(data['summary']['added'], 1)
        self.assertEqual([file['path'] for file in data['files']], ['README.md', 'index.js'])
        self.assertIn('Shipglass', self.report.read_text())
        self.assertIn('Shipglass', self.markdown.read_text())
        self.assertIn('Markdown:', output)
        self.assertIn('Downloading @scope/package@1.0.0', error)
        self.assertIn('Downloading @scope/package@2.0.0', error)

    def test_npm_same_version_downloads_once_and_reports_no_changes(self):
        package = self.archive('package-1.0.0.zip', {'package/index.js': 'ok'})
        with mock.patch('shipglass.cli.npm.download', side_effect=self.downloader({'1.0.0': package})) as download:
            code, _, error = self.run_cli('npm', 'package', '1.0.0', '1.0.0', '-o', self.report, '--json', self.data)
        self.assertEqual(code, 0)
        download.assert_called_once()
        self.assertFalse(download.call_args.args[2].exists())
        summary = json.loads(self.data.read_text())['summary']
        self.assertEqual((summary['changed'], summary['added'], summary['removed'], summary['delta_bytes']), (0, 0, 0, 0))
        self.assertEqual(summary['unchanged'], 1)
        self.assertEqual(error.count('Downloading package@1.0.0'), 1)

    def test_npm_policy_failures_still_write_reports_and_clean_downloads(self):
        first = self.archive('package-1.0.0.zip', {'package/index.js': 'old'})
        second = self.archive('package-2.0.0.zip', {'package/index.js': 'longer', 'package/.env': 'private'})
        for flags in [('--fail-on-growth', '0'), ('--fail-on-warnings',)]:
            with self.subTest(flags=flags), mock.patch('shipglass.cli.npm.download', side_effect=self.downloader({'1.0.0': first, '2.0.0': second})) as download:
                code, _, _ = self.run_cli('npm', 'package', '1.0.0', '2.0.0', '-o', self.report, '--json', self.data, '--markdown', self.markdown, *flags)
                self.assertEqual(code, 1)
                for path in (self.report, self.data, self.markdown):
                    self.assertTrue(path.exists())
                    path.unlink()
                for call in download.call_args_list:
                    self.assertFalse(call.args[2].exists())

    def test_npm_download_failure_cleans_partial_downloads_and_writes_no_reports(self):
        def fail_download(package, version, directory):
            path = directory / f'package-{version}.tgz'
            path.write_bytes(b'partial download')
            if version == '2.0.0':
                raise OSError('download failed\x1b[2J')
            return path

        with mock.patch('shipglass.cli.npm.download', side_effect=fail_download) as download:
            code, _, error = self.run_cli('npm', 'package', '1.0.0', '2.0.0', '-o', self.report, '--json', self.data, '--markdown', self.markdown)
        self.assertEqual(code, 2)
        self.assertEqual(download.call_count, 2)
        for call in download.call_args_list:
            self.assertFalse(call.args[2].exists())
        self.assertIn(r'download failed\x1b[2J', error)
        self.assertNotIn('\x1b', error)
        self.assertNotIn('Traceback', error)
        for path in (self.report, self.data, self.markdown):
            self.assertFalse(path.exists())

    def test_npm_scan_failure_cleans_downloads_and_writes_no_reports(self):
        first = self.archive('package-1.0.0.zip', {'package/index.js': 'old'})
        second = self.root / 'package-2.0.0.zip'
        second.write_bytes(b'not an archive')
        with mock.patch('shipglass.cli.npm.download', side_effect=self.downloader({'1.0.0': first, '2.0.0': second})) as download:
            code, _, error = self.run_cli('npm', 'package', '1.0.0', '2.0.0', '-o', self.report, '--json', self.data, '--markdown', self.markdown)
        self.assertEqual(code, 2)
        self.assertIn('ZIP end-of-directory record is missing or truncated', error)
        for call in download.call_args_list:
            self.assertFalse(call.args[2].exists())
        for path in (self.report, self.data, self.markdown):
            self.assertFalse(path.exists())

    def test_npm_duplicate_outputs_fail_before_downloading(self):
        with mock.patch('shipglass.cli.npm.download') as download:
            code, _, error = self.run_cli('npm', 'package', '1.0.0', '2.0.0', '-o', self.report, '--json', self.data, '--markdown', self.data)
        self.assertEqual(code, 2)
        download.assert_not_called()
        self.assertIn('output files must use different paths', error)
        self.assertFalse(self.report.exists())

    def test_local_commands_do_not_download_packages(self):
        first = self.archive('before.zip', {'index.js': 'old'})
        second = self.archive('after.zip', {'index.js': 'new'})
        with mock.patch('shipglass.cli.npm.download', side_effect=AssertionError('unexpected network access')) as download:
            for args in [('compare', first, second), ('inspect', second), ('demo',)]:
                with self.subTest(command=args[0]):
                    self.assertEqual(self.run_cli(*args, '-o', self.report)[0], 0)
        download.assert_not_called()

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
