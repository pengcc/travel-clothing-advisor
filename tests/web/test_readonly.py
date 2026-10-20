"""S1 synthetic-only acceptance: every write/lock/provider access must fail."""
from datetime import date, timedelta
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.request import urlopen
from urllib.error import HTTPError

from test_forecasts import RECORDS, CITY
from test_live import NOW, forecast
from test_history import month_data
from web.forecasts import Cache, key, manifest_key, unpack, pack
from web.history import Library, MemoryStore, months, windows, key as history_key
from web.live import Unavailable
from web.readonly import service, ReadOnlyDirectoryStore, prepared_service
from web.server import ThreadingHTTPServer
from api.index import handler


def forbidden(*args, **kwargs):
    raise AssertionError('write, lock or provider called')


class GetOnly:
    def __init__(self, objects):
        self.objects = dict(objects)

    def get(self, name):
        return self.objects.get(name)

    @property
    def put(self):
        forbidden()

    @property
    def exclusive(self):
        forbidden()


class ReadOnlyTests(unittest.TestCase):
    def setUp(self):
        self.now = NOW
        store = MemoryStore()
        Cache(store, lambda: self.now).prefetch(RECORDS, lambda *a: forecast(NOW))
        library = Library(store, lambda: self.now)
        self.start, self.end = date(2026, 11, 2), date(2026, 11, 5)
        self.months = months(windows(self.start, self.end))
        for month in self.months:
            library.publish(CITY, month, month_data(month, value=14))
        self.store = GetOnly(store.objects)
        self.service = service(self.store, RECORDS, lambda: self.now)
        self.service.fetch = forbidden

    def params(self, historical=False):
        return dict(view='trip', city_id='berlin', preference='normal',
                    start=str(self.start) if historical else str(NOW.date()),
                    end=str(self.end) if historical else str(NOW.date()+timedelta(days=13)))

    def test_complete_and_rule_driven_copy(self):
        self.assertEqual(len(self.service.featured()['cities']), 10)
        result = self.service.advice(self.params())
        self.assertFalse(result['fixture'])
        self.assertIn('第8–14天', result['caveat'])
        self.assertTrue(result['packing_copy']['guidance'])
        hist = self.service.advice(self.params(True))
        self.assertEqual(hist['mode'], 'historical_reference')
        self.assertEqual(hist['warmth_indicator_level'], 4)
        self.assertIn('适中外套', hist['headline'])
        self.assertIn('五年', hist['caveat'])
        self.assertFalse(hist['fixture'])
        # An accidentally injected downloader must not activate in read-only mode.
        self.service.history_downloader = type('Worker', (), {'fill_locked': forbidden})()
        self.service.history_max_missing = 100
        del self.store.objects[history_key(CITY, self.months[0])]
        with self.assertRaises(Unavailable):
            self.service.advice(self.params(True))

    def test_city_lookup_search_and_unknown(self):
        self.assertEqual(self.service.resolve('2950159'), self.service.resolve('berlin'))
        for q in ('Berlin', '柏林', 'berlin'):
            self.assertEqual(self.service.cities(q)['cities'][0]['id'], 'berlin')
        self.assertEqual(len(self.service.cities('')['cities']), 10)
        self.assertEqual(self.service.cities('unknown')['cities'], [])
        with self.assertRaises(Unavailable):
            self.service.resolve('123456')
        with self.assertRaises(ValueError):
            service(self.store, [dict(RECORDS[0], country_code='FR')])

    def test_missing_corrupt_forecast_and_whole_manifest(self):
        for mutation in ('missing', 'hash', 'old'):
            with self.subTest(mutation=mutation):
                objkey = key(CITY, NOW.date())
                original = self.store.objects[objkey]
                if mutation == 'missing':
                    del self.store.objects[objkey]
                elif mutation == 'hash':
                    self.store.objects[objkey] = b'{"body":{},"sha256":"bad"}'
                else:
                    body = unpack(original)
                    body['weather_fetched_at'] = (NOW-timedelta(days=1)).isoformat()
                    self.store.objects[objkey] = pack(body)
                with self.assertRaises(Unavailable):
                    self.service.featured()
                with self.assertRaises(Unavailable):
                    self.service.city_advice(dict(view='city', city_id='munich'))
                with self.assertRaises(Unavailable):
                    self.service.advice(self.params())
                self.store.objects[objkey] = original
        self.store.objects[manifest_key(NOW.date())] = pack(dict(format={}, entries=[]))
        with self.assertRaises(Unavailable):
            self.service.featured()

    def test_corrupt_history_and_midnight(self):
        self.store.objects[history_key(CITY, self.months[0])] = b'invalid gzip'
        with self.assertRaises(Unavailable):
            self.service.advice(self.params(True))
        self.now = NOW.replace(hour=23, minute=59)+timedelta(minutes=2)
        with self.assertRaises(Unavailable):
            self.service.featured()
        with self.assertRaises(Unavailable):
            self.service.advice(dict(self.params(), start=str(self.now.date())))
        self.now = NOW
        original = self.store.get
        def rollover(name):
            raw = original(name)
            if name.startswith('forecast/hourly'):
                self.now = NOW+timedelta(days=1)
            return raw
        self.store.get = rollover
        with self.assertRaises(Unavailable):
            self.service.featured()

    def test_directory_is_get_only_and_does_not_create_missing_root(self):
        with tempfile.TemporaryDirectory() as root:
            missing = Path(root)/'absent'
            reader = ReadOnlyDirectoryStore(missing)
            self.assertIsNone(reader.get('x'))
            self.assertFalse(missing.exists())
            self.assertFalse(hasattr(reader, 'put'))
            with self.assertRaises(ValueError):
                reader.get('../outside')
            with self.assertRaises(Unavailable):
                prepared_service(missing)
            self.assertFalse(missing.exists())

    def test_prepared_directory_load_and_missing_manifest(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            for name, data in self.store.objects.items():
                path = root/name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            (root/'cities.json').write_text(json.dumps(RECORDS))
            before = {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*') if p.is_file()}
            prepared = prepared_service(root, lambda: NOW)
            self.assertEqual(len(prepared.featured()['cities']), 10)
            self.assertEqual(prepared.advice(self.params(True))['warmth_indicator_level'], 4)
            after = {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*') if p.is_file()}
            self.assertEqual(before, after)
        del self.store.objects[manifest_key(NOW.date())]
        with self.assertRaises(Unavailable):
            self.service.featured()
        # Personal sources remain independently usable without the manifest.
        self.assertEqual(self.service.advice(self.params())['mode'], 'forecast')

    def test_function_http_shared_link_static_errors_and_no_network(self):
        test_service = self.service
        class TestHandler(handler):
            service = test_service
        with patch('api.index.prepared_service', return_value=test_service), \
             patch('web.live.urlopen', side_effect=forbidden), \
             patch('web.history.urlopen', side_effect=forbidden):
            server = ThreadingHTTPServer(('127.0.0.1', 0), TestHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = 'http://127.0.0.1:'+str(server.server_port)
            def get(path):
                try:
                    with urlopen(base+path) as response:
                        return response.status, response.read()
                except HTTPError as exc:
                    return exc.code, exc.read()
            try:
                for path in ('/', '/static/app.js', '/static/style.css', '/api/cities?q=Berlin',
                             '/api/city?city_id=2950159', '/api/featured',
                             '/api/advice?view=city&city_id=berlin',
                             '/api/advice?view=trip&city_id=berlin&start=2026-11-02&end=2026-11-05&preference=normal'):
                    with self.subTest(path=path):
                        self.assertEqual(get(path)[0], 200)
                self.assertEqual(get('/api/city?city_id=123456')[0], 503)
                self.assertEqual(get('/api/featured?fixture=default')[0], 400)
                del self.store.objects[key(CITY, NOW.date())]
                self.assertEqual(get('/api/featured')[0], 503)
            finally:
                server.shutdown()
                server.server_close()
                thread.join()


if __name__ == '__main__':
    unittest.main()
