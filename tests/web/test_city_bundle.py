"""Mixed real-service paths with synthetic sources; no provider/network access."""
from datetime import timedelta
import json
from pathlib import Path
import tempfile
import unittest

from test_forecasts import RECORDS
from test_history import month_data
from test_live import NOW, forecast
from test_readonly import GetOnly
from web.bundle_data import prepare
from web.fixtures import window
from web.forecasts import Cache, key as forecast_key
from web.history import Library, MemoryStore, months, windows, key as history_key
from web.live import location
from web.readonly import service, prepared_service


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
