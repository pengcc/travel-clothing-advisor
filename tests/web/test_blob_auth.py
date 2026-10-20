"""Offline authentication boundaries against the pinned official SDK."""
from email.message import Message
import unittest
from unittest.mock import patch

from web.blob_store import blob_session


class BlobAuthTests(unittest.TestCase):
    def setUp(self):
        try:
            import httpx2
        except ImportError:
            self.skipTest('Optional SDK environment required')
        from vercel.api import session
        self.session = session
        self.http = httpx2
        self.env = dict(VERCEL_ENV='preview', BLOB_STORE_ID='store_trial',
                        TRAVEL_PREVIEW_BLOB_STORE_ID='trial')
        self.headers = Message()
        self.headers['X-Vercel-Oidc-Token'] = 'synthetic-request-oidc'

    def test_preview_request_oidc_private_read_without_long_lived_token(self):
        calls = []
        client = self.http.Client
        def respond(request):
            calls.append(request)
            return self.http.Response(200, content=b'weather')
        with patch.dict('os.environ', self.env, clear=True), patch(
                'vercel.api.session', side_effect=lambda **kw: self.session(
                    service_options=kw['service_options'],
                    httpx_client_factory=lambda: client(transport=self.http.MockTransport(respond)))):
            with blob_session('preview/s2-test', request_headers=self.headers) as reader:
                self.assertEqual(reader.get('preview/s2-test/sample'), b'weather')
                self.assertFalse(hasattr(reader, 'put'))
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].headers['authorization'], 'Bearer synthetic-request-oidc')
        self.assertEqual(calls[0].url.host, 'trial.private.blob.vercel-storage.com')

    def test_missing_request_credentials_never_use_ambient_defaults(self):
        self.env.update(VERCEL_OIDC_TOKEN='synthetic-build-token',
                        BLOB_READ_WRITE_TOKEN='synthetic-default',
                        VERCEL_BLOB_READ_WRITE_TOKEN='synthetic-other-default',
                        TRAVEL_PREVIEW_BLOB_TOKEN='synthetic-local-only')
        self.reject(self.env, headers={})

    def reject(self, env, *, headers=None, publisher=False):
        with patch.dict('os.environ', env, clear=True), patch.object(
                self.http, 'Client', side_effect=AssertionError('Network forbidden')):
            with self.assertRaises(OSError):
                with blob_session('preview/s2-test', publisher=publisher,
                                  request_headers=self.headers if headers is None else headers):
                    self.fail('Unsafe session accepted')

    def test_wrong_or_missing_connected_store_rejected_before_io(self):
        for store in ('production', ''):
            with self.subTest(store=store):
                self.reject(dict(self.env, BLOB_STORE_ID=store))
        self.reject(dict(self.env, TRAVEL_PREVIEW_BLOB_STORE_ID=''))

    def test_production_and_hosted_publisher_rejected_before_io(self):
        for publisher in (False, True):
            self.reject(dict(self.env, VERCEL_ENV='production'), publisher=publisher)
        self.reject(self.env, publisher=True)
        self.reject(dict(self.env, VERCEL_ENV='development', VERCEL='1'), publisher=True)

    def test_local_publisher_dedicated_token_and_embedded_store_validation(self):
        client = self.http.Client
        for embedded, success in (('trial', True), ('production', False)):
            calls = []
            env = dict(TRAVEL_PREVIEW_BLOB_STORE_ID='trial',
                       TRAVEL_PREVIEW_BLOB_TOKEN=f'vercel_blob_rw_{embedded}_synthetic')
            def respond(request):
                calls.append(request)
                return self.http.Response(200, content=b'weather')
            with self.subTest(embedded=embedded), patch.dict('os.environ', env, clear=True), \
                 patch('vercel.api.session', side_effect=lambda **kw: self.session(
                     service_options=kw['service_options'],
                     httpx_client_factory=lambda: client(transport=self.http.MockTransport(respond)))):
                if success:
                    with blob_session('preview/s2-test', publisher=True) as publisher:
                        self.assertTrue(hasattr(publisher, 'put'))
                        self.assertEqual(publisher.get('preview/s2-test/sample'), b'weather')
                    self.assertEqual(len(calls), 1)
                else:
                    with self.assertRaises(OSError):
                        with blob_session('preview/s2-test', publisher=True) as publisher:
                            publisher.get('preview/s2-test/sample')
                    self.assertEqual(calls, [])
        self.reject(dict(TRAVEL_PREVIEW_BLOB_STORE_ID='trial',
                         BLOB_READ_WRITE_TOKEN='synthetic-default'), publisher=True)
