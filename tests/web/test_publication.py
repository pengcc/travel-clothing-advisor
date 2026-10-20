"""S2 synthetic-only publication and request consistency; never cloud writes."""
from contextlib import contextmanager
from copy import deepcopy
from datetime import timedelta
import io
import json
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.request import urlopen
from urllib.error import HTTPError

from test_forecasts import CITY, RECORDS
from test_live import NOW, forecast
from test_history import month_data
from web.forecasts import Cache, key, pack, unpack
from web.history import MemoryStore, Library, encode
from web.live import Unavailable
from web.publication import (prepare, publish, announce, published_service, load_version,
                             sha, namespace, Snapshot, LIMIT)
from web.blob_store import BlobReader, BlobPublisher
from web.publish_preview import main, publisher_lock
from web.server import ThreadingHTTPServer
from api.index import handler

SCOPE = 'preview/s2-test'
MONTH = '2025-10'


class Remote:
    """Models whole-object puts, failed uploads and explicitly stale CDN reads."""
    def __init__(self):
        self.objects, self.reads, self.writes = {}, [], []
        self.fail, self.stale = None, None

    def get(self, name):
        self.reads.append(name)
        if self.stale is not None and name.endswith('/current.json'):
            return self.stale
        return self.objects.get(name)

    def put(self, name, raw, *, overwrite):
        self.writes.append(name)
        if self.fail and self.fail in name:
            raise OSError('Simulated interrupted publication')
        if name in self.objects and not overwrite:
            raise ValueError('Immutable collision')
        self.objects[name] = raw


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.now = NOW
        self.clock = lambda: self.now
        self.source = MemoryStore()
        Cache(self.source, self.clock).prefetch(RECORDS, lambda *a: forecast(NOW))
        Library(self.source, self.clock).publish(CITY, MONTH, month_data(MONTH, value=14))
        self.manifest, self.objects = prepare(self.source, RECORDS, 'berlin', MONTH, SCOPE, self.clock)
        self.remote = Remote()
        self.params = dict(view='trip', city_id='berlin', start=str(NOW.date()),
                           end=str(NOW.date()+timedelta(days=13)), preference='normal')

    def second(self):
        objects = dict(self.objects)
        name = key(CITY, NOW.date())
        body = unpack(objects[name])
        body['response']['hourly']['temperature_2m'] = [0]*len(body['response']['hourly']['time'])
        objects[name] = pack(body)
        manifest = deepcopy(self.manifest)
        manifest['objects'][name] = dict(sha256=sha(objects[name]), bytes=len(objects[name]))
        return manifest, objects

    def test_versions_pin_stale_pointer_and_rollback(self):
        first = publish(self.remote, self.manifest, self.objects, self.clock)
        pointer = self.remote.get(SCOPE+'/current.json')
        pinned = published_service(self.remote, SCOPE, self.clock)
        old = pinned.advice(self.params)
        second = publish(self.remote, *self.second(), self.clock)
        self.assertNotEqual(first, second)
        fresh = published_service(self.remote, SCOPE, self.clock)
        self.assertEqual(fresh.forecasts.store.version, second)
        self.assertNotEqual(fresh.advice(self.params)['headline'], old['headline'])
        self.assertEqual(pinned.advice(self.params)['headline'], old['headline'])
        self.remote.stale = pointer
        stale = published_service(self.remote, SCOPE, self.clock)
        self.assertEqual(stale.forecasts.store.version, first)
        self.assertEqual(stale.advice(self.params)['headline'], old['headline'])
        self.remote.stale = None
        announce(self.remote, SCOPE, first, self.clock)
        self.assertEqual(published_service(self.remote, SCOPE, self.clock).forecasts.store.version, first)
        # One sample cannot silently weaken complete-ten or five-year contracts.
        with self.assertRaises(Unavailable):
            fresh.featured()
        with self.assertRaises(Unavailable):
            fresh.advice(dict(self.params, start='2026-11-02', end='2026-11-05'))
        self.remote.reads.clear()
        published_service(self.remote, SCOPE, self.clock)
        self.assertEqual(len(self.remote.reads), 5)

    def test_failed_partial_upload_readback_and_resume(self):
        first = publish(self.remote, self.manifest, self.objects, self.clock)
        old = self.remote.objects[SCOPE+'/current.json']
        self.remote.fail = 'history/'
        with self.assertRaises(OSError):
            publish(self.remote, *self.second(), self.clock)
        self.assertEqual(self.remote.objects[SCOPE+'/current.json'], old)
        self.assertEqual(published_service(self.remote, SCOPE, self.clock).forecasts.store.version, first)
        self.remote.fail = None
        second = publish(self.remote, *self.second(), self.clock)
        self.assertNotEqual(first, second)
        # Complete resume rewrites only the pointer, never immutable bytes.
        self.remote.writes.clear()
        publish(self.remote, *self.second(), self.clock)
        self.assertEqual(self.remote.writes, [SCOPE+'/current.json'])
        manifest, objects = self.second()
        corrupt = Remote()
        original = corrupt.put
        def damage(name, raw, **kwargs):
            original(name, b'corrupt' if 'history/' in name else raw, **kwargs)
        corrupt.put = damage
        with self.assertRaises(ValueError):
            publish(corrupt, manifest, objects, self.clock)
        self.assertNotIn(SCOPE+'/current.json', corrupt.objects)

    def test_invalid_input_has_zero_writes_and_corrupt_remote_fails_closed(self):
        for change in ('hash', 'inner', 'identity', 'manifest', 'size', 'archive'):
            manifest, objects = deepcopy(self.manifest), dict(self.objects)
            name = key(CITY, NOW.date())
            if change == 'archive':
                name = next(n for n in objects if n.endswith('.gz'))
                objects[name] = b'invalid gzip'
                manifest['objects'][name] = dict(bytes=len(objects[name]), sha256=sha(objects[name]))
            elif change == 'manifest':
                manifest['namespace'] = 'production/main'
            elif change == 'hash':
                objects[name] = b'wrong'
            elif change == 'size':
                objects[name] = b'x'*(LIMIT+1)
            else:
                body = unpack(objects[name])
                if change == 'inner':
                    body['response']['hourly']['time'].pop()
                else:
                    body['identity']['coordinates'] = [0, 0]
                objects[name] = pack(body)
                manifest['objects'][name] = dict(bytes=len(objects[name]), sha256=sha(objects[name]))
            with self.subTest(change=change), self.assertRaises((ValueError, Unavailable)):
                publish(self.remote, manifest, objects, self.clock)
            self.assertEqual(self.remote.writes, [])
        version = publish(self.remote, self.manifest, self.objects, self.clock)
        path = f'{SCOPE}/versions/{version}/'+key(CITY, NOW.date())
        raw = self.remote.objects.pop(path)
        with self.assertRaises(Unavailable):
            published_service(self.remote, SCOPE, self.clock)
        self.remote.objects[path] = b'corrupt'
        with self.assertRaises(Unavailable):
            published_service(self.remote, SCOPE, self.clock)
        self.remote.objects[path] = raw
        self.now += timedelta(days=1)
        with self.assertRaises(Unavailable):
            published_service(self.remote, SCOPE, self.clock)
        with self.assertRaises(ValueError):
            announce(self.remote, SCOPE, version, self.clock)

    def test_pointer_manifest_namespace_and_midread_switch(self):
        version = publish(self.remote, self.manifest, self.objects, self.clock)
        pointer = self.remote.objects[SCOPE+'/current.json']
        for bad in (b'{}', b'{"schema":1,"schema":1}', encode(dict(schema=1, namespace=SCOPE, version='../other'))):
            self.remote.objects[SCOPE+'/current.json'] = bad
            with self.assertRaises(Unavailable):
                published_service(self.remote, SCOPE, self.clock)
        self.remote.objects[SCOPE+'/current.json'] = pointer
        with self.assertRaises(Unavailable):
            published_service(self.remote, 'preview/other', self.clock)
        for scope in ('production/main', 'preview/../production', 'preview/a/extra', 'https://evil'):
            with self.assertRaises(ValueError):
                namespace(scope)
        # Change pointer after it was read: this request still sees one full v1.
        original = self.remote.get
        manifest2, objects2 = self.second()
        def switch(name):
            raw = original(name)
            if name.endswith('/current.json'):
                self.remote.get = original
                publish(self.remote, manifest2, objects2, self.clock)
            return raw
        self.remote.get = switch
        self.assertEqual(published_service(self.remote, SCOPE, self.clock).forecasts.store.version, version)

    def test_http_same_server_observes_new_version_and_production_rejects(self):
        first = publish(self.remote, self.manifest, self.objects, self.clock)
        @contextmanager
        def connection(scope):
            self.assertEqual(scope, SCOPE)
            yield self.remote
        original = published_service
        with patch.dict('os.environ', dict(TRAVEL_PREVIEW_NAMESPACE=SCOPE, VERCEL_ENV='preview')), \
             patch('web.blob_store.blob_session', connection), \
             patch('web.publication.published_service', side_effect=lambda r,s: original(r,s,self.clock)):
            server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = 'http://127.0.0.1:'+str(server.server_port)
            def read(path):
                try:
                    with urlopen(base+path) as response:
                        self.assertEqual(response.headers['Cache-Control'], 'no-store')
                        return response.status, json.load(response)
                except HTTPError as exc:
                    return exc.code, json.load(exc)
            try:
                path = '/api/advice?view=trip&city_id=berlin&start=2026-10-16&end=2026-10-29&preference=normal'
                status, old = read(path)
                self.assertEqual(status, 200)
                self.assertEqual(old['dataset_version'], first)
                second = publish(self.remote, *self.second(), self.clock)
                status, new = read(path)
                self.assertEqual(status, 200)
                self.assertEqual(new['dataset_version'], second)
                self.assertNotEqual(old['headline'], new['headline'])
                self.assertEqual(read('/api/featured')[0], 503)
                self.assertEqual(read('/api/city?city_id=123456')[0], 503)
                with patch.dict('os.environ', dict(VERCEL_ENV='production')):
                    self.assertEqual(read(path)[0], 503)
            finally:
                server.shutdown(); server.server_close(); thread.join()

    def test_cli_dry_run_and_local_publisher_exclusion(self):
        with tempfile.TemporaryDirectory() as root:
            from pathlib import Path
            for name, raw in self.objects.items():
                p = Path(root)/name
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(raw)
            with patch('web.publish_preview.prepare', return_value=(self.manifest, self.objects)), \
                 patch('web.blob_store.blob_session', side_effect=AssertionError('network')), \
                 patch('sys.stdout', new_callable=io.StringIO) as out:
                self.assertEqual(main(['--source',root,'--namespace',SCOPE,'--city-id','berlin','--month',MONTH]),0)
                self.assertEqual(json.loads(out.getvalue())['mode'], 'dry_run')
            lock = Path(root)/'lock'
            with publisher_lock(lock):
                with self.assertRaises(ValueError):
                    with publisher_lock(lock):
                        pass


class SDKContractTests(unittest.TestCase):
    def test_trial_config_required_without_default_credential_fallback(self):
        try:
            import httpx2
        except ImportError:
            self.skipTest('Optional SDK environment required')
        from web.blob_store import blob_session
        with patch.dict('os.environ', {}, clear=True), \
             patch.object(httpx2, 'Client', side_effect=AssertionError('network')):
            with self.assertRaises(OSError):
                with blob_session(SCOPE):
                    self.fail('Missing dedicated config accepted')

    def test_actual_sdk_mock_transport_private_get_errors_size_and_put_options(self):
        try:
            import httpx2
            from vercel.blob import sync as sdk
            from vercel.api import session
        except ImportError:
            self.skipTest('Optional SDK; run with .local-tools/s2-venv/bin/python')
        # Fabricated SDK credentials, not a real account or token; never sent.
        credentials = lambda: sdk.BlobCredentials(token='synthetic', store_id='trial', kind=sdk.CredentialKind.OIDC)
        calls = []
        def respond(request):
            calls.append(request)
            if request.method == 'PUT':
                name = request.url.params['pathname']
                return httpx2.Response(200, json=dict(url='https://trial.private.blob.vercel-storage.com/'+name,
                    downloadUrl='https://trial.private.blob.vercel-storage.com/'+name+'?download=1', pathname=name,
                    contentType='application/octet-stream', contentDisposition='attachment', etag='test'))
            if 'denied' in request.url.path:
                return httpx2.Response(403, json=dict(error=dict(code='forbidden',message='denied')))
            if 'missing' in request.url.path:
                return httpx2.Response(404)
            return httpx2.Response(200, content=b'x'*(LIMIT+1) if 'large' in request.url.path else b'ok')
        with session(service_options=[sdk.SyncBlobServiceOptions(credentials_factory=credentials)],
                     httpx_client_factory=lambda: httpx2.Client(transport=httpx2.MockTransport(respond))):
            reader = BlobReader(sdk, SCOPE)
            self.assertFalse(hasattr(reader, 'put'))
            self.assertFalse(hasattr(reader, 'exclusive'))
            self.assertEqual(reader.get(SCOPE+'/sample'), b'ok')
            self.assertIn('.private.blob.vercel-storage.com', str(calls[-1].url))
            self.assertIsNone(reader.get(SCOPE+'/missing'))
            for name in ('denied','large'):
                with self.assertRaises(OSError):
                    reader.get(SCOPE+'/'+name)
            with self.assertRaises(ValueError):
                reader.get('production/sample')
            writer = BlobPublisher(sdk, SCOPE)
            writer.put(SCOPE+'/immutable', b'raw', overwrite=False)
            self.assertEqual(calls[-1].headers['x-allow-overwrite'], '0')
            self.assertEqual(calls[-1].headers['x-cache-control-max-age'], '60')
            writer.put(SCOPE+'/current.json', b'{}', overwrite=True)
            self.assertEqual(calls[-1].headers['x-allow-overwrite'], '1')
            self.assertEqual(calls[-1].headers['x-vercel-blob-access'], 'private')
            self.assertEqual(calls[-1].headers['x-add-random-suffix'], '0')


if __name__ == '__main__':
    unittest.main()
