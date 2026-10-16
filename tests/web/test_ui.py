import unittest
from datetime import datetime, timedelta
from web.fixtures import BERLIN, CITIES, advice, featured, validate, window

NOW = datetime(2026, 10, 15, 12, tzinfo=BERLIN)


class FixtureContractTests(unittest.TestCase):
    def params(self, **kw):
        return dict(dict(view='trip', city_id='berlin', start='2026-10-15', end='2026-10-17', preference='normal'), **kw)

    def test_city_discards_personal_inputs(self):
        p = validate(self.params(view='city', start='invalid', end='invalid', preference='hot'), NOW)
        self.assertEqual((p['start'], p['end'], p['preference']), ('2026-10-15', '2026-10-28', 'normal'))

    def test_variations_and_independent_indicator(self):
        for scenario, level, notice in [('stable', 4, False), ('colder', 2, True), ('warmer', 4, True), ('split', None, True)]:
            with self.subTest(scenario=scenario):
                d = advice(self.params(end='2026-10-28'), scenario, NOW)
                self.assertEqual(d['warmth_indicator_level'], level)
                self.assertEqual(bool(d['packing_variation_notice']), notice)
                self.assertEqual(bool(d['packing_variation_summary']), notice)

    def test_card_detail_consistency(self):
        snapshot = featured(now=NOW)
        self.assertEqual(len(snapshot['cities']), 10)
        for card in snapshot['cities']:
            result = advice(dict(view='city', city_id=card['city']['id']), now=NOW)
            for key in ['warmth_indicator_level', 'packing_variation_notice', 'packing_variation_summary', 'data_version', 'start', 'end']:
                self.assertEqual(card[key], result[key])

    def test_forecast_historical_boundary(self):
        for end, mode in [('2026-10-28', 'forecast'), ('2026-10-29', 'historical_reference'), ('2026-11-13', 'historical_reference')]:
            d = advice(self.params(end=end), now=NOW)
            self.assertEqual(d['mode'], mode)
            if mode == 'historical_reference':
                self.assertIsNone(d['packing_variation_notice'])
                self.assertIn('不是旅行当天', d['caveat'])

    def test_invalid_inputs(self):
        for kw in [dict(start='2026-10-14'), dict(end='2026-11-14'), dict(start='2026-10-19'), dict(end='2026-02-30'), dict(end='2026-1-1'), dict(preference='other'), dict(city_id='unknown'), dict(view='other')]:
            with self.subTest(kw=kw), self.assertRaises(ValueError):
                validate(self.params(**kw), NOW)

    def test_berlin_midnight_and_dst(self):
        from datetime import timezone
        for instant, expected in [('2026-10-15T21:59:00+00:00', '2026-10-15'), ('2026-10-15T22:00:00+00:00', '2026-10-16'), ('2026-10-25T23:00:00+00:00', '2026-10-26')]:
            now = datetime.fromisoformat(instant)
            w = window(now)
            self.assertEqual(w['today'], expected)
            self.assertEqual((datetime.fromisoformat(w['forecast_end']) - datetime.fromisoformat(w['today'])).days, 13)
        with self.assertRaises(ValueError):
            validate(self.params(), NOW + timedelta(days=1))

    def test_no_fabricated_weather_timestamp(self):
        d = advice(self.params(), now=NOW)
        self.assertTrue(d['fixture'])
        self.assertIsNone(d['weather_fetched_at'])
        self.assertIn('未查询历史数据', advice(self.params(end='2026-11-01'), now=NOW)['caveat'])

    def test_sensitivity_changes_layers_not_weather(self):
        normal = advice(self.params(), now=NOW)
        cold = advice(self.params(preference='cold'), now=NOW)
        self.assertEqual(normal['reference_temperature_c'], cold['reference_temperature_c'])
        self.assertNotEqual(normal['layers'], cold['layers'])

    def test_short_scenario_is_not_mislabeled(self):
        with self.assertRaises(ValueError):
            advice(self.params(), 'split', NOW)
        self.assertIsNone(advice(self.params(end='2026-10-15'), now=NOW)['packing_variation_notice'])

    def test_one_clock_instant_per_snapshot(self):
        from unittest.mock import patch
        with patch('web.fixtures.now_berlin', side_effect=[NOW, NOW + timedelta(days=1)]) as clock:
            snapshot = featured()
            self.assertEqual(clock.call_count, 1)
            self.assertTrue(all(c['start'] == snapshot['today'] and c['end'] == snapshot['forecast_end'] for c in snapshot['cities']))

    def test_failure_and_stale(self):
        with self.assertRaises(LookupError):
            advice(self.params(), 'unavailable', NOW)
        self.assertEqual(advice(self.params(), 'stale', NOW)['data_status'], 'stale')


if __name__ == '__main__':
    unittest.main()
