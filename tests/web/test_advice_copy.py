"""Copy-only presentation cannot erase decided risks or invent temperature triggers."""
import unittest

from unittest.mock import patch

from web.advice_copy import packing_copy
from web.live import packing


class CopyPresentationTests(unittest.TestCase):
    def test_collecting_copy_events_preserves_packing_decisions(self):
        for values in ([29,24,29], [24,14,24], [14,24,14], [24]*7+[0]*7, [13.2,12.8,13.2], [8]*4+[0]):
            days = [(f'2026-10-{i+16:02}', value) for i,value in enumerate(values)]
            events = []
            self.assertEqual(packing(days), packing(days, events))
            self.assertEqual(bool(events), bool(packing(days)[1]))

    def test_l1_to_l2_cooling_adds_only_the_uncovered_thin_long_sleeve(self):
        for kind, when, condition in (('cold', '2026-07-02', '偏冷'),
                                      ('edge', '07月01日 20时前后', '较凉')):
            with self.subTest(kind=kind):
                result = packing_copy(1, [dict(kind=kind, level=2, when=when)])
                self.assertEqual(result['outer'], '不必带厚外套')
                self.assertEqual(result['inner'], '短袖、轻薄透气下装')
                self.assertEqual(result['risks'], [f'{when}{condition}：另备薄长袖。'])
                self.assertNotIn('另备不必', ' '.join(result['risks']))

    def test_shared_nonpositive_coat_need_does_not_invent_a_packable_coat(self):
        result = packing_copy(2, [dict(kind='edge', level=2, when='早晚')])
        self.assertEqual(result['risks'], ['早晚较凉：可加已备的薄长袖。'])
        self.assertNotIn('厚外套', result['risks'][0])
        self.assertNotIn('保暖层', result['risks'][0])

    def test_same_positive_garment_is_deduplicated_even_across_level_ids(self):
        # A shared physical requirement must not become another coat if labels evolve.
        with patch.dict('web.advice_copy.COAT_ITEMS', {4: '可脱的薄外套'}):
            result = packing_copy(3, [dict(kind='cold', level=4, when='较冷日')])
        self.assertEqual(result['risks'], ['较冷日偏冷：另备薄毛衣。'])

    def test_cold_outer_inner_and_already_covered_evening_are_not_repeated(self):
        result = packing_copy(5, [dict(kind='cold', level=6, when='历史同期'),
                                  dict(kind='warm', level=5, when='历史同期'),
                                  dict(kind='edge', level=6, when='历史同期早晚')])
        text = ' '.join([result['outer'], result['inner'], *result['risks']])
        for garment in ('保暖夹克或轻羽绒', '冬季保暖外套', '保暖内搭', '毛衣或抓绒'):
            self.assertEqual(text.count(garment), 1)
        self.assertIn('历史同期早晚较凉：外出带上已备的保暖层。', result['risks'])
        self.assertIn('历史同期偏暖：减薄内搭、脱下外层。', result['risks'])

    def test_colder_evening_adds_uncovered_clothing(self):
        result = packing_copy(2, [dict(kind='edge', level=6, when='10月16日 20时前后')])
        self.assertIn('冬季保暖外套、保暖内搭、毛衣或抓绒', result['risks'][0])
        self.assertIn('20时前后较凉', result['risks'][0])

    def test_split_keeps_full_cold_and_warm_outfits_without_usual_claim(self):
        result = packing_copy(None, [dict(kind='cold', level=6, when='历史同期'),
                                     dict(kind='warm', level=2, when='历史同期')], split=(6,2))
        self.assertEqual(result['title'], '分情况准备')
        self.assertIn('冬季保暖外套', result['outer'])
        self.assertIn('保暖内搭', result['inner'])
        self.assertIn('短袖或薄长袖', result['inner'])
        self.assertNotIn('冬季保暖外套', ' '.join(result['risks']))

    def test_evening_only_and_boundary_copy_keep_their_distinct_meaning(self):
        self.assertEqual(packing_copy(6, [], evening_only=True)['title'], '剩余晚间准备')
        boundary = packing_copy(4, [], boundary=True)
        self.assertIn('怕冷可用轻羽绒替代', boundary['outer'])
        self.assertIn('13°C', boundary['boundary'])
        self.assertEqual(boundary['risks'], [])

    def test_guidance_preferences_and_winter_coverage(self):
        for pref in ('normal', 'cold', 'hot'):
            plain = packing_copy(5, [], preference=pref)['guidance']
            self.assertIn('如果已有', plain['alternative'])
            self.assertIn('实际保暖能力适合预计活动', plain['alternative'])
            self.assertIn('替代', plain['alternative'])
            self.assertIn('不必再多带', plain['alternative'])
            self.assertTrue(plain['personal_layer'])
            for kind in ('cold', 'edge'):
                winter = packing_copy(5, [dict(kind=kind, level=6, when='偏冷时')], preference=pref)
                self.assertEqual(winter['guidance']['alternative'], '')
                self.assertIn('冬季保暖外套、保暖内搭', winter['risks'][0])
                self.assertIn('需保暖下装覆盖', winter['guidance']['trousers_shoes'])
            self.assertNotIn('多备一层', plain['personal_layer'])

    def test_guidance_does_not_invent_usual_level_or_weather(self):
        for main, options in [(None, dict(split=(6, 2))), (6, dict(evening_only=True)),
                              (4, dict(boundary=True)), (1, {}), (2, {}), (3, {})]:
            result = packing_copy(main, [], **options)
            self.assertEqual(result['guidance']['alternative'], '')
            if main in (1, 2, 3):
                self.assertEqual(result['guidance']['trousers_shoes'], '')
            text = result['guidance']['trousers_shoes']
            if text:
                self.assertIn('如另查预报提示雨雪', text)
                self.assertIn('如有结冰风险', text)
            self.assertNotIn('通常', ' '.join(result['guidance'].values()))


if __name__ == '__main__':
    unittest.main()
