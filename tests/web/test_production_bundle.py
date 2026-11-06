"""Actual Production handler with offline synthetic immutable bundles."""
from datetime import timedelta
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import urlopen

from api.index import handler
from test_forecasts import RECORDS
from test_history import month_data
from test_live import NOW, forecast
from test_readonly import forbidden
from web.bundle_data import prepare
from web.forecasts import Cache, key as forecast_key
from web.history import Library, MemoryStore, months, windows
from web.live import location
from web.readonly import prepared_service


class ProductionBundleTests(unittest.TestCase):
    def setUp(self):
        self.now = NOW
        self.clock = lambda: self.now
        self.tmp = tempfile.TemporaryDirectory(dir=Path(__file__).parents[2])
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'bundle'
        store = MemoryStore()
        Cache(store, self.clock).prefetch(RECORDS, lambda *a: forecast(self.now))
        library = Library(store, self.clock)
        for month in months(windows(NOW.date(), NOW.date()+timedelta(days=29))):
            library.publish(location(RECORDS[0]), month, month_data(month))
        prepare(RECORDS, store, store, self.root, self.clock)
        for target, options in [
            ('api.index.DATASET', dict(new=self.root)),
            ('api.index.prepared_service', dict(side_effect=lambda root: prepared_service(root, self.clock))),
            ('api.index.handler.service', dict(new=prepared_service(self.root, self.clock))),
            ('web.live.fetch_json', dict(new=forbidden)),
            ('web.readonly.no_provider', dict(new=forbidden)),
            ('web.history.DirectoryStore.put', dict(new=forbidden)),
            ('web.history.DirectoryStore.exclusive', dict(new=forbidden)),
        ]:
            patcher = patch(target, **options)
            patcher.start()
            self.addCleanup(patcher.stop)
        env = patch.dict('os.environ', {'VERCEL_ENV': 'production'}, clear=True)
        env.start()
        self.addCleanup(env.stop)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop)

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def get(self, path):
        try:
            response = urlopen('http://127.0.0.1:' + str(self.server.server_port) + path, timeout=3)
        except HTTPError as exc:
            response = exc
        with response:
            raw = response.read()
            self.assertEqual(response.headers['Cache-Control'], 'no-store')
            self.assertEqual(response.headers['X-Content-Type-Options'], 'nosniff')
            return response.status, json.loads(raw) if 'application/json' in response.headers['Content-Type'] else raw

    def files(self):
        return {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}

    def test_fresh_ten_cities_actual_handler_and_readonly(self):
        before = self.files()
        self.assertEqual(self.get('/api/context')[1]['data_delivery'], 'manual_git_bundle')
        with patch('pathlib.Path.write_bytes', new=forbidden), patch('pathlib.Path.write_text', new=forbidden):
            status, snapshot = self.get('/api/featured')
        self.assertEqual(status, 200)
        self.assertEqual(len(snapshot['cities']), 10)
        for card in snapshot['cities']:
            self.assertEqual(card['mode'], 'forecast')
            self.assertFalse(card['fixture'])
            status, detail = self.get('/api/advice?view=city&city_id=' + card['city']['id'])
            self.assertEqual((status, detail), (200, card))
        for preference in ('cold', 'normal', 'hot'):
            status, data = self.get('/api/advice?view=trip&city_id=berlin&start=2026-10-16&end=2026-10-18&preference=' + preference)
            self.assertEqual((status, data['preference'], data['mode']), (200, preference, 'forecast'))
        self.assertEqual(self.get('/api/cities?q=unknown')[1]['cities'], [])
        self.assertEqual(self.get('/api/city?city_id=123456')[0], 503)
        self.assertEqual(self.get('/api/featured?fixture=default')[0], 400)
        self.assertEqual(self.get('/api/advice?view=trip&city_id=berlin&start=2026-10-15&end=2026-10-18&preference=normal')[0], 400)
        self.assertEqual(before, self.files())

    def test_production_collision_precedes_remote_reader(self):
        for config in ({'TRAVEL_P1_READER': 'true'}, {'TRAVEL_PREVIEW_NAMESPACE': 'test'},
                       {'TRAVEL_PREVIEW_NAMESPACE': ''}, {'TRAVEL_P1_READER': 'true', 'TRAVEL_PREVIEW_NAMESPACE': 'test'}):
            with self.subTest(config=config), patch.dict('os.environ', config), patch('web.lifecycle.production_service', new=forbidden), patch('web.blob_store.blob_session', new=forbidden):
                status, error = self.get('/api/featured')
                self.assertEqual(status, 503)
                self.assertIn('配置冲突', error['error'])
                for path in ('/', '/static/app.js', '/api/context'):
                    self.assertEqual(self.get(path)[0], 200)

    def test_missing_and_corrupt_metadata_fail_closed_but_shell_works(self):
        path = self.root / 'cities.json'
        for raw in (None, b'bad', b'{}', b'[]', json.dumps(RECORDS[:9]).encode(),
                    json.dumps([RECORDS[0]] * 10).encode()):
            if raw is None:
                path.unlink()
            else:
                path.write_bytes(raw)
            self.assertEqual(self.get('/api/featured')[0], 503)
            for route in ('/', '/static/style.css', '/api/context'):
                self.assertEqual(self.get(route)[0], 200)

    def test_expiry_isolation_history_and_real_missing_503(self):
        (self.root / forecast_key(location(RECORDS[1]), NOW.date())).write_bytes(b'corrupt')
        status, snapshot = self.get('/api/featured')
        self.assertEqual(status, 200)
        self.assertEqual(snapshot['cities'][0]['mode'], 'forecast')
        self.assertEqual(snapshot['cities'][1]['mode'], 'unavailable')
        self.now += timedelta(days=1)
        snapshot = self.get('/api/featured')[1]
        self.assertEqual(snapshot['cities'][0]['mode'], 'historical_reference')
        self.assertTrue(all(c['mode'] == 'unavailable' for c in snapshot['cities'][1:]))
        status, data = self.get('/api/advice?view=city&city_id=berlin')
        self.assertEqual((status, data['mode']), (200, 'historical_reference'))
        self.assertEqual(self.get('/api/advice?view=city&city_id=hamburg')[0], 503)
        # Delete history only inside this test's temporary bundle.
        for path in self.root.glob('**/*'):
            if path.is_file() and 'history' in path.relative_to(self.root).parts:
                path.unlink()
        self.assertEqual(self.get('/api/advice?view=city&city_id=berlin')[0], 503)

    # ---- 穿衣小伙伴 (Issue #101) through the actual Production handler ----
    def test_pal_pages_and_api_actual_handler(self):
        for path in ('/pal/berlin', '/pal/berlin/'):
            status, page = self.get(path)
            self.assertEqual(status, 200)
            self.assertIn('穿衣小伙伴'.encode(), page)
        status, data = self.get('/api/pal')
        self.assertEqual(status, 200)
        self.assertEqual(data['city']['id'], 'berlin')
        self.assertEqual(len(data['days']), 7)
        self.assertFalse(data['fixture'])
        self.assertFalse(data['stale'])
        for day in data['days']:
            for slot in day['slots']:
                self.assertEqual(slot['level'] is None, slot['past'])
        self.assertEqual(self.get('/api/pal?city_id=berlin')[0], 400)
        self.assertEqual(self.get('/api/pal?fixture=default')[0], 400)
        self.assertEqual(self.get('/pal/nowhere')[0], 404)
        self.assertEqual(self.get('/pal/freiburg')[0], 404)        # only the ten featured cities have pages
        self.assertEqual(self.get('/pal/berlin/extra')[0], 404)
        self.assertEqual(self.get('/static/pal/missing.js')[0], 404)

    def test_pal_all_ten_cities_pages_manifests_and_api(self):
        from web.server import PAL_CITIES
        for city_id, city in PAL_CITIES.items():
            for path in (f'/pal/{city_id}', f'/pal/{city_id}/'):
                status, page = self.get(path)
                self.assertEqual(status, 200, path)
                self.assertIn(f'穿衣小伙伴 · {city["zh"]}'.encode(), page)
                self.assertIn(f'data-city="{city_id}"'.encode(), page)
            status, manifest = self.get(f'/pal/{city_id}/manifest.webmanifest')
            self.assertEqual(status, 200)
            manifest = json.loads(manifest)
            self.assertEqual((manifest['start_url'], manifest['scope']), (f'/pal/{city_id}', '/pal/'))
            status, data = self.get(f'/api/pal?city={city_id}')
            self.assertEqual(status, 200, city_id)
            self.assertEqual((data['city']['id'], data['stale'], len(data['days'])), (city_id, False, 7))
        for path in ('/pal', '/pal/'):
            status, page = self.get(path)
            self.assertEqual(status, 200)
            self.assertEqual(page.count(b'class="city"'), 10)
        self.assertEqual(self.get('/api/pal')[1]['city']['id'], 'berlin')          # no parameter still means berlin

    def test_pal_city_parameter_is_strict(self):
        for query in ('?city=', '?city=nowhere', '?city=freiburg', '?city=Berlin', '?city=berlin&city=munich',
                      '?city=berlin&x=1', '?city_id=munich', '?x=1', '?city=berlin%00'):
            status, data = self.get('/api/pal' + query)
            self.assertEqual(status, 400, query)
            self.assertEqual(data['code'], 'invalid_request')

    def test_pal_other_city_is_503_when_its_data_is_missing_or_old(self):
        (self.root / forecast_key(location(RECORDS[1]), NOW.date())).write_bytes(b'corrupt')
        status, data = self.get('/api/pal?city=munich')
        self.assertEqual((status, data['code']), (503, 'temporarily_unavailable'))
        self.assertEqual(self.get('/api/pal?city=berlin')[0], 200)               # other cities unaffected
        self.now += timedelta(days=1)                                              # berlin: previous-day snapshot
        self.assertEqual(self.get('/api/pal?city=berlin')[1]['stale'], True)

    def test_pal_uses_previous_days_snapshot_then_gives_up(self):
        self.now += timedelta(days=1)              # tomorrow 10:30; today's snapshot is 24 h old
        status, data = self.get('/api/pal')
        self.assertEqual((status, data['stale']), (200, True))
        self.assertEqual(data['days'][0]['date'], self.now.date().isoformat())
        self.now += timedelta(days=1, hours=1)     # snapshot is now 49 h old: too old
        status, data = self.get('/api/pal')
        self.assertEqual(status, 503)
        self.assertEqual(data['code'], 'temporarily_unavailable')
        # The homepage reference still behaves as before (history only); pal never falls back to it.
        self.assertEqual(self.get('/api/advice?view=city&city_id=berlin')[1]['mode'], 'historical_reference')

    def test_pal_missing_and_corrupt_data_is_503_not_400(self):
        (self.root / forecast_key(location(RECORDS[0]), NOW.date())).write_bytes(b'corrupt')
        status, data = self.get('/api/pal')
        self.assertEqual(status, 503)
        self.assertEqual(data['code'], 'temporarily_unavailable')
        for route in ('/pal/berlin', '/api/context'):
            self.assertEqual(self.get(route)[0], 200)

    def test_pal_legacy_mode_is_503_and_never_downloads(self):
        from web.readonly import service as legacy_service
        from web.history import MemoryStore as Memory
        legacy = legacy_service(Memory(), RECORDS, self.clock)      # independent_cities=False
        with patch('api.index.prepared_service', side_effect=lambda root: legacy):
            status, data = self.get('/api/pal')
        self.assertEqual(status, 503)
        self.assertIn('暂不提供', data['error'])

    def test_pal_static_files_are_exactly_registered_and_icons_opaque(self):
        import struct
        from web.server import STATIC, ROOT
        registered = {path for path in STATIC if path.startswith('/static/pal/')}
        on_disk = {'/static/pal/' + p.relative_to(ROOT / 'static/pal').as_posix() for p in (ROOT / 'static/pal').rglob('*') if p.is_file()}
        self.assertEqual(registered, on_disk)
        self.assertEqual(STATIC['/static/pal/manifest.webmanifest'][1], 'application/manifest+json')
        for path in sorted(registered):
            status, body = self.get(path)
            self.assertEqual(status, 200, path)
        manifest = json.loads(self.get('/static/pal/manifest.webmanifest')[1])
        self.assertEqual((manifest['display'], manifest['start_url'], manifest['scope']), ('standalone', '/pal/berlin', '/pal/'))
        for n in range(1, 7):                                         # neutral sprites: transparent PNG, 256x256, no weather pieces to check here
            raw = self.get(f'/static/pal/sprites/warmth-l{n}.png')[1]
            self.assertEqual(raw[:8], b'\x89PNG\r\n\x1a\n')
            width, height, depth, color = struct.unpack('>IIBB', raw[16:26])
            self.assertEqual((width, height, depth, color), (256, 256, 8, 6), n)   # RGBA
        for name, size in (('apple-touch-icon.png', 180), ('icon-192.png', 192)):
            raw = self.get('/static/pal/' + name)[1]
            self.assertEqual(raw[:8], b'\x89PNG\r\n\x1a\n')
            width, height, depth, color = struct.unpack('>IIBB', raw[16:26])
            self.assertEqual((width, height, depth), (size, size, 8), name)
            self.assertIn(color, (0, 2), name)                    # grayscale or RGB: no alpha channel
            self.assertNotIn(b'tRNS', raw, name)
