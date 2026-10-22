"""Mixed real-service paths with synthetic sources; no provider/network access."""
from datetime import timedelta
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import urlopen

from test_forecasts import RECORDS
from test_history import month_data
from test_live import NOW, forecast
from test_readonly import GetOnly
from web.bundle_data import prepare
from web.fixtures import window
from web.forecasts import Cache, key as forecast_key
from web.history import Library, MemoryStore, months, windows, key as history_key
from web.live import HistoryIncomplete, location
from web.readonly import service, prepared_service
from web.server import Handler


class CityBundleTests(unittest.TestCase):
    def setUp(self):
        self.now = NOW
        self.store = MemoryStore()
        self.clock = lambda: self.now
        self.berlin, self.munich = map(location, RECORDS[:2])
        Cache(self.store, self.clock).prefetch(RECORDS[:1], lambda *a: forecast(self.now))
        self.library = Library(self.store, self.clock)
        for city in (self.berlin, self.munich):
            for month in months(windows(self.now.date(), self.now.date()+timedelta(days=29))):
                self.library.publish(city, month, month_data(month))
        self.reader = GetOnly(self.store.objects)
        self.app = service(self.reader, RECORDS, self.clock, independent_cities=True)

    def test_mixed_states_detail_and_rollover(self):
        result = self.app.featured()
        self.assertEqual(len(result['cities']), 10)
        berlin, munich, hamburg = result['cities'][:3]
        self.assertEqual(berlin['mode'], 'forecast')
        self.assertEqual(munich['mode'], 'historical_reference')
        self.assertEqual(munich['view'], 'city')
        self.assertIn('非这趟行程的预报', munich['caveat'])
        self.assertEqual(hamburg['headline'], '数据暂缺')
        self.assertEqual(self.app.city_advice(dict(city_id='munich')), munich)
        self.now += timedelta(days=1)
        new = self.app.featured()
        self.assertEqual(new['cities'][0]['mode'], 'historical_reference')
        self.assertEqual(new['today'], window(self.now)['today'])
        self.assertEqual(new['cities'][0]['start'], new['today'])

    def test_incomplete_corrupt_and_city_io_failure_are_isolated(self):
        needed = months(windows(self.now.date(), self.now.date()+timedelta(days=13)))
        self.reader.objects[history_key(self.munich, needed[0])] = b'corrupt'
        self.reader.objects[forecast_key(self.berlin, self.now.date())] = b'corrupt'
        result = self.app.featured()['cities']
        self.assertEqual(result[0]['mode'], 'historical_reference')
        self.assertEqual(result[1]['mode'], 'unavailable')
        get = self.reader.get
        def fail(name):
            if name == forecast_key(self.berlin, self.now.date()):
                raise OSError('city IO failure')
            return get(name)
        self.reader.get = fail
        self.assertEqual(self.app.featured()['cities'][0]['mode'], 'historical_reference')

    def test_export_is_validated_readonly_and_contains_no_controls(self):
        self.store.put('control/private.json', b'do not export')
        with tempfile.TemporaryDirectory(dir=Path(__file__).parents[2]) as root:
            target = Path(root)/'bundle'
            prepare(RECORDS, self.reader, self.reader, target, self.clock)
            before = {p.relative_to(target): p.read_bytes() for p in target.rglob('*') if p.is_file()}
            app = prepared_service(target, self.clock)
            self.assertEqual(app.featured()['cities'][1]['mode'], 'historical_reference')
            self.assertFalse(any('control' in str(p) or '.lock' in str(p) for p in before))
            self.assertEqual(before, {p.relative_to(target): p.read_bytes() for p in target.rglob('*') if p.is_file()})
            with self.assertRaises(ValueError):
                prepare(RECORDS, self.reader, self.reader, target, self.clock)

    def test_selected_forecast_cache_reuses_validated_source(self):
        calls = []
        cache = Cache(self.store, self.clock)
        stats = cache.prefetch(RECORDS[:1], lambda *a: calls.append(a))
        self.assertEqual(stats['hits'], 1)
        self.assertEqual(calls, [])
        with self.assertRaises(ValueError):
            cache.prefetch([RECORDS[0], RECORDS[0]])

    def test_local_selected_city_needs_no_whole_publication_or_provider(self):
        from web.live import Service
        from test_readonly import forbidden
        app = Service(forbidden, self.clock, featured_records=RECORDS,
                      forecast_cache=Cache(self.reader, self.clock, read_only=True),
                      history=Library(self.reader, self.clock, read_only=True))
        from web.forecasts import manifest_key
        self.reader.objects.pop(manifest_key(self.now.date()), None)
        self.assertEqual(app.featured()['cities'][0]['mode'], 'forecast')
        self.assertEqual(app.featured()['cities'][1]['mode'], 'historical_reference')

    def trip_params(self, city='munich', preference='normal', first=2, last=4):
        return dict(view='trip', city_id=city, preference=preference,
                    start=str(self.now.date()+timedelta(days=first)),
                    end=str(self.now.date()+timedelta(days=last)))

    def test_personal_history_fallback_preserves_dates_and_preference(self):
        guidance = []
        for preference in ('cold', 'normal', 'hot'):
            p = self.trip_params(preference=preference)
            result = self.app.advice(p)
            self.assertEqual(result['mode'], 'historical_reference')
            self.assertEqual(result['city']['id'], p['city_id'])
            for field in ('start', 'end', 'preference', 'view'):
                self.assertEqual(result[field], p[field])
            self.assertIn('非这趟行程的预报', result['caveat'])
            self.assertIn('ERA5', result['source'])
            self.assertFalse(result['fixture'])
            guidance.append(result['packing_copy']['guidance'])
        self.assertNotEqual(guidance[0], guidance[1])
        self.assertNotEqual(guidance[1], guidance[2])
        # The pre-existing beyond-forecast historical path remains whole-trip.
        self.assertEqual(self.app.advice(self.trip_params(first=12, last=18))['mode'],
                         'historical_reference')

    def test_personal_forecast_priority_expiry_and_incomplete_history(self):
        p = self.trip_params(city='berlin', preference='hot')
        result = self.app.advice(p)
        self.assertEqual(result['mode'], 'forecast')
        self.assertEqual(result['preference'], 'hot')
        self.now += timedelta(days=1)
        result = self.app.advice(p)
        self.assertEqual(result['mode'], 'historical_reference')
        self.assertEqual((result['start'], result['end']), (p['start'], p['end']))
        self.assertEqual(result['preference'], 'hot')
        needed = months(windows(self.now.date()+timedelta(days=2),
                                self.now.date()+timedelta(days=4)))
        del self.reader.objects[history_key(self.munich, needed[0])]
        with self.assertRaises(HistoryIncomplete):
            self.app.advice(self.trip_params())

    def test_personal_fallback_http_forecast_history_expiry_and_missing(self):
        app = self.app
        class TestHandler(Handler):
            service = app
            allow_fixtures = False
        server = ThreadingHTTPServer(('127.0.0.1', 0), TestHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        def request(p):
            url = 'http://127.0.0.1:' + str(server.server_port) + '/api/advice?' + urlencode(p)
            try:
                with urlopen(url, timeout=2) as response:
                    return response.status, json.load(response)
            except HTTPError as exc:
                return exc.code, json.load(exc)
        try:
            for preference in ('cold', 'normal', 'hot'):
                p = self.trip_params(preference=preference)
                status, result = request(p)
                self.assertEqual(status, 200)
                self.assertEqual(result['mode'], 'historical_reference')
                self.assertEqual(result['city']['id'], 'munich')
                for field in ('start', 'end', 'preference'):
                    self.assertEqual(result[field], p[field])
            p = self.trip_params(city='berlin')
            self.assertEqual(request(p)[1]['mode'], 'forecast')
            self.now += timedelta(days=1)
            self.assertEqual(request(p)[1]['mode'], 'historical_reference')
            needed = months(windows(self.now.date(), self.now.date()+timedelta(days=13)))
            self.reader.objects[history_key(self.munich, needed[0])] = b'corrupt'
            status, result = request(self.trip_params())
            self.assertEqual(status, 503)
            self.assertEqual(result['code'], 'history_incomplete')
            self.assertNotIn('headline', result)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
