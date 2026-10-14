import unittest
from pathlib import Path
from validate_clothing_rules import load, recommend, select_rows

DATA = load(Path(__file__).with_name('berlin_tempelhof_2025_sample.csv'))

def sample(start, end):
    return [row for row in DATA if start <= row['date'] <= end]

class RulesTest(unittest.TestCase):
    def test_record_count(self):
        self.assertEqual(len(DATA), 26)

    def test_winter(self):
        rec = recommend(sample('2025-02-16', '2025-02-20'))
        self.assertEqual(rec['main_level'], 6)
        self.assertTrue(any('积雪' in note for note in rec['notices']))

    def test_spring_cold_snap(self):
        rec = recommend(sample('2025-04-15', '2025-04-19'))
        self.assertEqual(rec['main_level'], 3)
        self.assertTrue(any('10.3°C' in note and '保暖' in note for note in rec['notices']))
        self.assertTrue(any('防雨' in note for note in rec['notices']))
        self.assertTrue(any('挡风' in note for note in rec['notices']))

    def test_summer_no_winter_layer(self):
        rec = recommend(sample('2025-07-01', '2025-07-07'))
        self.assertEqual(rec['main_level'], 1)
        self.assertFalse(any('可增加的保暖层' in note for note in rec['notices']))
        self.assertTrue(any('不需要因此额外携带保暖厚外套' in note for note in rec['notices']))

    def test_autumn_chill(self):
        rec = recommend(sample('2025-10-14', '2025-10-22'))
        self.assertEqual(rec['main_level'], 4)
        self.assertTrue(any('清晨/深夜' in note for note in rec['notices']))

    def test_boundary_uses_both_adjacent_levels(self):
        for t in (12.9, 13.1):
            row = {'date': '2025-01-01', 'tmax_c': t, 'tmin_c': 10,
                   'precip_mm': 0, 'snow_cm': 0, 'wind_gust_kmh': 0}
            rec = recommend([row])
            self.assertTrue(any('L4 / L5' in note for note in rec['notices']))

    def test_rejects_missing_dates(self):
        with self.assertRaisesRegex(ValueError, 'not complete'):
            select_rows(DATA, '2025-04-15', '2025-07-07')

    def test_personalization_does_not_force_hard_shift(self):
        hot = [{'date': '2025-07-02', 'tmax_c': 37.6, 'tmin_c': 17.9,
                'precip_mm': 0, 'snow_cm': 0, 'wind_gust_kmh': 0}]
        cold = [{'date': '2025-02-18', 'tmax_c': 0.4, 'tmin_c': -11.6,
                 'precip_mm': 0, 'snow_cm': 7, 'wind_gust_kmh': 0}]
        for preference in ('normal', 'cold', 'hot'):
            self.assertEqual(recommend(hot, preference)['main_level'], 1)
            self.assertEqual(recommend(cold, preference)['main_level'], 6)

if __name__ == '__main__':
    unittest.main()
