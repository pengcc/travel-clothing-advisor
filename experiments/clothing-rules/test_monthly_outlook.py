import datetime as dt
import unittest
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

from test_trip_advisor import BERLIN, MUNICH, history_fixture, fake_fetch_log, NOW
from trip_advisor import build, format_trip, validate_month_trip


def monthly_fetch(calls, *, city=BERLIN, missing_year=None, temperatures=None):
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
            rain_dates=[start.isoformat()] if self_year % 2 else [],
        )
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
        self.assertIn('整趟行程统一采用历史参考', format_trip(result, histories))
        self.assertIn('不是逐日预报', format_trip(result, histories))

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
        self.assertIn('基本衣物', report)
        self.assertIn('过去8年同期', report)
        self.assertIn('8年样本不是气候常年值', report)
        self.assertIn('不是今年的预测温度', report)
        self.assertIn('不代表今年必然下雨', report)
        self.assertIn('可准备方便增加的保暖层', report)
        self.assertNotIn('降雨概率', report)

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
        self.assertNotIn('可准备方便增加的保暖层', report)

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


if __name__ == '__main__':
    unittest.main()
