import datetime as dt
import unittest
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

from test_forecast_advice import fixture as forecast_fixture
from trip_advisor import (geocode_url, select_city, historic_url,
                          historical_summary, validate_trip, year_earlier,
                          build, format_trip)

NOW = dt.datetime(2026, 10, 14, 8, tzinfo=ZoneInfo('Europe/Berlin'))
BERLIN = {'name': 'Berlin', 'latitude': 52.52437, 'longitude': 13.41053,
          'timezone': 'Europe/Berlin', 'country_code': 'DE', 'admin1': 'Berlin'}
MUNICH = {'name': 'München', 'latitude': 48.137, 'longitude': 11.575,
          'timezone': 'Europe/Berlin', 'country_code': 'DE', 'admin1': 'Bayern'}


def history_fixture(start, end, temp=10, rain_dates=None):
    days = [(start + dt.timedelta(days=i)).isoformat()
            for i in range((end - start).days + 1)]
    times = [f'{date}T{hour:02d}:00' for date in days for hour in range(24)]
    return {'timezone': 'Europe/Berlin',
            'hourly': {'time': times, 'temperature_2m': [temp for _ in times]},
            'daily': {'time': days,
                      'precipitation_sum': [3 if date in (rain_dates or []) else 0 for date in days],
                      'snowfall_sum': [0] * len(days)}}


def fake_fetch_log(calls, city=BERLIN,  temp_2025=8, temp_2024=11, current=None):
    def fetch(url):
        calls.append(url)
        host = urlparse(url).netloc
        params = parse_qs(urlparse(url).query)
        if host == 'geocoding-api.open-meteo.com':
            return {'results': [city]}
        if host == 'api.open-meteo.com':
            return current or forecast_fixture([21,21,21,21,21,21,21,21,21,21,21,21,0,0])
        if host == 'archive-api.open-meteo.com':
            start, end = dt.date.fromisoformat(params['start_date'][0]), dt.date.fromisoformat(params['end_date'][0])
            return history_fixture(start, end, temp_2025 if start.year == 2025 else temp_2024)
        raise AssertionError('Unexpected host: ' + host)
    return fetch


class TripAdvisorTest(unittest.TestCase):
    def test_geocode_filtered_germany(self):
        query = parse_qs(urlparse(geocode_url('München')).query)
        self.assertEqual(query['countryCode'], ['DE'])
        self.assertEqual(query['name'], ['München'])
        self.assertEqual(select_city({'results': [MUNICH]}, 'München')['name'], 'München')

    def test_no_silent_guess_on_prefix_or_other_country(self):
        with self.assertRaisesRegex(ValueError, '找不到唯一'):
            select_city({'results': [MUNICH]}, 'Münch')
        with self.assertRaisesRegex(ValueError, '找不到唯一'):
            select_city({'results': [dict(MUNICH, country_code='AT')]}, 'München')

    def test_ambiguous_city_rejected(self):
        options = [dict(BERLIN, admin1='Berlin'), dict(BERLIN, admin1='Brandenburg')]
        with self.assertRaisesRegex(ValueError, '不唯一'):
            select_city({'results': options}, 'Berlin')

    def test_historical_url_has_city_and_exact_dates(self):
        url = historic_url(MUNICH, dt.date(2025, 10, 20), dt.date(2025, 10, 23))
        q = parse_qs(urlparse(url).query)
        self.assertEqual(q['latitude'], ['48.137'])
        self.assertEqual(q['start_date'], ['2025-10-20'])
        self.assertEqual(q['end_date'], ['2025-10-23'])
        self.assertEqual(q['hourly'], ['temperature_2m'])

    def test_history_daytime_uses_hourly_not_daily_high(self):
        a, b = dt.date(2025, 10, 20), dt.date(2025, 10, 22)
        h = history_fixture(a, b, 12, rain_dates=['2025-10-21'])
        for j, t in enumerate(h['hourly']['time']):
            if t.startswith('2025-10-21T') and 9 <= int(t[11:13]) <= 18:
                h['hourly']['temperature_2m'][j] = 5
        s = historical_summary(h, a, b)
        self.assertEqual(s['typical_daytime'], 12)
        self.assertEqual(s['coldest_daytime'], 5)
        self.assertEqual(s['precipitation_days'], 1)

    def test_historical_missing_dates_or_daytime_refused(self):
        a, b = dt.date(2025, 10, 20), dt.date(2025, 10, 21)
        h = history_fixture(a, b)
        h['daily']['time'].pop()
        with self.assertRaisesRegex(ValueError, 'do not cover'):
            historical_summary(h, a, b)
        h = history_fixture(a, b)
        h['hourly']['temperature_2m'] = [None] * len(h['hourly']['time'])
        with self.assertRaisesRegex(ValueError, 'incomplete'):
            historical_summary(h, a, b)

    def test_dates_outside_short_forecast_rejected_before_api(self):
        with self.assertRaisesRegex(ValueError, '未来14'):
            validate_trip(dt.date(2026, 10, 20), dt.date(2026, 11, 10), NOW)
        with self.assertRaisesRegex(ValueError, '早于'):
            validate_trip(dt.date(2026, 10, 22), dt.date(2026, 10, 20), NOW)
        with self.assertRaisesRegex(ValueError, '之后'):
            validate_trip(dt.date(2026, 10, 13), dt.date(2026, 10, 20), NOW)

    def test_two_year_windows_match_selected_trip(self):
        calls = []
        f, hist = build('Berlin', dt.date(2026,10,20), dt.date(2026,10,23),
                        now=NOW, fetch=fake_fetch_log(calls))
        self.assertEqual(len(calls), 4)
        self.assertEqual([h['start'] for h in hist], ['2025-10-20', '2024-10-20'])
        self.assertEqual([h['end'] for h in hist], ['2025-10-23', '2024-10-23'])
        self.assertEqual(f['dates'], ['2026-10-20', '2026-10-21', '2026-10-22', '2026-10-23'])
        self.assertEqual(f['typical_daytime'], 21.0)
        self.assertEqual([h['typical_daytime'] for h in hist], [8,11])

    def test_non_berlin_city_changes_forecast_coordinates_and_title(self):
        calls = []
        f, history = build('München',dt.date(2026,10,17),dt.date(2026,10,19),
                           now=NOW,fetch=fake_fetch_log(calls,city=MUNICH))
        self.assertEqual(parse_qs(urlparse(calls[1]).query)['latitude'], ['48.137'])
        self.assertIn('München · 2026年10月17～19日', format_trip(f,history))

    def test_selected_dates_do_not_use_cold_days_outside_trip(self):
        data = forecast_fixture([12]*2+[22]*5+[0]*7)
        calls=[]
        f,history=build('Berlin',dt.date(2026,10,16),dt.date(2026,10,19),
                        now=NOW,fetch=fake_fetch_log(calls,current=data))
        self.assertEqual(f['main_level'], 3)
        self.assertEqual(f['cold_dates'], [])
        self.assertEqual(f['typical_daytime'], 22)

    def test_historic_cold_helps_layer_note_not_override_forecast(self):
        calls=[]
        f,history=build('Berlin',dt.date(2026,10,16),dt.date(2026,10,19),
                        now=NOW,fetch=fake_fetch_log(calls,temp_2025=1,temp_2024=3))
        text=format_trip(f,history)
        self.assertEqual(f['main_level'],3)
        self.assertIn('历史对照',text)
        self.assertIn('更凉的白天',text)
        self.assertIn('两年的同期记录',text)

    def test_year_earlier_cross_year_and_leap(self):
        self.assertEqual(year_earlier(dt.date(2027,1,3),1),dt.date(2026,1,3))
        self.assertEqual(year_earlier(dt.date(2024,2,29),1),dt.date(2023,2,28))

    def test_pref_hot_kept_in_selected_trip(self):
        calls=[]
        f,history=build('Berlin',dt.date(2026,10,16),dt.date(2026,10,18),
                        preference='hot',now=NOW,fetch=fake_fetch_log(calls))
        self.assertIn('比较怕热',format_trip(f,history))


    def test_city_advisor_preserves_live_forecast_13c_boundary_copy(self):
        calls = []
        temperatures = [12.8] * 14
        f, history = build('München', dt.date(2026, 10, 17), dt.date(2026, 10, 20),
                           now=NOW, fetch=fake_fetch_log(calls, city=MUNICH,
                                                         current=forecast_fixture(temperatures)))
        text = format_trip(f, history)
        self.assertEqual(f['typical_daytime'], 12.8)
        self.assertIn('München · 2026年10月17～20日穿衣建议', text)
        self.assertIn('接近厚度分界', text)
        self.assertIn('保暖程度适中的外套', text)
        self.assertIn('轻羽绒替代外套', text)
        self.assertNotIn('建议准备长袖、保暖中间层，以及保暖外套或轻羽绒', text)

    def test_city_advisor_preserves_second_week_uncertainty(self):
        calls = []
        f, history = build('München', dt.date(2026, 10, 24), dt.date(2026, 10, 26),
                           now=NOW, fetch=fake_fetch_log(calls, city=MUNICH))
        text = format_trip(f, history)
        self.assertIn('行程全部处于预报第8～14天', text)
        self.assertIn('后期留意：10月26日', text)

    def test_other_city_detailed_report_contains_correct_name(self):
        calls = []
        f, history = build('München', dt.date(2026, 10, 17), dt.date(2026, 10, 20),
                           now=NOW, fetch=fake_fetch_log(calls, city=MUNICH))
        self.assertIn('München指定旅行日期穿衣建议', format_trip(f, history, details=True))
        self.assertNotIn('柏林指定旅行日期穿衣建议', format_trip(f, history, details=True))


if __name__ == '__main__':
    unittest.main()
