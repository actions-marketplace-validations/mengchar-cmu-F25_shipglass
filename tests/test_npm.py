import base64
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

from shipglass import core, npm


class Response(io.BytesIO):
    def __init__(self, data, url='https://registry.npmjs.org/example', headers=None):
        super().__init__(data)
        self.url = url
        self.headers = headers or {}
        self.requests = []

    def geturl(self):
        return self.url

    def read(self, size=-1):
        self.requests.append(size)
        return super().read(size)


class NpmTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.payload = b'Published tarball bytes; never execute or extract here.'
        self.opener = Mock()
        self.build = patch('shipglass.npm.urllib.request.build_opener', return_value=self.opener).start()
        self.addCleanup(patch.stopall)

    def metadata(self, package='example', version='1.2.3'):
        return {
            'name': package,
            'version': version,
            'dist': {
                'tarball': 'https://registry.npmjs.org/example/-/example-1.2.3.tgz',
                'integrity': 'sha512-' + base64.b64encode(hashlib.sha512(self.payload).digest()).decode(),
                'shasum': hashlib.sha1(self.payload).hexdigest(),
            },
        }

    def responses(self, metadata=None, archive=None):
        if metadata is None:
            metadata = self.metadata()
        self.opener.open.side_effect = [
            Response(json.dumps(metadata).encode()),
            archive if archive is not None else Response(self.payload),
        ]

    def assert_empty(self):
        self.assertEqual(list(self.root.iterdir()), [])

    def test_verified_download_and_timeout(self):
        self.responses()
        result = npm.download('example', '1.2.3', self.root)
        self.assertEqual(result.read_bytes(), self.payload)
        self.assertEqual(result.parent, self.root)
        self.assertTrue(result.name.startswith('example-1.2.3-'))
        self.assertEqual(result.suffix, '.tgz')
        self.assertEqual(self.opener.open.call_count, 2)
        for call in self.opener.open.call_args_list:
            self.assertEqual(call.kwargs['timeout'], npm.NETWORK_TIMEOUT)
            self.assertNotIn('Authorization', call.args[0].headers)
        handlers = self.build.call_args.args
        self.assertTrue(any(isinstance(handler, npm._RegistryRedirect) for handler in handlers))

    def test_scoped_name_and_prerelease_build_are_encoded(self):
        self.responses(self.metadata('@scope/name', '1.2.3-rc.1+build.5'))
        result = npm.download('@scope/name', '1.2.3-rc.1+build.5', self.root)
        request = self.opener.open.call_args_list[0].args[0]
        self.assertEqual(request.full_url, 'https://registry.npmjs.org/%40scope%2Fname/1.2.3-rc.1%2Bbuild.5')
        self.assertTrue(result.name.startswith('scope-name-1.2.3-rc.1+build.5-'))
        self.assertEqual(result.parent, self.root)

    def test_sha1_fallback(self):
        metadata = self.metadata()
        del metadata['dist']['integrity']
        self.responses(metadata)
        self.assertEqual(npm.download('example', '1.2.3', self.root).read_bytes(), self.payload)

    def test_sha512_takes_priority_over_shasum(self):
        metadata = self.metadata()
        metadata['dist']['shasum'] = '0' * 40
        self.responses(metadata)
        self.assertEqual(npm.download('example', '1.2.3', self.root).read_bytes(), self.payload)

    def test_wrong_name_or_version_is_rejected_before_archive_request(self):
        for field, value in [('name', 'other'), ('version', '2.0.0')]:
            with self.subTest(field=field):
                metadata = self.metadata()
                metadata[field] = value
                self.opener.reset_mock()
                self.responses(metadata)
                with self.assertRaisesRegex(ValueError, 'does not match'):
                    npm.download('example', '1.2.3', self.root)
                self.assertEqual(self.opener.open.call_count, 1)
                self.assert_empty()

    def test_malformed_metadata(self):
        cases = [b'{', b'\xff', b'[]', b'null', b'{}', b'{"name":"example","version":"1.2.3","dist":[]}']
        cases.append(b'[' * 2000 + b']' * 2000)
        for raw in cases:
            with self.subTest(raw=raw[:60]):
                self.opener.open.side_effect = [Response(raw)]
                with self.assertRaises(ValueError):
                    npm.download('example', '1.2.3', self.root)
                self.assert_empty()

    def test_missing_or_malformed_digest_is_rejected(self):
        for fields in [{}, {'shasum': 'short'}, {'integrity': None}, {'integrity': ''},
                       {'integrity': 'sha512-!!!!'}, {'integrity': 'sha512-YQ=='},
                       {'integrity': 'sha512-' + 'é'}, {'integrity': 'unknown-YQ=='}]:
            with self.subTest(fields=fields):
                metadata = self.metadata()
                metadata['dist'] = {'tarball': metadata['dist']['tarball'], **fields}
                self.opener.reset_mock()
                self.responses(metadata)
                with self.assertRaises(ValueError):
                    npm.download('example', '1.2.3', self.root)
                self.assertEqual(self.opener.open.call_count, 1)
                self.assert_empty()

    def test_disallowed_tarball_urls(self):
        urls = ['http://registry.npmjs.org/file.tgz', 'https://example.com/file.tgz',
                'https://registry.npmjs.org.evil.test/file.tgz', 'file:///tmp/file.tgz',
                'https://user:secret@registry.npmjs.org/file.tgz',
                'https://registry.npmjs.org:444/file.tgz', '//registry.npmjs.org/file.tgz',
                'https://registry.npmjs.org/evil\nname.tgz', None, [], 'https://[broken']
        for url in urls:
            with self.subTest(url=url):
                metadata = self.metadata()
                metadata['dist']['tarball'] = url
                self.opener.reset_mock()
                self.responses(metadata)
                with self.assertRaises(ValueError):
                    npm.download('example', '1.2.3', self.root)
                self.assertEqual(self.opener.open.call_count, 1)
                self.assert_empty()

    def test_redirects_are_checked_before_following(self):
        handler = npm._RegistryRedirect()
        request = urllib.request.Request('https://registry.npmjs.org/example')
        for url in ['https://evil.test/file.tgz', 'http://registry.npmjs.org/file.tgz',
                    'https://user:pass@registry.npmjs.org/file.tgz']:
            with self.subTest(url=url), self.assertRaises(ValueError):
                handler.redirect_request(request, None, 302, 'Found', {}, url)
        allowed = 'https://registry.npmjs.org/example/-/example-1.2.3.tgz'
        redirected = handler.redirect_request(request, None, 302, 'Found', {}, allowed)
        self.assertEqual(redirected.full_url, allowed)

    def test_final_response_url_is_checked(self):
        self.opener.open.side_effect = [Response(json.dumps(self.metadata()).encode(), 'https://evil.test/metadata')]
        with self.assertRaises(ValueError):
            npm.download('example', '1.2.3', self.root)
        self.responses(archive=Response(self.payload, 'https://evil.test/file.tgz'))
        with self.assertRaises(ValueError):
            npm.download('example', '1.2.3', self.root)
        self.assert_empty()

    def test_missing_version_is_a_concise_error(self):
        self.opener.open.side_effect = urllib.error.HTTPError('https://registry.npmjs.org/example/1.2.3', 404, 'Not Found', {}, None)
        with self.assertRaisesRegex(ValueError, 'not found: example@1.2.3'):
            npm.download('example', '1.2.3', self.root)
        self.assert_empty()

    def test_digest_mismatch_removes_download(self):
        self.responses(archive=Response(b'Wrong or corrupted tarball'))
        with self.assertRaisesRegex(ValueError, 'digest does not match'):
            npm.download('example', '1.2.3', self.root)
        self.assert_empty()

    def test_sha512_mismatch_does_not_fall_back_to_matching_sha1(self):
        metadata = self.metadata()
        metadata['dist']['integrity'] = 'sha512-' + base64.b64encode(bytes(64)).decode()
        self.responses(metadata)
        with self.assertRaisesRegex(ValueError, 'digest does not match'):
            npm.download('example', '1.2.3', self.root)
        self.assert_empty()

    def test_metadata_bounds_with_and_without_content_length(self):
        for headers in [{}, {'Content-Length': '21'}, {'Content-Length': '1'}]:
            with self.subTest(headers=headers):
                response = Response(b'x' * 21, headers=headers)
                self.opener.open.side_effect = [response]
                with patch.object(npm, 'MAX_METADATA_BYTES', 20), self.assertRaisesRegex(ValueError, 'metadata exceeds'):
                    npm.download('example', '1.2.3', self.root)
                if headers.get('Content-Length') == '21':
                    self.assertEqual(response.requests, [])
                self.assert_empty()

    def test_archive_bounds_with_and_without_content_length(self):
        for headers in [{}, {'Content-Length': '21'}, {'Content-Length': '1'}]:
            with self.subTest(headers=headers):
                response = Response(b'x' * 21, headers=headers)
                self.responses(archive=response)
                with patch.object(core, 'MAX_ARCHIVE_BYTES', 20), self.assertRaisesRegex(ValueError, 'archive exceeds'):
                    npm.download('example', '1.2.3', self.root)
                if headers.get('Content-Length') == '21':
                    self.assertEqual(response.requests, [])
                self.assert_empty()

    def test_archive_exactly_at_limit_succeeds(self):
        self.responses(archive=Response(self.payload, headers={'Content-Length': str(len(self.payload))}))
        with patch.object(core, 'MAX_ARCHIVE_BYTES', len(self.payload)):
            self.assertEqual(npm.download('example', '1.2.3', self.root).read_bytes(), self.payload)

    def test_bad_or_inconsistent_content_length(self):
        for length in ['-1', 'invalid', str(len(self.payload) + 1)]:
            with self.subTest(length=length):
                self.responses(archive=Response(self.payload, headers={'Content-Length': length}))
                with self.assertRaisesRegex(ValueError, 'length'):
                    npm.download('example', '1.2.3', self.root)
                self.assert_empty()

    def test_interrupted_archive_cleans_partial_file(self):
        response = Response(self.payload)
        response.read = Mock(side_effect=[b'partial', http.client.IncompleteRead(b'', 10)])
        self.responses(archive=response)
        with self.assertRaisesRegex(OSError, 'Cannot download'):
            npm.download('example', '1.2.3', self.root)
        self.assert_empty()

    def test_network_failures_are_concise_errors(self):
        for error in [urllib.error.URLError('failed'), TimeoutError(),
                      urllib.error.HTTPError('https://registry.npmjs.org/example', 503, 'Unavailable', {}, None)]:
            with self.subTest(error=error):
                self.opener.open.side_effect = error
                with self.assertRaises(OSError):
                    npm.download('example', '1.2.3', self.root)
                self.assert_empty()

    def test_invalid_inputs_do_not_access_the_network(self):
        names = ['', None, '../example', './example', '/tmp/example', 'https://registry.npmjs.org/example',
                 'example@1.2.3', '@scope/name/extra', '@../example', 'bad name', 'example\n', 'a' * 215]
        versions = ['', None, 'latest', 'next', '^1.2.3', '~1.2.3', '*', '1.2', 'v1.2.3',
                    '01.2.3', '1.2.3-01', '1.2.3+', '1.2.3/../2', '1.2.3 || 2.0.0', '1.2.3\n']
        for package, version in [(name, '1.2.3') for name in names] + [('example', version) for version in versions]:
            with self.subTest(package=package, version=version), self.assertRaises(ValueError):
                npm.download(package, version, self.root)
        self.build.assert_not_called()
        self.opener.open.assert_not_called()
        self.assert_empty()


if __name__ == '__main__':
    unittest.main()
