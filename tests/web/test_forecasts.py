"""Phase 2C offline acceptance. All city metadata/weather below is synthetic."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from test_live import NOW, Fake, forecast, geo
from web.fixtures import BERLIN, CITIES
from web.live import Service, IDS, FORECAST, GEO, Unavailable, location, parse_hours
from web.forecasts import Cache, MemoryStore, DirectoryStore, FORMAT, LEDGER, key, manifest_key, pack, unpack

# Deliberately synthetic test records, never an operator/live initialization file.
RECORDS = [geo(IDS[c['id']], name=c['name'], admin1=c['state']) for c in CITIES[:10]]
CITY = location(RECORDS[0])


class ForecastTests(unittest.TestCase):
    def setUp(self):
        self.now = NOW
        self.store = MemoryStore()
        self.cache = Cache(self.store, lambda: self.now)
        self.calls = []

    def provider(self, url, params, timeout):
        self.assertEqual(url, FORECAST)
        self.assertTrue(0 < timeout <= 4)
        self.calls.append(params)
        return forecast(self.now)

    def service(self, cache=None):
        def fetch(url, params):
            if url == FORECAST:
                return self.provider(url, params, 4)
            self.geocodes += 1
            return geo(int(params['id']))
        self.geocodes = 0
        return Service(fetch, lambda: self.now, forecast_cache=cache or self.cache)

    def params(self, **kw):
        return dict(dict(view='trip', city_id='berlin', start=self.now.date().isoformat(),
                    end=(self.now.date()+timedelta(days=2)).isoformat(), preference='normal'), **kw)

    def test_ten_city_rerun_and_personal_sharing(self):
        stats = self.cache.prefetch(RECORDS, self.provider)
        self.assertEqual(stats, dict(forecast_attempts=10, geocoding_attempts=0,
                                    hits=0, published=10, failed=0, complete=True))
        self.assertEqual(len(self.calls), 10)
        rerun = self.cache.prefetch(RECORDS, self.provider)
        self.assertEqual((rerun['hits'], rerun['forecast_attempts']), (10, 0))
        service = self.service()
        cards = service.featured()
        self.assertFalse(cards['fixture'])
        self.assertEqual(len(cards['cities']), 10)
        berlin = cards['cities'][0]
        detail = service.city_advice(dict(view='city', city_id='berlin', start='invalid', preference='hot'))
        self.assertEqual(berlin, detail)
        self.assertEqual(detail['preference'], 'normal')
        for pref in ('cold','normal','hot'):
            for n in (0,1,5):
                result = service.advice(self.params(preference=pref,
                    start=(self.now.date()+timedelta(days=n)).isoformat(),
                    end=(self.now.date()+timedelta(days=n+2)).isoformat()))
                for field in ('data_version','weather_fetched_at'):
                    self.assertEqual(result[field], berlin[field])
        self.assertEqual(len(self.calls), 10)
        self.assertEqual(self.geocodes, 9)  # geocoding is not a forecast hit/miss
        for city in cards['cities']:
            self.assertEqual(bool(city['packing_variation_notice']), bool(city['packing_variation_summary']))
            self.assertEqual(city['packing_variation_kind'] is not None, bool(city['packing_variation_summary']))
        for params in self.calls:
            self.assertEqual(params['models'], 'best_match')
            self.assertNotIn('daily', params)

    def test_one_source_restart_reload_and_no_advice_storage(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parents[2]) as root:
            cache = Cache(DirectoryStore(root), lambda: self.now)
            stats = dict(hits=0, forecast_attempts=0, published=0, failed=0)
            with cache.store.exclusive():
                cache.load_locked(CITY, self.now.date(), self.provider, cache.timer()+10, stats)
            self.assertEqual(stats['forecast_attempts'], 1)
            service = self.service(cache)
            first = service.advice(self.params())
            self.assertEqual(len(self.calls), 1)
            self.now += timedelta(minutes=1)
            restarted = self.service(Cache(DirectoryStore(root), lambda: self.now))
            second = restarted.advice(self.params(preference='cold', end='2026-10-20'))
            self.assertEqual(len(self.calls), 1)
            self.assertEqual(first['data_version'], second['data_version'])
            self.assertEqual(first['weather_fetched_at'], second['weather_fetched_at'])
            self.assertNotEqual(first['advice_generated_at'], second['advice_generated_at'])
            for path in Path(root).rglob('*.json'):
                text = path.read_text()
                self.assertNotIn('preference', text)
                self.assertNotIn('headline', text)
            # The already prefetched Berlin source is reused by the ten-city worker.
            cache.prefetch(RECORDS, self.provider)
            self.assertEqual(len(self.calls), 10)
            another = self.service(Cache(DirectoryStore(root), lambda: self.now))
            card = another.featured()['cities'][0]
            detail = another.city_advice(dict(view='city', city_id='berlin'))
            another.featured()  # reload
            self.assertEqual(card, detail)
            self.assertEqual(card['data_version'], first['data_version'])
            self.assertEqual(len(self.calls), 10)

    def test_failure_recovery_never_partial_publication(self):
        attempts = [0]
        def fail(url, params, timeout):
            attempts[0] += 1
            if attempts[0] == 4:
                return dict(error=True)
            return self.provider(url, params, timeout)
        with self.assertRaises(Unavailable):
            self.cache.prefetch(RECORDS, fail)
        self.assertEqual(self.cache.stats['forecast_attempts'], 4)
        self.assertEqual(self.cache.stats['published'], 3)
        self.assertIsNone(self.store.get(manifest_key(self.now.date())))
        service = self.service()
        with self.assertRaises(Unavailable): service.featured()
        with self.assertRaises(Unavailable): service.city_advice(dict(city_id='berlin'))
        # A completed city remains usable for a personal trip despite failed block.
        service.advice(self.params())
        self.assertEqual(len(self.calls), 3)
        with self.assertRaises(Unavailable): self.cache.prefetch(RECORDS, self.provider)
        self.assertEqual(self.cache.stats['forecast_attempts'], 0)  # cooldown
        self.now += timedelta(minutes=6)
        recovered = self.cache.prefetch(RECORDS, self.provider)
        self.assertEqual((recovered['hits'], recovered['forecast_attempts']), (3, 7))
        self.assertEqual(unpack(self.store.get(LEDGER))['attempts'], 11)
        self.assertEqual(len(service.featured()['cities']), 10)

    def test_unfeatured_on_demand_and_daily_admission_restart(self):
        cache = Cache(self.store, lambda: self.now, daily_limit=1)
        service = self.service(cache)
        self.assertFalse(service.advice(self.params(city_id='123'))['fixture'])
        service.advice(self.params(city_id='123', preference='hot'))
        restarted = self.service(Cache(self.store, lambda: self.now, daily_limit=1))
        with self.assertRaises(Unavailable): restarted.advice(self.params())
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(unpack(self.store.get(LEDGER))['attempts'], 1)
        self.store.put(LEDGER, b'broken')
        with self.assertRaises(Unavailable): restarted.advice(self.params())
        self.assertEqual(len(self.calls), 1)

    def test_corruption_namespace_coordinates_and_safe_reads(self):
        self.cache.prefetch(RECORDS, self.provider)
        original = self.store.get(key(CITY, self.now.date()))
        mutations = [lambda b: b['identity'].update(model='different'),
                     lambda b: b['identity'].update(schema=999),
                     lambda b: b['identity'].update(coordinates=[1,2]),
                     lambda b: b.update(weather_fetched_at=(self.now-timedelta(days=1)).isoformat()),
                     lambda b: b.update(weather_fetched_at=(self.now+timedelta(hours=1)).isoformat()),
                     lambda b: b['response']['hourly_units'].update(temperature_2m='°F')]
        for mutate in mutations:
            body = unpack(original)
            mutate(body)
            self.store.put(key(CITY, self.now.date()), pack(body))
            self.assertIsNone(self.cache.read(CITY, self.now.date()))
            with self.assertRaises(Unavailable): self.service().featured()
        self.store.put(key(CITY, self.now.date()), original.replace(b'24', b'25', 1))
        self.assertIsNone(self.cache.read(CITY, self.now.date()))
        self.store.put(key(CITY, self.now.date()), original)
        changed = dict(CITY, latitude=52.53)
        self.assertNotEqual(key(CITY, self.now.date()), key(changed, self.now.date()))
        self.assertIsNone(self.cache.read(changed, self.now.date()))
        with patch.dict(FORMAT, request_version='new-v2'):
            self.assertIsNone(self.cache.read(CITY, self.now.date()))
            with self.assertRaises(Unavailable): self.service().featured()
        self.store.put(manifest_key(self.now.date()), b'broken')
        with self.assertRaises(Unavailable): self.service().featured()
        self.assertEqual(len(self.calls), 10)

    def test_berlin_midnight_and_dst_utc_instants(self):
        for instant in (datetime(2026,3,25,9,tzinfo=timezone.utc),
                        datetime(2026,10,20,8,tzinfo=timezone.utc),
                        datetime(2026,10,16,21,59,tzinfo=timezone.utc)):
            self.now = instant.astimezone(BERLIN)
            cache = Cache(MemoryStore(), lambda: self.now)
            cache.prefetch(RECORDS, self.provider)
            service = self.service(cache)
            today = self.now.date()
            before = service.featured()
            self.assertEqual(before['today'], today.isoformat())
            hours = parse_hours(forecast(self.now), self.now)
            self.assertEqual(len({d.timestamp() for d,v in hours}), len(hours))
            if instant.month == 10 and instant.day == 20:
                folds = [d for d,v in hours if d.day == 25 and d.hour == 2]
                self.assertEqual([d.fold for d in folds], [0,1])
            # Advance across local midnight via UTC, including offset changes.
            self.now = datetime.combine(today+timedelta(days=1), datetime.min.time(), BERLIN)
            with self.assertRaises(Unavailable): service.featured()
            cache.prefetch(RECORDS, self.provider)
            self.assertNotEqual(service.featured()['today'], before['today'])

    def test_cross_midnight_during_fetch_and_publication(self):
        self.now = NOW.replace(hour=23, minute=59)
        day = self.now.date()
        def late(u,p,t):
            data = forecast(self.now)
            self.now += timedelta(minutes=2)
            return data
        with self.assertRaises(Unavailable): self.cache.prefetch(RECORDS, late)
        self.assertIsNone(self.store.get(manifest_key(day)))
        self.assertIsNone(self.store.get(key(CITY, day)))

    def test_deadline_budget_invalid_input_and_storage_outage(self):
        ticks = [0.0]
        cache = Cache(self.store, lambda: self.now, timer=lambda: ticks[0])
        def slow(u,p,t):
            ticks[0] += 5
            return forecast(self.now)
        with self.assertRaises(Unavailable): cache.prefetch(RECORDS, slow, timeout=1)
        self.assertEqual(cache.stats['forecast_attempts'], 1)
        self.assertEqual(cache.stats['published'], 0)
        for records in (RECORDS[:9], RECORDS+[RECORDS[0]], RECORDS[:9]+[geo(123)],
                        [dict(r, latitude=True) for r in RECORDS]):
            with self.assertRaises((ValueError, Unavailable)):
                cache.prefetch(records, self.provider)
        self.assertEqual(len(self.calls), 0)
        with patch.object(self.store, 'get', side_effect=OSError()):
            with self.assertRaises(Unavailable): self.service().featured()
            with self.assertRaises(Unavailable): self.service().advice(self.params())
        with patch.object(self.store, 'put', side_effect=OSError()):
            with self.assertRaises(Unavailable): self.cache.prefetch(RECORDS, self.provider)

    def test_simultaneous_worker_reader_and_directory_locks(self):
        entered, release = threading.Event(), threading.Event()
        failures = []
        def blocking(u,p,t):
            entered.set()
            release.wait(3)
            return self.provider(u,p,t)
        def worker():
            try: self.cache.prefetch(RECORDS, blocking)
            except Exception as exc: failures.append(exc)
        thread = threading.Thread(target=worker)
        thread.start()
        self.assertTrue(entered.wait(2))
        try:
            with self.assertRaises(Unavailable): self.cache.prefetch(RECORDS, self.provider)
            with self.assertRaises(Unavailable): self.service().featured()
            with self.assertRaises(Unavailable): self.service().advice(self.params())
        finally:
            release.set(); thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(failures, [])
        self.assertEqual(len(self.calls), 10)
        with tempfile.TemporaryDirectory(dir=Path(__file__).parents[2]) as root:
            one, two = DirectoryStore(root), DirectoryStore(root)
            with one.exclusive():
                with self.assertRaises(Unavailable):
                    with two.exclusive(): pass
            with two.exclusive():
                two.put('forecast/test.json', b'complete')
            self.assertEqual(one.get('forecast/test.json'), b'complete')

    def test_manifest_publication_failure_recovery_is_all_hits(self):
        original_put = self.store.put
        def fail_manifest(name, data):
            if name == manifest_key(self.now.date()):
                raise OSError('Injected atomic publication failure')
            original_put(name, data)
        with patch.object(self.store, 'put', side_effect=fail_manifest):
            with self.assertRaises(Unavailable): self.cache.prefetch(RECORDS, self.provider)
        self.assertEqual(len(self.calls), 10)
        with self.assertRaises(Unavailable): self.service().featured()
        recovered = self.cache.prefetch(RECORDS, self.provider)
        self.assertTrue(recovered['complete'])
        self.assertEqual((recovered['hits'], recovered['forecast_attempts']), (10, 0))
        self.assertEqual(len(self.service().featured()['cities']), 10)

    def test_actual_process_restart_and_cross_process_lock(self):
        import subprocess
        import sys
        with tempfile.TemporaryDirectory(dir=Path(__file__).parents[2]) as root:
            cache = Cache(DirectoryStore(root), lambda: self.now)
            cache.prefetch(RECORDS, self.provider)
            code = """
import sys, json
sys.path.insert(0, 'tests/web')
from test_live import NOW
from test_forecasts import RECORDS
from web.forecasts import Cache, DirectoryStore
from web.live import Service, Unavailable
cache = Cache(DirectoryStore(sys.argv[1]), lambda: NOW)
def forbidden(*args):
    raise AssertionError('No network permitted after restart')
try:
    stats = cache.prefetch(RECORDS, forbidden)
    service = Service(forbidden, lambda: NOW, forecast_cache=cache)
    assert len(service.featured()['cities']) == 10
    assert service.city_advice(dict(city_id='berlin'))['fixture'] is False
    print(json.dumps(stats, sort_keys=True))
except Unavailable:
    print('locked')
"""
            result = subprocess.run([sys.executable, '-c', code, root], capture_output=True, text=True, check=True)
            stats = json.loads(result.stdout)
            self.assertEqual((stats['hits'], stats['forecast_attempts']), (10, 0))
            with cache.store.exclusive():
                result = subprocess.run([sys.executable, '-c', code, root], capture_output=True, text=True, check=True)
                self.assertEqual(result.stdout.strip(), 'locked')

    def test_cli_counts_only_on_bad_operator_input(self):
        from contextlib import redirect_stdout
        from io import StringIO
        from web.prefetch_forecasts import main
        with tempfile.TemporaryDirectory(dir=Path(__file__).parents[2]) as root:
            source = Path(root)/'cities.json'
            source.write_text(json.dumps(RECORDS[:9]))
            output = StringIO()
            with redirect_stdout(output):
                status = main(['--cities-file', str(source), '--store-dir', str(Path(root)/'store')])
            self.assertEqual(status, 1)
            result = json.loads(output.getvalue())
            self.assertFalse(result['complete'])
            self.assertEqual(result['forecast_attempts'], 0)
            self.assertNotIn('Berlin', output.getvalue())

    def test_same_source_packing_outliers_split_noise(self):
        for values, main, expected_kind in [([24,14,24]+[24]*11,2,'cold'),
                ([14,24,14]+[14]*11,4,'warm'), ([24]*7+[14]*7,None,'mixed'),
                ([12.9,13.1,13.2]+[13.1]*11,4,None)]:
            cache = Cache(MemoryStore(), lambda: self.now)
            cache.prefetch(RECORDS, lambda u,p,t: forecast(self.now,values))
            service = self.service(cache)
            card = service.featured()['cities'][0]
            detail = service.city_advice(dict(city_id='berlin'))
            self.assertEqual(card['warmth_indicator_level'], main)
            self.assertEqual(bool(card['packing_variation_summary']), expected_kind is not None)
            self.assertEqual(bool(detail['packing_variation_notice']), expected_kind is not None)
            self.assertEqual(card['packing_variation_kind'],expected_kind)
            self.assertEqual(detail['packing_variation_kind'],expected_kind)
            self.assertEqual(card, detail)


class ForecastAPITests(unittest.TestCase):
    def test_real_default_featured_readonly_and_explicit_fixtures(self):
        from http.server import ThreadingHTTPServer
        from urllib.request import urlopen
        from urllib.error import HTTPError
        from web.server import Handler
        fake = Fake()
        cache = Cache(MemoryStore(), lambda: NOW)
        cache.prefetch(RECORDS, lambda u,p,t: fake(u,p))
        class TestHandler(Handler):
            service = Service(fake, lambda: NOW, forecast_cache=cache)
        server = ThreadingHTTPServer(('127.0.0.1', 0), TestHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = 'http://127.0.0.1:'+str(server.server_port)
        def request(path):
            try:
                with urlopen(base+path) as r: return r.status, json.load(r)
            except HTTPError as exc:
                return exc.code, json.load(exc)
        try:
            code, cards = request('/api/featured')
            self.assertEqual(code, 200)
            self.assertFalse(cards['fixture'])
            code, detail = request('/api/advice?view=city&city_id=berlin&preference=hot&start=bogus')
            self.assertEqual(code, 200)
            self.assertEqual(detail, cards['cities'][0])
            self.assertEqual(request('/api/context')[1]['today'], NOW.date().isoformat())
            self.assertEqual(request('/api/advice?view=city')[0], 400)
            self.assertEqual(request('/api/advice?view=city&city_id=unknown')[0], 400)
            self.assertEqual(len(fake.calls), 10)
            code, demo = request('/api/featured?fixture=stable')
            self.assertEqual(code, 200)
            self.assertTrue(demo['fixture'])
            cache.store.put(key(CITY, NOW.date()), b'broken')
            self.assertEqual(request('/api/featured')[0], 503)
            self.assertEqual(request('/api/advice?view=city&city_id=berlin')[0], 503)
            self.assertEqual(len(fake.calls), 10)
        finally:
            server.shutdown(); server.server_close(); thread.join()


if __name__ == '__main__':
    unittest.main()
