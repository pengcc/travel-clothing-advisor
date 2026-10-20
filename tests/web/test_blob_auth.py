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
        if headers is None and not publisher:
            headers = self.headers
        with patch.dict('os.environ', env, clear=True), patch.object(
                self.http, 'Client', side_effect=AssertionError('Network forbidden')):
            with self.assertRaises(OSError):
                with blob_session('preview/s2-test', publisher=publisher,
                                  request_headers=headers):
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

    def local_env(self, **changes):
        return dict(BLOB_STORE_ID='store_trial', TRAVEL_PREVIEW_BLOB_STORE_ID='trial',
                    VERCEL_OIDC_TOKEN='synthetic-cli-oidc', **changes)

    def test_local_publisher_requires_matching_store_and_oidc_without_fallback(self):
        for variable in ('BLOB_STORE_ID', 'TRAVEL_PREVIEW_BLOB_STORE_ID', 'VERCEL_OIDC_TOKEN'):
            for value in (None, '', '   '):
                env = self.local_env()
                if value is None:
                    env.pop(variable)
                else:
                    env[variable] = value
                env.update(BLOB_READ_WRITE_TOKEN='synthetic-default',
                           TRAVEL_PREVIEW_BLOB_TOKEN='synthetic-legacy',
                           VERCEL_BLOB_READ_WRITE_TOKEN='synthetic-other')
                with self.subTest(variable=variable, value=value):
                    self.reject(env, publisher=True)
        for store in ('production', 'store_', 'store_other'):
            env = self.local_env()
            env['BLOB_STORE_ID'] = store
            self.reject(env, publisher=True)
        env = self.local_env()
        env.update(BLOB_STORE_ID='store_', TRAVEL_PREVIEW_BLOB_STORE_ID='store_')
        self.reject(env, publisher=True)

    def test_local_publisher_rejects_hosted_and_request_contexts(self):
        for changes in (dict(VERCEL_ENV='production'), dict(VERCEL_ENV='preview'),
                        dict(VERCEL='1'), dict(VERCEL_ENV='development', VERCEL='1'),
                        dict(VERCEL_TARGET_ENV='production')):
            self.reject(self.local_env(**changes), publisher=True)
        for headers in ({}, self.headers):
            self.reject(self.local_env(), publisher=True, headers=headers)

    def test_local_oidc_publication_with_actual_sdk_and_failure_boundaries(self):
        from test_forecasts import CITY, RECORDS
        from test_live import NOW, forecast
        from test_history import month_data
        from web.forecasts import Cache
        from web.history import MemoryStore, Library
        from web.publication import prepare, publish

        source = MemoryStore()
        clock = lambda: NOW
        Cache(source, clock).prefetch(RECORDS, lambda *a: forecast(NOW))
        Library(source, clock).publish(CITY, '2025-10', month_data('2025-10'))
        scope = 'preview/s2-test'
        manifest, objects = prepare(source, RECORDS, 'berlin', '2025-10', scope, clock)
        pointer = scope+'/current.json'
        client = self.http.Client
        for failure in (None, 'unauthorized', 'forbidden', 'upload', 'readback', 'pointer'):
            stored = {pointer: b'previous-pointer'}
            calls = []
            def respond(request):
                calls.append(request)
                if failure in ('unauthorized', 'forbidden'):
                    return self.http.Response(401 if failure == 'unauthorized' else 403,
                        json=dict(error=dict(code='forbidden', message='synthetic-cli-oidc')))
                if request.method == 'PUT':
                    name = request.url.params['pathname']
                    if failure == 'upload' or (failure == 'pointer' and name == pointer):
                        return self.http.Response(500, json=dict(error=dict(code='internal_error',
                            message='synthetic-cli-oidc')))
                    stored[name] = request.content
                    url = 'https://trial.private.blob.vercel-storage.com/'+name
                    return self.http.Response(200, json=dict(url=url, downloadUrl=url+'?download=1',
                        pathname=name, contentType='application/octet-stream',
                        contentDisposition='attachment', etag='test'))
                name = request.url.path.lstrip('/')
                if name not in stored:
                    return self.http.Response(404)
                body = b'corrupt' if failure == 'readback' else stored[name]
                return self.http.Response(200, content=body)

            with self.subTest(failure=failure), patch.dict('os.environ', self.local_env(
                    VERCEL_ENV='development', BLOB_READ_WRITE_TOKEN='synthetic-ignored',
                    TRAVEL_PREVIEW_BLOB_TOKEN='synthetic-ignored'), clear=True), patch(
                    'vercel.api.session', side_effect=lambda **kw: self.session(
                        service_options=kw['service_options'],
                        httpx_client_factory=lambda: client(transport=self.http.MockTransport(respond)))):
                with blob_session(scope, publisher=True) as publisher:
                    if failure:
                        with self.assertRaises((OSError, ValueError)) as error:
                            publish(publisher, manifest, objects, clock)
                        self.assertNotIn('synthetic-cli-oidc', str(error.exception))
                        self.assertEqual(stored[pointer], b'previous-pointer')
                    else:
                        version = publish(publisher, manifest, objects, clock)
                        self.assertIn(version.encode(), stored[pointer])
                        self.assertEqual(publisher.stats['writes'], 5)
                        self.assertEqual(publisher.stats['reads'], 8)
                self.assertTrue(calls)
                for request in calls:
                    self.assertEqual(request.headers['authorization'], 'Bearer synthetic-cli-oidc')
                    self.assertIn(request.url.host, ('vercel.com', 'trial.private.blob.vercel-storage.com'))
                puts = [r for r in calls if r.method == 'PUT']
                for request in puts:
                    self.assertEqual(request.headers['x-vercel-blob-access'], 'private')
                    self.assertEqual(request.headers['x-add-random-suffix'], '0')
                    self.assertEqual(request.headers['x-allow-overwrite'],
                                     '1' if request.url.params['pathname'] == pointer else '0')
                if failure in ('unauthorized', 'forbidden'):
                    self.assertEqual(len(calls), 1)  # no retry, no default-credential fallback
                    self.assertEqual(puts, [])
                elif failure not in ('upload', 'readback'):
                    self.assertEqual(puts[-1].url.params['pathname'], pointer)
                    self.assertEqual(calls[-2].method, 'GET')  # readback before pointer switch
                else:
                    self.assertNotIn(pointer, [r.url.params['pathname'] for r in puts])
