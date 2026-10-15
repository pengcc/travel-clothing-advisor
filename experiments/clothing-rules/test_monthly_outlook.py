import datetime as dt
import unittest
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

from test_trip_advisor import BERLIN, MUNICH, history_fixture, fake_fetch_log, NOW
from trip_advisor import build, format_trip, historical_summary


def monthly_fetch(calls, *, city=BERLIN, missing_year=None, temperatures=None,
                  edge_offset=0, precipitation_years=None, snow_years=None):
    """Deterministic history-only API stand-in: a future forecast is an error."""
    temps = temperatures or {
        2025: 12.8, 2024: 9, 2023: 13, 2022: 15,
        2021: 8, 2020: 6, 2019: 11, 2018: 17,
    }

    def fetch(url):
        calls.append(url)
        parsed = urlparse(url)
        q = parse_qs(parsed.query)
        if parsed.netloc == 'geocoding-api.open-meteo.com':
            return {'results': [city]}
        if parsed.netloc != 'archive-api.open-meteo.com':
            raise AssertionError('Month-ahead mode must not fetch forecasts: ' + url)
        start = dt.date.fromisoformat(q['start_date'][0])
        end = dt.date.fromisoformat(q['end_date'][0])
        self_year = start.year
        answer = history_fixture(
            start, end, temps.get(self_year, 12),
            rain_dates=[start.isoformat()] if (self_year % 2 if precipitation_years is None
                                               else self_year in precipitation_years) else [],
        )
        if snow_years and self_year in snow_years:
            answer['daily']['snowfall_sum'][0] = 1
        if edge_offset:
            for i, stamp in enumerate(answer['hourly']['time']):
                hour = int(stamp[11:13])
                if 6 <= hour <= 8 or 19 <= hour <= 22:
                    answer['hourly']['temperature_2m'][i] -= edge_offset
        if self_year == missing_year:
            answer['hourly']['temperature_2m'] = [None] * len(answer['hourly']['time'])
        return answer
    return fetch


class MonthAheadOutlookTest(unittest.TestCase):
    def test_short_trip_still_uses_original_forecast_and_two_histories(self):
        calls = []
        result, histories = build('Berlin', dt.date(2026, 10, 25),
                                  dt.date(2026, 10, 27),
                                  now=NOW, fetch=fake_fetch_log(calls))
        self.assertNotIn('kind', result)
        self.assertEqual(len(histories), 2)
        self.assertEqual(len(calls), 4)
        self.assertIn('过去两年同期参考', format_trip(result, histories))

    def test_crossing_fourteen_day_horizon_uses_history_for_entire_trip(self):
        calls = []
        result, histories = build('Berlin', dt.date(2026, 10, 25),
                                  dt.date(2026, 10, 28),
                                  now=NOW, fetch=monthly_fetch(calls))
        self.assertEqual(result['kind'], 'historical_outlook')
        self.assertEqual(len(histories), 8)
        self.assertEqual(len(calls), 9)
        self.assertTrue(all(urlparse(u).netloc != 'api.open-meteo.com' for u in calls))
        self.assertIn('出发前两周内', format_trip(result, histories))
        self.assertIn('历史同期，不是今年的具体预报', format_trip(result, histories))

    def test_all_archive_queries_era5_exact_past_intervals_and_city_coordinates(self):
        calls = []
        first, last = dt.date(2026, 10, 28), dt.date(2026, 11, 3)
        result, histories = build('München', first, last, now=NOW,
                                  fetch=monthly_fetch(calls, city=MUNICH))
        self.assertEqual(result['city'], 'München')
        self.assertEqual([h['start'] for h in histories],
                         [f'{year}-10-28' for year in range(2025, 2017, -1)])
        self.assertEqual([h['end'] for h in histories],
                         [f'{year}-11-03' for year in range(2025, 2017, -1)])
        for url in calls[1:]:
            q = parse_qs(urlparse(url).query)
            self.assertEqual(q['models'], ['era5'])
            self.assertEqual(q['latitude'], ['48.137'])
            self.assertEqual(q['longitude'], ['11.575'])
            self.assertEqual(q['timezone'], ['Europe/Berlin'])

    def test_day_30_is_accepted(self):
        calls = []
        last = NOW.date() + dt.timedelta(days=29)
        result, histories = build('Berlin', last, last, now=NOW,
                                  fetch=monthly_fetch(calls))
        self.assertEqual(result['kind'], 'historical_outlook')
        self.assertEqual(len(histories), 8)

    def test_day_31_rejected_before_external_requests(self):
        never = lambda _: self.fail('Validation must precede HTTP requests')
        with self.assertRaisesRegex(ValueError, '30个日历日'):
            build('Berlin', NOW.date() + dt.timedelta(days=14),
                  NOW.date() + dt.timedelta(days=30),
                  now=NOW, fetch=never)

    def test_invalid_past_and_reverse_windows_rejected_before_requests(self):
        never = lambda _: self.fail('Validation must precede HTTP requests')
        with self.assertRaisesRegex(ValueError, '早于'):
            build('Berlin', NOW.date() + dt.timedelta(days=20),
                  NOW.date() + dt.timedelta(days=15),
                  now=NOW, fetch=never)
        with self.assertRaisesRegex(ValueError, '之后'):
            build('Berlin', NOW.date() - dt.timedelta(days=1),
                  NOW.date() + dt.timedelta(days=18),
                  now=NOW, fetch=never)

    def test_historical_range_is_not_a_daily_forecast_or_probability(self):
        calls = []
        result, histories = build('Berlin', dt.date(2026, 10, 28),
                                  dt.date(2026, 10, 31),
                                  now=NOW, fetch=monthly_fetch(calls))
        report = format_trip(result, histories)
        self.assertIn('主要建议：', report)
        self.assertIn('过去8年同期', report)
        self.assertIn('出发前两周内', report)
        self.assertIn('不是今年的具体预报', report)
        self.assertIn('这不是今年的降雨预报', report)
        self.assertIn('怎么穿：', report)
        self.assertNotRegex(report, r'降雨概率\s*[:=]\s*\d')

    def test_near_thirteen_clothing_copy_stays_lightweight(self):
        calls = []
        uniform = {year: 12.8 for year in range(2018, 2026)}
        result, histories = build('Berlin', dt.date(2026, 10, 28),
                                  dt.date(2026, 10, 31),
                                  now=NOW, fetch=monthly_fetch(calls, temperatures=uniform))
        self.assertEqual(result['typical_daytime'], 12.8)
        report = format_trip(result, histories)
        self.assertIn('保暖程度适中的外套', report)
        self.assertIn('轻羽绒替代外套', report)
        self.assertNotIn('早晚偏冷：', report)

    def test_preferences_and_details_are_considered(self):
        for preference, phrase in (('cold', '比较怕冷'), ('hot', '比较怕热')):
            calls = []
            result, histories = build('Berlin', dt.date(2026, 10, 28),
                                      dt.date(2026, 11, 1), preference,
                                      now=NOW, fetch=monthly_fetch(calls))
            self.assertIn(phrase, format_trip(result, histories))
            details = format_trip(result, histories, details=True)
            self.assertIn('逐年历史参考', details)
            self.assertIn('2018-10-28', details)

    def test_missing_history_fails_closed_instead_of_shortening_sample(self):
        calls = []
        with self.assertRaisesRegex(ValueError, 'incomplete'):
            build('Berlin', dt.date(2026, 10, 28),
                  dt.date(2026, 11, 1), now=NOW,
                  fetch=monthly_fetch(calls, missing_year=2021))

    def test_cross_calendar_year_period_uses_correct_past_years(self):
        end_of_year = dt.datetime(2026, 12, 20, 9, tzinfo=ZoneInfo('Europe/Berlin'))
        calls = []
        result, histories = build('Berlin', dt.date(2026, 12, 30),
                                  dt.date(2027, 1, 5),
                                  now=end_of_year, fetch=monthly_fetch(calls))
        self.assertEqual(result['kind'], 'historical_outlook')
        self.assertEqual(histories[0]['start'], '2025-12-30')
        self.assertEqual(histories[0]['end'], '2026-01-05')
        self.assertEqual(histories[-1]['start'], '2018-12-30')
        self.assertEqual(histories[-1]['end'], '2019-01-05')

    def test_leap_day_is_approximated_without_crashing(self):
        leap_now = dt.datetime(2028, 2, 14, 9, tzinfo=ZoneInfo('Europe/Berlin'))
        calls = []
        result, histories = build('Berlin', dt.date(2028, 2, 29),
                                  dt.date(2028, 3, 2),
                                  now=leap_now, fetch=monthly_fetch(calls))
        self.assertEqual(result['kind'], 'historical_outlook')
        self.assertEqual(histories[0]['start'], '2027-02-28')
        self.assertEqual(histories[0]['end'], '2027-03-02')


    def test_morning_evening_hourly_temperatures_are_not_daytime_minima(self):
        # Daytime proxy and morning/evening windows are separately calculated.
        start, end = dt.date(2025, 11, 8), dt.date(2025, 11, 9)
        payload = history_fixture(start, end, temp=12)
        for i, stamp in enumerate(payload['hourly']['time']):
            hour = int(stamp[11:13])
            if hour in (6, 7, 8, 19, 20, 21, 22):
                payload['hourly']['temperature_2m'][i] = 3
        # An isolated edge-hour cold snap affects the minimum but not the
        # trip's representative morning/evening temperature.
        j = payload['hourly']['time'].index('2025-11-09T07:00')
        payload['hourly']['temperature_2m'][j] = -2
        h = historical_summary(payload, start, end, require_edges=True)
        self.assertEqual(h['typical_daytime'], 12)
        self.assertEqual(h['coldest_daytime'], 12)
        self.assertEqual(h['typical_edge'], 3)
        self.assertEqual(h['coldest_edge'], -2)

    def test_missing_edge_window_fails_monthly_but_not_short_historical_summary(self):
        start, end = dt.date(2025, 11, 8), dt.date(2025, 11, 8)
        payload = history_fixture(start, end, temp=11)
        # Evening time samples missing; leave normal daytime data intact.
        for i, stamp in enumerate(payload['hourly']['time']):
            if 19 <= int(stamp[11:13]) <= 22:
                payload['hourly']['temperature_2m'][i] = None
        with self.assertRaisesRegex(ValueError, 'morning/evening temperatures are incomplete'):
            historical_summary(payload, start, end, require_edges=True)
        brief = historical_summary(payload, start, end)
        self.assertEqual(brief['typical_daytime'], 11)
        self.assertIsNone(brief['typical_edge'])

    def test_public_outlook_prioritizes_garments_and_explains_edge_times(self):
        calls = []
        result, histories = build('Berlin', dt.date(2026, 10, 28),
                                  dt.date(2026, 11, 1),
                                  now=NOW, fetch=monthly_fetch(calls, edge_offset=6))
        summary = format_trip(result, histories)
        self.assertLess(summary.index('主要建议：'), summary.index('参考依据：'))
        self.assertIn('早晚', summary)
        self.assertIn('早晚偏冷', summary)
        self.assertIn('历史同期早晚约', summary)
        self.assertIn('接近或低于0°C', summary)
        self.assertNotIn('建议带：建议准备', summary)
        self.assertIn('不是今年的具体预报', summary)
        details = format_trip(result, histories, details=True)
        self.assertIn('逐年历史参考', details)
        self.assertIn('早晚最低样本', details)
        self.assertIn('06–08时及19–22时', details)

    def test_offseason_warm_day_and_cool_evening_uses_layers_without_winter_claim(self):
        calls = []
        result, histories = build('Berlin', dt.date(2026, 10, 28),
                                  dt.date(2026, 10, 31),
                                  now=NOW,
                                  fetch=monthly_fetch(calls, temperatures={yr: 20 for yr in range(2018,2026)},
                                                      edge_offset=8))
        summary = format_trip(result, histories)
        self.assertIn('主要建议：带薄外套', summary)
        self.assertNotIn('较厚冬季外套', summary)
        self.assertIn('外出可随身带一件薄外套', summary)


    def test_cold_early_evening_alert_even_with_small_daytime_difference(self):
        calls = []
        uniform = {year: 7.7 for year in range(2018, 2026)}
        result, history = build('Berlin', dt.date(2026, 10, 28),
                                dt.date(2026, 11, 1), now=NOW,
                                fetch=monthly_fetch(calls, temperatures=uniform, edge_offset=1.1))
        text = format_trip(result, history)
        self.assertEqual(result['typical_daytime'], 7.7)
        self.assertIn('早晚偏冷：历史同期早晚约 6.6°C', text)
        self.assertIn('主要建议：带轻羽绒', text)
        self.assertNotIn('接近或低于0°C', text)

    def test_no_rain_snow_or_early_chill_does_not_create_unneeded_warning(self):
        calls = []
        warm = {year: 24 for year in range(2018, 2026)}
        result, history = build('Berlin', dt.date(2026, 10, 28),
                                dt.date(2026, 11, 1), now=NOW,
                                fetch=monthly_fetch(calls, temperatures=warm,
                                                   precipitation_years=set(),
                                                   snow_years=set()))
        text = format_trip(result, history)
        self.assertNotIn('早晚偏冷：', text)
        self.assertNotIn('降水提醒：', text)
        self.assertNotIn('降雪提醒：', text)
        self.assertIn('主要建议：', text)

    def test_historical_precipitation_reminder_is_conditional_not_a_forecast(self):
        calls = []
        result, history = build('Berlin', dt.date(2026, 10, 28),
                                dt.date(2026, 11, 1), now=NOW,
                                fetch=monthly_fetch(calls, precipitation_years={2025, 2024}))
        text = format_trip(result, history)
        self.assertIn('降水提醒：历史同期多次出现较明显降水', text)
        self.assertIn('建议带折叠伞或防水外层', text)
        self.assertIn('不是今年的降雨预报', text)
        result, history = build('Berlin', dt.date(2026, 10, 28),
                                dt.date(2026, 11, 1), now=NOW,
                                fetch=monthly_fetch([], precipitation_years={2025}))
        self.assertNotIn('降水提醒：', format_trip(result, history))

    def test_historical_snow_warns_conditionally_without_predicting_snow(self):
        calls = []
        result, history = build('Berlin', dt.date(2026, 10, 28),
                                dt.date(2026, 11, 1), now=NOW,
                                fetch=monthly_fetch(calls, precipitation_years=set(),
                                                   snow_years={2024}))
        text = format_trip(result, history)
        self.assertIn('降雪提醒：历史同期曾出现降雪', text)
        self.assertIn('如果预报有雪', text)
        self.assertIn('鞋底防滑', text)
        self.assertNotIn('降水提醒：', text)
        self.assertIn('有降雪的历史年份 1/8', format_trip(result, history, details=True))


if __name__ == '__main__':
    unittest.main()
