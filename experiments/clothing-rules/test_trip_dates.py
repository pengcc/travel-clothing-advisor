"""Date-scoped Berlin forecast: no network access is required for these tests."""
import datetime as dt
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from zoneinfo import ZoneInfo

from forecast_advice import format_advice, format_user_advice, process, select_trip_rows
from test_forecast_advice import fixture, NOW

ROOT = Path(__file__).resolve().parent
AT_EVENING = dt.datetime(2026, 10, 14, 20, 0, tzinfo=ZoneInfo('Europe/Berlin'))


class TravelDatesTest(unittest.TestCase):
    def test_only_travel_days_affect_main_clothing_level(self):
        temps = [32] * 14
        temps[3:5] = [10, 11]
        result = process(fixture(temps), NOW,
                         start_date='2026-10-17', end_date='2026-10-18')
        self.assertEqual(result['dates'], ['2026-10-17', '2026-10-18'])
        self.assertEqual(result['main_level'], 5)
        text = format_user_advice(result)
        self.assertIn('2026年10月17～18日穿衣建议', text)
        self.assertIn('保暖中间层', text)
        self.assertNotIn('10月14日', text.split('穿衣建议')[0])

    def test_rain_wind_snow_outside_trip_are_excluded(self):
        f = fixture()
        f['daily']['precipitation_probability_max'][12] = 90
        f['daily']['wind_gusts_10m_max'][12] = 80
        f['daily']['snowfall_sum'][12] = 4
        result = process(f, NOW, start_date='2026-10-15', end_date='2026-10-17')
        self.assertEqual(result['rain_dates'], [])
        self.assertEqual(result['wind_dates'], [])
        self.assertEqual(result['snow_dates'], [])
        text = format_user_advice(result)
        self.assertNotIn('降水提醒', text)
        self.assertNotIn('大风提醒', text)
        self.assertNotIn('降雪提醒', text)

    def test_requested_rain_day_kept(self):
        f = fixture()
        f['daily']['precipitation_probability_max'][4] = 75
        result = process(f, NOW, start_date='2026-10-17', end_date='2026-10-19')
        self.assertEqual(result['rain_dates'], ['2026-10-18'])
        self.assertIn('10月18日有降水可能', format_user_advice(result))

    def test_original_cold_spell_remains_visible_for_overlapping_trip(self):
        temps = [14.1] * 14
        temps[3:6] = [12.4, 12.3, 11.5]
        result = process(fixture(temps), NOW,
                         start_date='2026-10-15', end_date='2026-10-25')
        self.assertTrue(set(['2026-10-17', '2026-10-18', '2026-10-19'])
                        .issubset(result['cold_dates']))
        self.assertIn('10月17～19日', format_user_advice(result))

    def test_trip_in_second_week_still_warns_of_long_range_cold(self):
        temps = [16] * 14
        temps[13] = 10
        result = process(fixture(temps), NOW,
                         start_date='2026-10-21', end_date='2026-10-27')
        self.assertEqual(result['cold_dates'], ['2026-10-27'])
        text = format_user_advice(result)
        self.assertIn('后期留意：10月27日', text)
        self.assertNotIn('降温提醒：10月27日', text)
        details = format_advice(result)
        self.assertIn('指定旅行日期', details)
        self.assertIn('2026-10-21: 16°C L4 · 后期预报需复查', details)
        self.assertNotIn('2026-10-14:', details)

    def test_far_only_rain_carries_uncertainty(self):
        f = fixture()
        f['daily']['precipitation_probability_max'][10] = 70
        result = process(f, NOW, start_date='2026-10-23', end_date='2026-10-25')
        self.assertIn('日期较远，临近再确认', format_user_advice(result))

    def test_single_day_trip_is_not_a_fourteen_day_report(self):
        result = process(fixture(), NOW,
                         start_date='2026-10-16', end_date='2026-10-16')
        self.assertEqual(len(result['days']), 1)
        self.assertIn('2026年10月16日穿衣建议', format_user_advice(result))
        self.assertIn('指定旅行日期穿衣建议', format_advice(result))
        self.assertNotIn('未来14个日历日穿衣建议', format_advice(result))

    def test_today_after_daytime_is_not_treated_as_future_trip(self):
        result = process(fixture(), AT_EVENING,
                         start_date='2026-10-14', end_date='2026-10-15')
        self.assertEqual(result['dates'], ['2026-10-14', '2026-10-15'])
        self.assertIsNone(result['days'][0]['daytemp'])
        self.assertIn('2026年10月15日穿衣建议', format_user_advice(result))

    def test_only_elapsed_today_raises(self):
        with self.assertRaisesRegex(ValueError, 'No usable future daytime forecast'):
            process(fixture(), AT_EVENING,
                    start_date='2026-10-14', end_date='2026-10-14')

    def test_dates_must_be_complete(self):
        with self.assertRaisesRegex(ValueError, '同时提供'):
            process(fixture(), NOW, start_date='2026-10-16')
        with self.assertRaisesRegex(ValueError, '同时提供'):
            process(fixture(), NOW, end_date='2026-10-16')

    def test_rejects_reversed_dates(self):
        with self.assertRaisesRegex(ValueError, '开始日期'):
            process(fixture(), NOW, start_date='2026-10-19', end_date='2026-10-17')

    def test_rejects_out_of_horizon_dates(self):
        for start, end in [('2026-10-13', '2026-10-16'),
                           ('2026-10-25', '2026-10-28')]:
            with self.subTest(start=start, end=end):
                with self.assertRaisesRegex(ValueError, '超出覆盖范围'):
                    process(fixture(), NOW, start_date=start, end_date=end)

    def test_rejects_invalid_date_strings(self):
        with self.assertRaisesRegex(ValueError, 'YYYY-MM-DD'):
            process(fixture(), NOW, start_date='nonsense', end_date='2026-10-20')

    def test_default_mode_still_covers_fourteen_calendar_days(self):
        result = process(fixture(), NOW)
        self.assertEqual(len(result['days']), 14)
        self.assertEqual(result['dates'][0], '2026-10-14')
        self.assertIn('未来14个日历日', format_advice(result))

    def test_missing_hourly_temperature_outside_trip_is_irrelevant(self):
        f = fixture()
        for i, stamp in enumerate(f['hourly']['time']):
            if stamp.startswith('2026-10-25T'):
                f['hourly']['temperature_2m'][i] = None
        result = process(f, NOW, start_date='2026-10-17', end_date='2026-10-19')
        self.assertEqual(len(result['days']), 3)

    def test_missing_hourly_temperature_during_trip_is_rejected(self):
        f = fixture()
        for i, stamp in enumerate(f['hourly']['time']):
            if stamp.startswith('2026-10-18T'):
                f['hourly']['temperature_2m'][i] = None
        with self.assertRaisesRegex(ValueError, 'Missing daytime forecast'):
            process(f, NOW, start_date='2026-10-17', end_date='2026-10-19')

    def test_actual_129c_trip_uses_moderate_outerwear_not_required_down(self):
        # Reproduces the traveler-visible 2026-10-15 run's ~12.9°C
        # representative daytime temperature using synthetic hourly data.
        # The raw API forecast was not saved.
        temps = [32] * 14
        temps[3:7] = [12.9, 12.9, 12.9, 12.9]
        out = process(fixture(temps), NOW,
                      start_date='2026-10-17', end_date='2026-10-20')
        self.assertEqual(out['main_level'], 5)
        self.assertEqual(out['typical_daytime'], 12.9)
        text = format_user_advice(out)
        self.assertIn('2026年10月17～20日穿衣建议', text)
        self.assertIn('长袖搭配毛衣或抓绒', text)
        self.assertIn('保暖程度适中的外套', text)
        self.assertIn('轻羽绒替代外套', text)
        self.assertIn('接近厚度分界', text)
        self.assertIn('一般不必优先准备厚冬季羽绒服', text)
        self.assertNotIn('建议准备长袖、保暖中间层，以及保暖外套或轻羽绒', text)

    def test_131c_trip_does_not_switch_to_incompatible_clothing(self):
        low = [32] * 14
        high = [32] * 14
        low[3:7] = [12.9] * 4
        high[3:7] = [13.1] * 4
        a = format_user_advice(process(fixture(low), NOW,
                             start_date='2026-10-17', end_date='2026-10-20'))
        b = format_user_advice(process(fixture(high), NOW,
                             start_date='2026-10-17', end_date='2026-10-20'))
        self.assertIn('建议长袖搭配毛衣或抓绒', a)
        self.assertIn('建议长袖搭配毛衣或抓绒', b)
        self.assertIn('轻羽绒替代外套', a)
        self.assertIn('轻羽绒替代外套', b)

    def test_significantly_colder_trip_keeps_stronger_outerwear(self):
        temps = [32] * 14
        temps[3:7] = [9.5] * 4
        out = process(fixture(temps), NOW,
                      start_date='2026-10-17', end_date='2026-10-20')
        self.assertEqual(out['main_level'], 5)
        text = format_user_advice(out)
        self.assertIn('保暖外套或轻羽绒', text)
        self.assertNotIn('接近厚度分界', text)
        self.assertNotIn('一般不必优先准备厚冬季羽绒服', text)

    def test_near_boundary_does_not_hide_real_cold_day(self):
        temps = [32] * 14
        temps[3:8] = [12.9, 12.9, 0, 12.9, 12.9]
        out = process(fixture(temps), NOW,
                      start_date='2026-10-17', end_date='2026-10-21')
        self.assertEqual(out['main_level'], 5)
        text = format_user_advice(out)
        self.assertIn('接近厚度分界', text)
        self.assertIn('冬季保暖内搭', text)
        self.assertIn('较厚的冬季外套', text)
        self.assertNotIn('一般不必优先准备厚冬季羽绒服', text)

    def test_short_near_term_trip_has_no_irrelevant_week_two_warning(self):
        out = process(fixture(), NOW,
                      start_date='2026-10-17', end_date='2026-10-20')
        self.assertNotIn('第8～14天', format_advice(out))
        self.assertNotIn('第8～14天', format_user_advice(out))

    def test_far_only_trip_explicitly_discloses_lower_confidence(self):
        out = process(fixture(), NOW,
                      start_date='2026-10-23', end_date='2026-10-25')
        text = format_user_advice(out)
        self.assertIn('行程全部处于预报第8～14天', text)
        self.assertIn('临近出发复查', text)
        self.assertIn('行程包含预报第8～14天', format_advice(out))

    def test_trip_spanning_week_boundary_qualifies_only_later_days(self):
        out = process(fixture(), NOW,
                      start_date='2026-10-19', end_date='2026-10-23')
        text = format_user_advice(out)
        self.assertIn('行程后段涉及预报第8～14天', text)
        self.assertNotIn('行程全部处于预报第8～14天', text)
        self.assertIn('2026年10月19～23日穿衣建议', text)

    def test_cli_date_arguments_work_with_offline_fixture(self):
        with tempfile.TemporaryDirectory() as td:
            saved = Path(td) / 'forecast.json'
            saved.write_text(json.dumps(fixture()), encoding='utf-8')
            result = subprocess.run([
                sys.executable, str(ROOT / 'forecast_advice.py'),
                '--fixture', str(saved), '--now', NOW.isoformat(),
                '--start', '2026-10-17', '--end', '2026-10-19',
            ], capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('2026年10月17～19日穿衣建议', result.stdout)

    def test_cli_rejects_outside_horizon_without_truncating_trip(self):
        with tempfile.TemporaryDirectory() as td:
            saved = Path(td) / 'forecast.json'
            saved.write_text(json.dumps(fixture()), encoding='utf-8')
            result = subprocess.run([
                sys.executable, str(ROOT / 'forecast_advice.py'),
                '--fixture', str(saved), '--now', NOW.isoformat(),
                '--start', '2026-10-23', '--end', '2026-11-05',
            ], capture_output=True, text=True, check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('超出覆盖范围', result.stderr)


if __name__ == '__main__':
    unittest.main()
