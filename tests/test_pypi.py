import hashlib
import http.client
import io
import json
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import Mock, patch

from shipglass import core, pypi


class Response(io.BytesIO):
    def __init__(self, data, url='https://pypi.org/pypi/example/1.2.3/json', headers=None):
        super().__init__(data)
        self.url = url
        self.headers = headers or {}

    def geturl(self):
        return self.url


class PypiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.payload = b'Published wheel bytes; no installation or execution.'
        self.archive_url = 'https://files.pythonhosted.org/packages/example.whl'
        self.opener = Mock()
        self.build = patch('shipglass.pypi.urllib.request.build_opener', return_value=self.opener).start()
        self.addCleanup(patch.stopall)

    def metadata(self, name='example', version='1.2.3', tag='py3-none-any'):
        return {'info': {'name': name, 'version': version}, 'urls': [{
            'filename': f'{name.replace("-", "_")}-{version}-{tag}.whl',
            'packagetype': 'bdist_wheel', 'url': self.archive_url,
            'digests': {'sha256': hashlib.sha256(self.payload).hexdigest()},
            'size': len(self.payload), 'yanked': False,
        }]}

    def responses(self, metadata=None, archive=None):
        self.opener.reset_mock()
        self.opener.open.side_effect = [
            Response(json.dumps(self.metadata() if metadata is None else metadata).encode()),
            Response(self.payload, self.archive_url) if archive is None else archive,
        ]

    def assert_empty(self):
        self.assertEqual(list(self.root.iterdir()), [])

    def test_verified_download_normalizes_name_and_uses_host_specific_handlers(self):
        self.responses(self.metadata('typing-extensions', '4.12.2', 'py2.py3-none-any'))
        result = pypi.download('Typing_Extensions', '4.12.2', self.root)
        self.assertEqual(result.read_bytes(), self.payload)
        self.assertEqual(result.parent, self.root)
        self.assertEqual(result.suffix, '.whl')
        requests = self.opener.open.call_args_list
        self.assertEqual(requests[0].args[0].full_url, 'https://pypi.org/pypi/typing-extensions/4.12.2/json')
        self.assertEqual(requests[1].args[0].full_url, self.archive_url)
        self.assertEqual([c.args[0].host for c in self.build.call_args_list], ['pypi.org', 'files.pythonhosted.org'])
        for call in requests:
            self.assertEqual(call.kwargs['timeout'], pypi.NETWORK_TIMEOUT)
            self.assertNotIn('Authorization', call.args[0].headers)

    def test_pre_and_local_version_is_encoded_and_matched_exactly(self):
        version = '1!2.0rc1+local.3'
        self.responses(self.metadata(version=version))
        self.assertEqual(pypi.download('example', version, self.root).read_bytes(), self.payload)
        url = self.opener.open.call_args_list[0].args[0].full_url
        self.assertEqual(url, 'https://pypi.org/pypi/example/1%212.0rc1%2Blocal.3/json')

    def test_invalid_inputs_make_no_request(self):
        for name, version in [('bad/name', '1.0'), ('-bad', '1.0'), ('bad.', '1.0'), ('x'*257, '1.0'),
                              ('example', 'latest'), ('example', '>=1.0'), ('example', '../1.0'), ('example', 'v1.0')]:
            with self.subTest(name=name, version=version), self.assertRaises(ValueError):
                pypi.download(name, version, self.root)
        self.opener.open.assert_not_called()

    def test_returned_name_and_version_must_match(self):
        for name, version in [('other', '1.2.3'), ('example', '1.2.3.0')]:
            with self.subTest(name=name, version=version):
                self.responses(self.metadata(name, version))
                with self.assertRaisesRegex(ValueError, 'does not match'):
                    pypi.download('example', '1.2.3', self.root)
                self.assertEqual(self.opener.open.call_count, 1)
                self.assert_empty()

    def test_only_one_unyanked_universal_wheel_is_selected(self):
        metadata = self.metadata()
        metadata['urls'] += self.metadata(tag='cp312-cp312-manylinux_x86_64')['urls']
        metadata['urls'] += [{**metadata['urls'][0], 'filename': 'example-1.2.3-1-py3-none-any.whl', 'yanked': True}]
        self.responses(metadata)
        self.assertEqual(pypi.download('example', '1.2.3', self.root).read_bytes(), self.payload)

    def test_ambiguous_builds_are_not_silently_selected(self):
        metadata = self.metadata()
        metadata['urls'].append({**metadata['urls'][0], 'filename': 'example-1.2.3-1.foo-py3-none-any.whl'})
        self.responses(metadata)
        with self.assertRaisesRegex(ValueError, 'Multiple.*shipglass compare'):
            pypi.download('example', '1.2.3', self.root)
        self.assertEqual(self.opener.open.call_count, 1)

    def test_yanked_and_unsupported_wheels_explain_manual_comparison(self):
        for tag in ['py2-none-any', 'cp312-none-any', 'py3-none-win_amd64', 'py3-abi3-any', 'py310-none-any']:
            with self.subTest(tag=tag):
                self.responses(self.metadata(tag=tag))
                with self.assertRaisesRegex(ValueError, 'No universal.*shipglass compare'):
                    pypi.download('example', '1.2.3', self.root)
        metadata = self.metadata()
        metadata['urls'][0]['yanked'] = True
        self.responses(metadata)
        with self.assertRaisesRegex(ValueError, 'Only yanked.*shipglass compare'):
            pypi.download('example', '1.2.3', self.root)
        metadata['urls'][0]['packagetype'] = 'sdist'
        self.responses(metadata)
        with self.assertRaisesRegex(ValueError, 'No universal'):
            pypi.download('example', '1.2.3', self.root)
        self.assert_empty()

    def test_wrong_or_malformed_wheel_filenames_are_not_selected(self):
        for name in ['other-1.2.3-py3-none-any.whl', 'example-2.0-py3-none-any.whl',
                     'example-1.2.3-invalid-py3-none-any.whl', '../example-1.2.3-py3-none-any.whl', None]:
            with self.subTest(name=name):
                metadata = self.metadata()
                metadata['urls'][0]['filename'] = name
                self.responses(metadata)
                with self.assertRaisesRegex(ValueError, 'No universal'):
                    pypi.download('example', '1.2.3', self.root)

    def test_invalid_metadata_is_a_clean_error(self):
        for raw in [b'{', b'\xff', b'[]', b'null', b'{}', b'['*2000 + b']'*2000]:
            with self.subTest(raw=raw[:20]):
                self.opener.open.side_effect = [Response(raw)]
                with self.assertRaises(ValueError):
                    pypi.download('example', '1.2.3', self.root)
        for field, value in [('yanked', 'false'), ('digests', {}), ('digests', {'sha256': 'short'}),
                             ('digests', {'sha256': 'z'*64}), ('size', True), ('size', -1), ('size', 1.5),
                             ('size', core.MAX_ARCHIVE_BYTES + 1)]:
            with self.subTest(field=field, value=value):
                metadata = self.metadata()
                metadata['urls'][0][field] = value
                self.responses(metadata)
                with self.assertRaises(ValueError):
                    pypi.download('example', '1.2.3', self.root)
                self.assertEqual(self.opener.open.call_count, 1)
        self.assert_empty()

    def test_unsafe_archive_urls_rejected_before_download(self):
        for url in ['http://files.pythonhosted.org/file.whl', 'https://pypi.org/file.whl',
                    'https://files.pythonhosted.org.evil.test/file.whl', 'https://user:secret@files.pythonhosted.org/f.whl',
                    'https://files.pythonhosted.org:444/f.whl', 'https://files.pythonhosted.org/f#fragment',
                    'https://files.pythonhosted.org/a\nb.whl', 'https://files.pythonhosted.org/a\\b.whl', None]:
            with self.subTest(url=url):
                metadata = self.metadata()
                metadata['urls'][0]['url'] = url
                self.responses(metadata)
                with self.assertRaises(ValueError):
                    pypi.download('example', '1.2.3', self.root)
                self.assertEqual(self.opener.open.call_count, 1)

    def test_redirects_cannot_cross_metadata_and_archive_hosts(self):
        for host, other in [('pypi.org', 'files.pythonhosted.org'), ('files.pythonhosted.org', 'pypi.org')]:
            handler = pypi._HostRedirect(host)
            request = urllib.request.Request(f'https://{host}/original')
            for url in [f'https://{other}/file', f'http://{host}/file', f'https://user:pass@{host}/file']:
                with self.subTest(url=url), self.assertRaises(ValueError):
                    handler.redirect_request(request, None, 302, 'Found', {}, url)
            allowed = f'https://{host}/next'
            self.assertEqual(handler.redirect_request(request, None, 302, 'Found', {}, allowed).full_url, allowed)

    def test_final_response_hosts_are_checked(self):
        self.opener.open.side_effect = [Response(json.dumps(self.metadata()).encode(), 'https://evil.test/json')]
        with self.assertRaises(ValueError):
            pypi.download('example', '1.2.3', self.root)
        self.responses(archive=Response(self.payload, 'https://pypi.org/file.whl'))
        with self.assertRaises(ValueError):
            pypi.download('example', '1.2.3', self.root)
        self.assert_empty()

    def test_metadata_limit_with_and_without_length(self):
        for headers in [{}, {'Content-Length': '17'}]:
            with self.subTest(headers=headers), patch.object(pypi, 'MAX_METADATA_BYTES', 16):
                self.opener.open.side_effect = [Response(b'x'*17, headers=headers)]
                with self.assertRaisesRegex(ValueError, 'metadata exceeds'):
                    pypi.download('example', '1.2.3', self.root)
        self.assert_empty()

    def test_size_digest_and_response_length_failures_clean_up(self):
        for payload, headers, message in [(b'x'*len(self.payload), {}, 'digest'),
                                         (self.payload[:-1], {}, 'size'),
                                         (self.payload+b'x', {}, 'exceeds'),
                                         (self.payload, {'Content-Length': 'bad'}, 'response length'),
                                         (self.payload, {'Content-Length': '1'}, 'inconsistent'),
                                         (self.payload, {'Content-Length': str(len(self.payload)+1)}, 'exceeds')]:
            with self.subTest(message=message):
                self.responses(archive=Response(payload, self.archive_url, headers))
                with self.assertRaisesRegex(ValueError, message):
                    pypi.download('example', '1.2.3', self.root)
                self.assert_empty()

    def test_http_errors_and_interrupted_body_clean_up(self):
        for code in (404, 500):
            self.opener.open.side_effect = urllib.error.HTTPError('https://pypi.org/', code, 'failed', {}, None)
            with self.subTest(code=code), self.assertRaises((ValueError, OSError)):
                pypi.download('example', '1.2.3', self.root)
        for error in (TimeoutError(), urllib.error.URLError('offline'), http.client.IncompleteRead(b'partial')):
            response = Response(b'', self.archive_url)
            response.read = Mock(side_effect=[self.payload[:3], error])
            self.responses(archive=response)
            with self.subTest(error=type(error).__name__), self.assertRaisesRegex(OSError, 'Cannot download'):
                pypi.download('example', '1.2.3', self.root)
            self.assert_empty()


if __name__ == '__main__':
    unittest.main()
