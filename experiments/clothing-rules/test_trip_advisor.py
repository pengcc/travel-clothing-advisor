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

    def test_berlin_capital_wins_over_schleswig_holstein_namesake(self):
        # Open-Meteo's documented Berlin capital record is GeoNames 2950159.
        # The same name also exists in Schleswig-Holstein, as observed in the
        # user's real 2026-10-15 geocoding request.
        capital = dict(BERLIN, id=2950159, feature_code='PPLC',
                       population=3426354, admin1='Land Berlin')
        namesake = dict(BERLIN, id=9999, latitude=54.04, longitude=10.45,
                        feature_code='PPL', population=500,
                        admin1='Schleswig-Holstein')
        for matches in ([namesake, capital], [capital, namesake]):
            self.assertEqual(select_city({'results': matches}, 'Berlin')['id'], 2950159)
            self.assertEqual(select_city({'results': matches}, 'Berlin, Germany')['id'], 2950159)

    def test_explicit_german_state_selects_intended_berlin(self):
        capital = dict(BERLIN, id=2950159, feature_code='PPLC',
                       population=3426354, admin1='Land Berlin')
        namesake = dict(BERLIN, id=9999, latitude=54.04,
                        feature_code='PPL', population=500,
                        admin1='Schleswig-Holstein')
        payload = {'results': [namesake, capital]}
        self.assertEqual(select_city(payload, 'Berlin, Schleswig-Holstein')['id'], 9999)
        self.assertEqual(select_city(payload, 'Berlin, Berlin')['id'], 2950159)
        self.assertEqual(select_city(payload, 'Berlin, Land Berlin')['id'], 2950159)
        with self.assertRaisesRegex(ValueError, '找不到唯一'):
            select_city(payload, 'Berlin, Bayern')

    def test_much_larger_noncapital_can_be_selected_without_order_guess(self):
        large = dict(MUNICH, name='Halle', population=230000, feature_code='PPLA2')
        village = dict(MUNICH, name='Halle', population=1800, feature_code='PPL',
                       admin1='Niedersachsen')
        self.assertEqual(select_city({'results': [village, large]}, 'Halle'), large)

    def test_same_name_rivals_or_missing_population_not_guessed(self):
        a = dict(MUNICH, name='Halle', population=160000, feature_code='PPL',
                 admin1='Sachsen-Anhalt')
        b = dict(MUNICH, name='Halle', population=90000, feature_code='PPL',
                 admin1='Niedersachsen')
        with self.assertRaisesRegex(ValueError, '不唯一'):
            select_city({'results': [a, b]}, 'Halle')
        del b['population']
        with self.assertRaisesRegex(ValueError, '不唯一'):
            select_city({'results': [a, b]}, 'Halle')

    def test_duplicate_capital_records_remain_ambiguous(self):
        a = dict(BERLIN, feature_code='PPLC', population=3426354)
        b = dict(BERLIN, feature_code='PPLC', population=3426354,
                 admin1='Schleswig-Holstein')
        with self.assertRaisesRegex(ValueError, '不唯一'):
            select_city({'results': [a, b]}, 'Berlin')

    def test_wrong_country_or_prefix_remains_rejected_with_namesakes(self):
        capital = dict(BERLIN, feature_code='PPLC', population=3426354)
        namesake = dict(BERLIN, feature_code='PPL', population=500,
                        admin1='Schleswig-Holstein')
        payload = {'results': [dict(capital, country_code='US'), namesake]}
        self.assertEqual(select_city(payload, 'Berlin')['admin1'], 'Schleswig-Holstein')
        with self.assertRaisesRegex(ValueError, '找不到唯一'):
            select_city(payload, 'Berli')

    def test_build_uses_capital_coordinates_for_all_three_weather_requests(self):
        capital = dict(BERLIN, id=2950159, feature_code='PPLC',
                       population=3426354, admin1='Land Berlin')
        namesake = dict(BERLIN, id=9999, latitude=54.04, longitude=10.45,
                        population=500, feature_code='PPL',
                        admin1='Schleswig-Holstein')
        calls = []
        fallback = fake_fetch_log(calls, city=capital)
        def fetch(url):
            if urlparse(url).netloc == 'geocoding-api.open-meteo.com':
                calls.append(url)
                return {'results': [namesake, capital]}
            return fallback(url)
        forecast, history = build('Berlin', dt.date(2026, 10, 17),
                                  dt.date(2026, 10, 20),
                                  now=NOW, fetch=fetch)
        self.assertEqual(len(calls), 4)
        for url in calls[1:]:
            params = parse_qs(urlparse(url).query)
            self.assertEqual(params['latitude'], ['52.52437'])
            self.assertEqual(params['longitude'], ['13.41053'])
        self.assertIn('Berlin · 2026年10月17～20日', format_trip(forecast, history))

    def test_state_qualified_lookup_queries_only_settlement_name(self):
        url = geocode_url('Berlin, Schleswig-Holstein')
        params = parse_qs(urlparse(url).query)
        self.assertEqual(params['name'], ['Berlin'])
        self.assertEqual(params['countryCode'], ['DE'])
        self.assertEqual(parse_qs(urlparse(geocode_url(' München, Bayern ')).query)['name'],
                         ['München'])

    def test_state_qualified_trip_uses_matching_namesake_coordinates(self):
        capital = dict(BERLIN, id=2950159, feature_code='PPLC',
                       population=3426354, admin1='Land Berlin')
        smaller = dict(BERLIN, id=9999, latitude=54.04, longitude=10.45,
                       feature_code='PPL', population=500,
                       admin1='Schleswig-Holstein')
        calls = []
        fallback = fake_fetch_log(calls, city=capital)
        def fetch(url):
            if urlparse(url).netloc == 'geocoding-api.open-meteo.com':
                calls.append(url)
                return {'results': [capital, smaller]}
            return fallback(url)
        forecast, history = build('Berlin, Schleswig-Holstein',
                                  dt.date(2026, 10, 17), dt.date(2026, 10, 20),
                                  now=NOW, fetch=fetch)
        self.assertEqual(parse_qs(urlparse(calls[0]).query)['name'], ['Berlin'])
        self.assertEqual(len(calls), 4)
        for url in calls[1:]:
            params = parse_qs(urlparse(url).query)
            self.assertEqual(params['latitude'], ['54.04'])
            self.assertEqual(params['longitude'], ['10.45'])
        self.assertIn('Berlin · 2026年10月17～20日', format_trip(forecast, history))

    def test_real_world_munich_bavaria_vs_brandenburg_namesake(self):
        # München is a state capital (GeoNames 2867714, PPLA).
        # The user's live 2026-10-15 lookup also included a Brandenburg
        # namesake. A small place need not expose 'population' at all.
        bavaria = dict(MUNICH, id=2867714, feature_code='PPLA',
                       latitude=48.13743, longitude=11.57549, population=1505005)
        brandenburg = dict(MUNICH, id=1234567, feature_code='PPL',
                           admin1='Brandenburg', latitude=52.0,
                           longitude=13.0)
        brandenburg.pop('population', None)
        for places in ([brandenburg, bavaria], [bavaria, brandenburg]):
            out = select_city({'results': places}, 'München')
            self.assertEqual(out['id'], 2867714)
            self.assertEqual(out['admin1'], 'Bayern')
            self.assertEqual(select_city({'results': places}, 'München, Germany')['id'],
                             2867714)

    def test_explicit_brandenburg_overrides_munich_state_capital(self):
        bavaria = dict(MUNICH, id=2867714, feature_code='PPLA', population=1505005)
        brandenburg = dict(MUNICH, id=1234567, feature_code='PPL',
                           admin1='Brandenburg')
        places = {'results': [bavaria, brandenburg]}
        self.assertEqual(select_city(places, 'München, Brandenburg')['id'], 1234567)
        self.assertEqual(select_city(places, 'München, Bayern')['id'], 2867714)

    def test_duplicate_state_capitals_remain_ambiguous_despite_population(self):
        a = dict(MUNICH, feature_code='PPLA', population=1505005)
        b = dict(MUNICH, feature_code='PPLA', population=500,
                 admin1='Brandenburg')
        with self.assertRaisesRegex(ValueError, '不唯一'):
            select_city({'results': [a, b]}, 'München')

    def test_noncapital_not_promoted_based_only_on_admin_seat(self):
        # A smaller county seat (PPLA2) should not automatically beat a
        # same-name place of unknown population.
        district = dict(MUNICH, name='Teststadt', feature_code='PPLA2',
                        population=5000)
        other = dict(MUNICH, name='Teststadt', feature_code='PPL',
                     admin1='Brandenburg')
        other.pop('population', None)
        with self.assertRaisesRegex(ValueError, '不唯一'):
            select_city({'results': [district, other]}, 'Teststadt')

    def test_munich_state_capital_coordinates_reach_both_weather_apis(self):
        bavaria = dict(MUNICH, id=2867714, feature_code='PPLA',
                       latitude=48.13743, longitude=11.57549, population=1505005)
        brandenburg = dict(MUNICH, id=1234567, feature_code='PPL',
                           admin1='Brandenburg', latitude=52.0,
                           longitude=13.0)
        calls = []
        fetch_fallback = fake_fetch_log(calls, city=bavaria)
        def fetch(url):
            if urlparse(url).netloc == 'geocoding-api.open-meteo.com':
                calls.append(url)
                return {'results': [brandenburg, bavaria]}
            return fetch_fallback(url)
        forecast, history = build('München', dt.date(2026, 10, 17),
                                  dt.date(2026, 10, 20),
                                  now=NOW, fetch=fetch)
        self.assertEqual(len(calls), 4)
        for weather_url in calls[1:]:
            params = parse_qs(urlparse(weather_url).query)
            self.assertEqual(params['latitude'], ['48.13743'])
            self.assertEqual(params['longitude'], ['11.57549'])
        self.assertIn('München · 2026年10月17～20日', format_trip(forecast, history))

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
        detail=format_trip(f,history,details=True)
        self.assertEqual(f['main_level'],3)
        self.assertNotIn('过去两年同期参考',text)
        self.assertIn('历史对照',detail)
        self.assertIn('更凉的白天',detail)
        self.assertIn('两年的同期记录',detail)

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


    def test_short_trip_default_keeps_forecast_alerts_but_hides_past_year_rows(self):
        calls = []
        weather = forecast_fixture([15] * 14)
        weather['daily']['precipitation_probability_max'][4] = 80
        weather['daily']['snowfall_sum'][5] = 2
        weather['daily']['wind_gusts_10m_max'][6] = 55
        f, histories = build('Berlin', dt.date(2026, 10, 17),
                             dt.date(2026, 10, 21), now=NOW,
                             fetch=fake_fetch_log(calls, current=weather))
        public = format_trip(f, histories)
        self.assertIn('主要建议：', public)
        self.assertIn('降水提醒：', public)
        self.assertIn('降雪提醒：', public)
        self.assertIn('大风提醒：', public)
        self.assertNotIn('过去两年同期参考', public)
        details = format_trip(f, histories, details=True)
        self.assertIn('过去两年同期参考', details)
        self.assertIn('2025-10-17', details)


if __name__ == '__main__':
    unittest.main()
