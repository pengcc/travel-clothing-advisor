import datetime as dt
import unittest
from zoneinfo import ZoneInfo
from urllib.parse import parse_qs, urlparse
from forecast_advice import process, format_advice, forecast_url


def fixture(highs=None):
    start = dt.date(2026, 10, 14)
    dates = [(start + dt.timedelta(days=i)).isoformat() for i in range(14)]
    highs = highs or [16, 16, 16, 16, 16, 16, 16, 16, 16, 16, 16, 16, 16, 16]
    times = []
    temps = []
    for date, t in zip(dates, highs):
        for hour in range(24):
            times.append(f'{date}T{hour:02d}:00')
            temps.append(t if 9 <= hour <= 18 else t - 7)
    return {'timezone': 'Europe/Berlin',
            'hourly': {'time': times, 'temperature_2m': temps},
            'daily': {'time': dates,
                      'precipitation_probability_max': [10] * 14,
                      'precipitation_sum': [0] * 14,
                      'snowfall_sum': [0] * 14,
                      'wind_gusts_10m_max': [15] * 14}}


NOW = dt.datetime(2026, 10, 14, 8, 0, tzinfo=ZoneInfo('Europe/Berlin'))


class ForecastTest(unittest.TestCase):
    def test_url_14_days_berlin(self):
        p = parse_qs(urlparse(forecast_url()).query)
        self.assertEqual(p['forecast_days'], ['14'])
        self.assertEqual(p['timezone'], ['Europe/Berlin'])
        self.assertEqual(p['latitude'], ['52.52'])
        self.assertEqual(p['hourly'], ['temperature_2m'])

    def test_moderate_autumn_advice(self):
        out = process(fixture(), NOW)
        self.assertEqual(out['main_level'], 4)
        self.assertEqual(len(out['days']), 14)
        self.assertTrue(any('早晚' in x for x in out['advice']))

    def test_sudden_cold_requires_layer(self):
        highs = [23] * 14
        highs[4] = 7
        out = process(fixture(highs), NOW)
        self.assertTrue(any('保暖' in x and '10月18日' in x for x in out['advice']))

    def test_hot_to_warm_does_not_require_insulation(self):
        out = process(fixture([30] * 7 + [25] * 7), NOW)
        self.assertFalse(any('偏冷日' in x for x in out['advice']))
        self.assertFalse(any('可加的保暖层' in x for x in out['advice']))

    def test_rain_wind_are_independent(self):
        f = fixture()
        f['daily']['precipitation_probability_max'][3] = 80
        f['daily']['wind_gusts_10m_max'][5] = 50
        out = process(f, NOW)
        self.assertTrue(any('雨具' in x for x in out['advice']))
        self.assertTrue(any('挡风' in x for x in out['advice']))
        self.assertEqual(out['main_level'], 4)

    def test_evening_today_not_using_past_daytime(self):
        now = dt.datetime(2026, 10, 14, 20, 0, tzinfo=ZoneInfo('Europe/Berlin'))
        out = process(fixture(), now)
        self.assertIsNone(out['days'][0]['daytemp'])
        self.assertEqual(out['main_level'], 4)

    def test_missing_daily_raises(self):
        f = fixture()
        f['daily']['snowfall_sum'] = []
        with self.assertRaisesRegex(ValueError, 'incomplete'):
            process(f, NOW)

    def test_wrong_date_or_zone_raises(self):
        f = fixture()
        f['timezone'] = 'UTC'
        with self.assertRaisesRegex(ValueError, 'timezone'):
            process(f, NOW)
        f['timezone'] = 'Europe/Berlin'
        f['daily']['time'][1] = '2026-10-20'
        with self.assertRaisesRegex(ValueError, 'consecutive'):
            process(f, NOW)

    def test_missing_next_day_hourly_raises(self):
        f = fixture()
        for i, d in enumerate(f['hourly']['time']):
            if d.startswith('2026-10-16T'):
                f['hourly']['temperature_2m'][i] = None
        with self.assertRaisesRegex(ValueError, 'daytime forecast'):
            process(f, NOW)

    def test_overnight_low_does_not_count_as_morning_evening(self):
        f = fixture()
        for i, stamp in enumerate(f['hourly']['time']):
            if stamp.endswith('T03:00'):
                f['hourly']['temperature_2m'][i] = -20
            elif stamp.endswith(('T06:00', 'T07:00', 'T08:00', 'T19:00', 'T20:00', 'T21:00', 'T22:00')):
                f['hourly']['temperature_2m'][i] = 16
        out = process(f, NOW)
        self.assertFalse(any('部分早晚明显更凉' in x for x in out['advice']))

    def test_user_report_cold_spell_is_not_hidden_by_farther_coldest_day(self):
        # Daytime values reproduced from the user's successful 2026-10-14 CLI
        # result; synthetic per-hour details, no claim to be the original JSON.
        highs = [14.6, 14.6, 16.5, 12.4, 12.3, 11.5, 13.2,
                 15.4, 14.2, 14.9, 14.6, 13.1, 14.1, 10.4]
        out = process(fixture(highs), dt.datetime(2026, 10, 14, 20, 0, tzinfo=ZoneInfo('Europe/Berlin')))
        self.assertEqual(out['main_level'], 4)
        self.assertTrue(any('10月17～19日' in x and '共3天' in x for x in out['advice']))
        self.assertTrue(any('10月27日' in x and '第8～14天' in x for x in out['advice']))
        self.assertFalse(any('偏冷日 2026-10-27' in x for x in out['advice']))

    def test_rain_shows_dates_not_only_counts(self):
        f = fixture()
        f['daily']['precipitation_probability_max'][3] = 75
        f['daily']['precipitation_probability_max'][4] = 65
        out = process(f, NOW)
        self.assertTrue(any('10月17～18日' in x and '共2天' in x for x in out['advice']))

    def test_past_day_daily_rain_not_in_future_advice(self):
        f = fixture()
        f['daily']['precipitation_sum'][0] = 25  # no longer relevant after 20:00
        out = process(f, dt.datetime(2026, 10, 14, 20, 0, tzinfo=ZoneInfo('Europe/Berlin')))
        self.assertFalse(any('降水信号' in x for x in out['advice']))

    def test_today_after_daylight_is_labeled(self):
        now = dt.datetime(2026, 10, 14, 20, 0, tzinfo=ZoneInfo('Europe/Berlin'))
        text = format_advice(process(fixture(), now))
        self.assertIn('14个日历日', text)
        self.assertIn('2026-10-14: 今日白天已过', text)

    def test_horizon_not_turned_into_climate_claim(self):
        out = process(fixture(), NOW)
        text = format_advice(out)
        self.assertIn('第8～14天', text)
        self.assertIn('Open-Meteo', text)
        self.assertNotIn('历史气候', text)


if __name__ == '__main__':
    unittest.main()
