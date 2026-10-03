import json
import re
import unittest

from shipglass.report import render_report


class ReportTests(unittest.TestCase):
    def comparison(self):
        name = '</script><script>alert("path")</script>'
        entry = {'path': name, 'status': 'changed', 'before_size': 1, 'after_size': 2, 'delta': 1, 'warnings': []}
        snapshot = {'name': name, 'archive_bytes': 100, 'total_bytes': 2, 'format': 'zip', 'files': [{'content': 'PRIVATE_CONTENT', 'sha256': 'PRIVATE_HASH'}]}
        return {'schema_version': 1, 'before': snapshot, 'after': snapshot, 'summary': {'before_bytes': 1, 'after_bytes': 2, 'delta_bytes': 1, 'added': 0, 'changed': 1, 'removed': 0, 'unchanged': 0, 'warning_count': 0}, 'files': [entry], 'warnings': []}

    def test_script_delimiters_are_escaped_and_roundtrip(self):
        source = self.comparison()
        html = render_report(source)
        self.assertNotIn(source['files'][0]['path'], html)
        match = re.search(r'<script[^>]*type="application/json"[^>]*>(.*?)</script>', html, re.S)
        self.assertIsNotNone(match)
        payload = json.loads(match.group(1))
        self.assertEqual(payload['files'][0]['path'], source['files'][0]['path'])
        self.assertNotIn('<', match.group(1))
        self.assertEqual(html.count('</script>'), 2)

    def test_snapshot_inventory_is_not_embedded(self):
        html = render_report(self.comparison())
        self.assertNotIn('PRIVATE_CONTENT', html)
        self.assertNotIn('PRIVATE_HASH', html)
        self.assertNotIn('__SHIPGLASS_DATA__', html)

    def test_report_has_no_external_runtime_assets(self):
        html = render_report(self.comparison())
        self.assertNotRegex(html, r'<(?:script|link|img)[^>]+(?:src|href)=["\']https?://')
        self.assertIn("connect-src 'none'", html)


if __name__ == '__main__':
    unittest.main()
