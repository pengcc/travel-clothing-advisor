"""穿衣小伙伴 (Issue #101): pure build, Service.pal() snapshot rules, fixtures. No provider network."""
from datetime import date, datetime, time, timedelta
import json
import unittest
from unittest.mock import patch

from test_forecasts import RECORDS, CITY
from test_live import NOW, forecast
from test_readonly import forbidden, GetOnly
from web.fixtures import BERLIN, pal as fixture_pal
from web.forecasts import Cache, FORMAT, key, pack, identity
from web.history import MemoryStore
from web.live import FORECAST, Service, Unavailable, level, parse_hours
from web.pal import build, display_temperature
from web.readonly import service


def hourly(day, fn):
    """14 days of hourly data starting at Berlin midnight of `day`; fn(local datetime) -> temperature."""
    start = datetime.combine(day, time(), BERLIN)
    end = datetime.combine(day + timedelta(days=14), time(), BERLIN)
    times = list(range(int(start.timestamp()), int(end.timestamp()), 3600))
    return dict(timezone='Europe/Berlin', hourly_units=dict(temperature_2m='°C'),
                hourly=dict(time=times, temperature_2m=[fn(datetime.fromtimestamp(t, BERLIN)) for t in times]))


def diurnal(local):
    """Cool nights, warm afternoons, a little drift per day: intraday variation on purpose."""
    base = 8 + 3 * ((local.date().toordinal()) % 3)
    return round(base + 10 * max(0, 1 - abs(local.hour - 14) / 8), 1)


def put_snapshot(store, day, acquired, fn=diurnal, city=None):
    city = city or CITY
    data = hourly(day, fn)
    body = dict(identity=identity(city, day), source=FORECAST,
                weather_fetched_at=acquired.isoformat(), response=data)
    store.put(key(city, day), pack(body))
    return data


def at(day_offset, hour, minute=0, base=NOW):
    return datetime.combine(base.date() + timedelta(days=day_offset), time(hour, minute), BERLIN)


class PalCase(unittest.TestCase):
    def make(self, clock_value):
        self.now = clock_value
        self.store = MemoryStore()
        self.clock = lambda: self.now
        self.service = service(self.store, RECORDS, self.clock, independent_cities=True)
        self.service.fetch = forbidden
        return self.service


class DisplayTemperatureTests(unittest.TestCase):
    def test_documented_examples(self):
        for value, shown in [(12.6, 12), (17.6, 17), (22.5, 22), (13.0, 13), (-2.5, -3), (-0.3, 0), (27.9, 27), (5.5, 5), (6.0, 6)]:
            with self.subTest(value=value):
                self.assertEqual(display_temperature(value), shown)

    def test_level_is_always_consistent(self):
        for tenths in range(-300, 500):
            value = tenths / 10
            self.assertEqual(level(display_temperature(value)), level(value), value)
        self.assertEqual(display_temperature(-0.3), 0)
        self.assertNotEqual(str(display_temperature(-0.3)), '-0')


class BuildTests(PalCase):
    def cached(self, acquired, day=None):
        day = day or acquired.date()
        data = hourly(day, diurnal)
        return data, acquired, 'v1'

    def test_shape_and_values(self):
        now = at(0, 7)
        result = build(CITY, self.cached(at(0, 6)), now, now)
        self.assertEqual(len(result['days']), 7)
        self.assertEqual([d['date'] for d in result['days']][0], now.date().isoformat())
        self.assertEqual(result['city'], dict(id='berlin', zh='柏林', name='Berlin', state='Berlin'))
        self.assertFalse(result['stale'])
        self.assertFalse(result['fixture'])
        self.assertEqual(result['data_version'], 'temperature-v1-v1')
        for day in result['days']:
            self.assertEqual([s['slot'] for s in day['slots']], ['morning', 'midday', 'evening'])
            self.assertIn(day['swing'], ('none', 'large'))
        mid = result['days'][1]['slots'][1]
        self.assertEqual((mid['window'], mid['label_time'], mid['past'], mid['partial']), ('09–18', '13:00', False, False))
        self.assertEqual(level(mid['temperature_c']), mid['level'])

    def test_past_and_partial_follow_the_clock(self):
        now = at(0, 10, 30)
        today = build(CITY, self.cached(at(0, 10, 29)), now, now)['days'][0]['slots']
        self.assertTrue(today[0]['past'])
        self.assertIsNone(today[0]['temperature_c'])
        self.assertIsNone(today[0]['level'])
        self.assertFalse(today[1]['past'])
        self.assertTrue(today[1]['partial'])      # 11:00–18:00 only
        self.assertFalse(today[2]['partial'])

    def test_after_22_today_is_all_past_without_error(self):
        now = at(0, 22, 30)
        result = build(CITY, self.cached(at(0, 22, 0)), now, now)
        self.assertTrue(all(s['past'] for s in result['days'][0]['slots']))
        self.assertEqual(result['days'][0]['swing'], 'none')
        self.assertFalse(result['days'][1]['slots'][0]['past'])

    def test_swing_is_large_only_for_two_or_more_levels(self):
        def two_levels(local):
            return 8.0 if local.hour <= 8 else 19.0 if local.hour <= 18 else 14.0
        now = at(1, 7)
        data = hourly(now.date() - timedelta(days=1), two_levels)
        result = build(CITY, (data, at(0, 20), 'v'), now, now)
        slots = result['days'][0]['slots']
        self.assertEqual([s['level'] for s in slots], [5, 3, 4])
        self.assertEqual(result['days'][0]['swing'], 'large')
        flat = hourly(now.date() - timedelta(days=1), lambda l: 19.0 if l.hour < 12 else 18.0)
        self.assertEqual(build(CITY, (flat, at(0, 20), 'v'), now, now)['days'][0]['swing'], 'none')

    def test_dst_change_days(self):
        # Temperature equals the local hour, so a wrong hour shift across the transition changes the medians.
        for day in (date(2026, 10, 24), date(2026, 3, 28)):          # the day before the change
            with self.subTest(day=day):
                now = datetime.combine(day, time(20), BERLIN)
                data = hourly(day, lambda local: float(local.hour))
                result = build(CITY, (data, now - timedelta(hours=1), 'v'), now, now)
                self.assertEqual(len(result['days']), 7)
                change = result['days'][1]
                self.assertEqual(change['date'], (day + timedelta(days=1)).isoformat())
                slots = change['slots']
                self.assertEqual([s['temperature_c'] for s in slots], [7, 14, 21])
                self.assertEqual([s['level'] for s in slots], [level(7), level(14), level(21)])
                self.assertFalse(any(s['past'] or s['partial'] for s in slots))
                self.assertTrue(all(s['past'] for s in result['days'][0]['slots'][:2]))


class ServiceSnapshotTests(PalCase):
    def test_same_day_snapshot_matches_single_day_trip_level(self):
        """V3: same snapshot, clock before 18:00, single-day trip view is the comparator."""
        self.make(at(0, 10, 30))
        put_snapshot(self.store, self.now.date(), at(0, 10, 0))
        result = self.service.pal()
        self.assertFalse(result['stale'])
        today = self.now.date().isoformat()
        for offset in range(0, 3):
            day = (self.now.date() + timedelta(days=offset)).isoformat()
            trip = self.service.advice(dict(view='trip', city_id='berlin', start=day, end=day, preference='normal'))
            midday = result['days'][offset]['slots'][1]
            self.assertEqual(midday['level'], trip['warmth_indicator_level'], day)

    def test_latest_snapshot_is_yesterdays_when_today_is_missing(self):
        self.make(at(0, 8))
        put_snapshot(self.store, self.now.date() - timedelta(days=1), at(-1, 22, 22))
        result = self.service.pal()
        self.assertTrue(result['stale'])
        self.assertEqual(result['weather_fetched_at'], at(-1, 22, 22).isoformat(timespec='seconds'))
        self.assertEqual(len(result['days']), 7)
        self.assertEqual(result['days'][0]['date'], self.now.date().isoformat())
        self.assertFalse(result['days'][0]['slots'][0]['past'])      # today 06–08: 08:00 hour is not yet past

    def test_today_wins_over_older_and_corrupt_today_falls_back(self):
        self.make(at(0, 13))
        put_snapshot(self.store, self.now.date() - timedelta(days=1), at(-1, 22, 22))
        put_snapshot(self.store, self.now.date(), at(0, 12, 8))
        self.assertFalse(self.service.pal()['stale'])
        self.store.put(key(CITY, self.now.date()), b'corrupt')
        self.assertTrue(self.service.pal()['stale'])

    def test_day_before_yesterday_is_usable_within_48_hours_only(self):
        self.make(at(0, 12))
        put_snapshot(self.store, self.now.date() - timedelta(days=2), at(-2, 22, 0))     # 38 h old
        self.assertTrue(self.service.pal()['stale'])
        self.make(at(0, 12))
        put_snapshot(self.store, self.now.date() - timedelta(days=2), at(-2, 7, 0))      # 53 h old
        with self.assertRaises(Unavailable):
            self.service.pal()
        self.make(at(0, 12))
        put_snapshot(self.store, self.now.date() - timedelta(days=3), at(-3, 22, 0))     # not even tried
        with self.assertRaises(Unavailable):
            self.service.pal()

    def test_nothing_usable_is_unavailable_never_history(self):
        self.make(at(0, 8))
        with self.assertRaises(Unavailable):
            self.service.pal()

    def test_snapshot_validation_uses_the_snapshots_own_day(self):
        self.make(at(0, 8))
        yesterday = self.now.date() - timedelta(days=1)
        # Filed under yesterday but acquired on another Berlin day: invalid, not served.
        put_snapshot(self.store, yesterday, at(-2, 22, 0))
        with self.assertRaises(Unavailable):
            self.service.pal()

    def test_existing_read_still_only_accepts_today(self):
        self.make(at(0, 8))
        put_snapshot(self.store, self.now.date() - timedelta(days=1), at(-1, 22, 22))
        cache = Cache(self.store, self.clock, read_only=True)
        self.assertIsNone(cache.read(CITY, self.now.date() - timedelta(days=1)))
        self.assertIsNotNone(cache.read_snapshot(CITY, self.now.date() - timedelta(days=1)))

    def test_midnight_rollover_during_request_fails_closed(self):
        self.make(at(0, 23, 59))
        put_snapshot(self.store, self.now.date(), at(0, 23, 0))
        ticks = iter([at(0, 23, 59), at(1, 0, 0)])        # request start, then generated-at after midnight
        self.service.clock = lambda: next(ticks)
        self.service.forecasts.clock = lambda: at(0, 23, 59)
        with self.assertRaises(Unavailable):
            self.service.pal()

    def test_never_downloads_or_writes(self):
        self.make(at(0, 8))
        put_snapshot(self.store, self.now.date() - timedelta(days=1), at(-1, 22, 22))
        self.service.forecasts.store = GetOnly(self.store.objects)
        with patch('web.forecasts.Cache.obtain', new=forbidden), patch('web.forecasts.Cache.load_locked', new=forbidden):
            self.assertTrue(self.service.pal()['stale'])


class ModeTests(PalCase):
    def test_legacy_read_modes_are_unavailable(self):
        self.make(at(0, 10))
        put_snapshot(self.store, self.now.date(), at(0, 9))
        legacy = service(self.store, RECORDS, self.clock)            # independent_cities=False, the default
        with self.assertRaises(Unavailable) as caught:
            legacy.pal()
        self.assertIn('暂不提供', str(caught.exception))
        self.assertEqual(caught.exception.code, 'temporarily_unavailable')

    def test_local_worker_mode_cannot_use_previous_day_snapshot(self):
        now = at(0, 8)
        store = MemoryStore()
        put_snapshot(store, now.date() - timedelta(days=1), at(-1, 22, 22))
        # Real local worker shape: city records present, no offline_cities. The only
        # snapshot is yesterday's, so the previous-day rule must not apply here.
        local = Service(forbidden, lambda: now, forecast_cache=Cache(store, lambda: now),
                        featured_records=RECORDS)
        self.assertIsNone(local.offline_cities)
        with self.assertRaises(Unavailable):
            local.pal()
        put_snapshot(store, now.date(), at(0, 7))                       # today's snapshot still works
        self.assertFalse(local.pal()['stale'])

    def test_unexpected_failures_become_unavailable(self):
        self.make(at(0, 8))
        self.service.forecasts.read_snapshot = lambda *a: (_ for _ in ()).throw(KeyError('x'))
        with self.assertRaises(Unavailable):
            self.service.pal()


class FixtureTests(unittest.TestCase):
    def test_fixture_is_deterministic_and_marked(self):
        now = datetime(2026, 10, 16, 7, 0, tzinfo=BERLIN)
        a, b = fixture_pal(now), fixture_pal(now)
        self.assertEqual(a, b)
        self.assertTrue(a['fixture'])
        self.assertEqual(a['data_version'], 'ui-fixtures-v1')
        self.assertEqual(len(a['days']), 7)
        self.assertTrue(any(d['swing'] == 'large' for d in a['days']))
        self.assertTrue(all(s['level'] is not None for d in a['days'][1:] for s in d['slots']))
        # Intraday variation: morning and midday differ on at least one day.
        self.assertTrue(any(d['slots'][0]['temperature_c'] != d['slots'][1]['temperature_c'] for d in a['days']))
        json.dumps(a)


if __name__ == '__main__':
    unittest.main()
