"""Deterministic service and HTTP tests: no provider network required."""
from copy import deepcopy
from datetime import datetime, timedelta, time
from http.server import ThreadingHTTPServer
import json
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import urlopen
from urllib.parse import urlencode
from web.fixtures import BERLIN
from web.live import Service, Unavailable, parse_hours, packing, variation_kind, FORECAST, GEO
from web.server import Handler

NOW = datetime(2026,10,16,10,30,tzinfo=BERLIN)


def forecast(now=NOW, values=None):
    start = datetime.combine(now.date(), time(), BERLIN)
    end = datetime.combine(now.date()+timedelta(days=14), time(), BERLIN)
    times = list(range(int(start.timestamp()), int(end.timestamp()), 3600))
    values = values or [24,14,24]+[24]*11
    temps = [values[(datetime.fromtimestamp(t,BERLIN).date()-now.date()).days] for t in times]
    return dict(timezone='Europe/Berlin', hourly_units=dict(temperature_2m='°C'), hourly=dict(time=times, temperature_2m=temps))


def geo(id=2950159, **changes):
    return dict(dict(id=id,name='Berlin',admin1='Berlin',country_code='DE',feature_code='PPLC',latitude=52.52,longitude=13.41),**changes)


class Fake:
    def __init__(self, now=NOW, values=None):
        self.now, self.data, self.calls = now, forecast(now,values), []
        self.search = [geo(2925533,name='Frankfurt am Main',admin1='Hessen'),geo(2925535,name='Frankfurt (Oder)',admin1='Brandenburg'),geo(123,country_code='US')]
        self.city = geo()
    def __call__(self, url, params):
        self.calls.append((url,params.copy()))
        return deepcopy(self.data if url==FORECAST else dict(results=self.search) if url.endswith('search') else self.city)


class LiveTests(unittest.TestCase):
    def setUp(self):
        self.fake=Fake()
        self.service=Service(self.fake,lambda:self.fake.now)
    def params(self,**kw):
        return dict(dict(view='trip',city_id='berlin',start=self.fake.now.astimezone(BERLIN).date().isoformat(),end=(self.fake.now.astimezone(BERLIN).date()+timedelta(days=2)).isoformat(),preference='normal'),**kw)
    def test_contract_outlier_and_cache(self):
        d=self.service.advice(self.params())
        self.assertEqual(d['warmth_indicator_level'],2)
        self.assertIn('2026-10-17偏冷',d['packing_variation_notice'])
        self.assertIn('外套',d['packing_variation_summary'])
        self.assertEqual(d['packing_variation_kind'], 'cold')
        self.assertFalse(d['fixture'])
        self.assertEqual(d['mode'],'forecast')
        self.assertEqual(d['weather_fetched_at'],NOW.isoformat(timespec='seconds'))
        self.fake.now+=timedelta(minutes=1)
        cold=self.service.advice(self.params(preference='cold'))
        self.assertEqual(d['weather_fetched_at'],cold['weather_fetched_at'])
        self.assertNotEqual(d['advice_generated_at'],cold['advice_generated_at'])
        self.assertEqual(d['reference_temperature_c'],cold['reference_temperature_c'])
        self.assertEqual(d['data_version'],cold['data_version'])
        self.assertNotEqual(d['packing_copy']['guidance'],cold['packing_copy']['guidance'])
        calls=[p for u,p in self.fake.calls if u==FORECAST]
        self.assertEqual(len(calls),1)
        self.assertEqual(calls[0]['hourly'],'temperature_2m')
        self.assertEqual(calls[0]['forecast_days'],14)
        self.assertEqual(calls[0]['timeformat'],'unixtime')
        self.assertNotIn('daily',calls[0])
        self.assertNotIn('latitude',d['city'])
    def test_variations(self):
        cases=[([24,14,24],2,'cold'),([14,24,14],4,'warm'),([24]*7+[14]*7,None,'mixed'),([14]*14,4,None),([12.9,13.1,13.2],4,None),([22.9,23.1,23.2],2,None),([19,22,19],3,None),([22,24,22],3,'warm')]
        for values, main, expected_kind in cases:
            with self.subTest(values=values):
                dates=[((NOW.date()+timedelta(days=i)).isoformat(),v) for i,v in enumerate(values)]
                events=[]
                m,n,s=packing(dates,events)
                self.assertEqual(m,main)
                self.assertEqual(bool(n),expected_kind is not None)
                self.assertEqual(bool(s),expected_kind is not None)
                self.assertEqual(variation_kind(events) if s else None,expected_kind)
    def test_split_clothing_covers_actual_cold_requirement(self):
        for warm, cold, outer, inner, warm_inner in [
            (24, 0, '冬季保暖外套', '保暖内搭', '短袖或薄长袖'),
            (14, 0, '冬季保暖外套', '保暖内搭', '长袖搭配薄毛衣'),
            (24, 14, '适中外套', '薄毛衣', '短袖或薄长袖'),
        ]:
            for preference in ('normal', 'cold', 'hot'):
                with self.subTest(warm=warm, cold=cold, preference=preference):
                    fake = Fake(values=[warm]*7+[cold]*7)
                    d = Service(fake, lambda: NOW).advice(self.params(end='2026-10-29', preference=preference))
                    self.assertIsNone(d['warmth_indicator_level'])
                    self.assertEqual(d['packing_variation_kind'],'mixed')
                    self.assertIsNone(d['reference_temperature_c'])
                    for field in ('headline', 'packing_variation_notice', 'packing_variation_summary'):
                        self.assertIn(outer, d[field])
                    self.assertIn(inner, d['layers'])
                    self.assertIn(warm_inner, d['layers'])
                    self.assertIn('2026-10-23', d['packing_variation_notice'])
                    self.assertIn('2026-10-16', d['packing_variation_notice'])
                    if cold == 14:
                        self.assertNotIn('冬季', d['headline']+d['layers'])

    def test_fixture_variation_kinds(self):
        from web.fixtures import advice as fixture_advice, featured as fixture_featured
        cases={'colder':'cold','warmer':'warm','split':'mixed','stable':None}
        for scenario,kind in cases.items():
            with self.subTest(scenario=scenario):
                data=fixture_advice(dict(view='city',city_id='berlin'),scenario,NOW)
                self.assertEqual(data['packing_variation_kind'],kind)
                self.assertEqual(bool(data['packing_variation_summary']),kind is not None)
                city=fixture_featured(scenario,NOW)['cities'][0]
                self.assertEqual(city['packing_variation_kind'],kind)
        historical=fixture_advice(dict(view='trip',city_id='berlin',start=NOW.date().isoformat(),
            end=(NOW.date()+timedelta(days=20)).isoformat(),preference='normal'),'colder',NOW)
        self.assertIsNone(historical['packing_variation_kind'])
        self.assertIsNone(historical['packing_variation_summary'])

    def test_city_search_skips_incomplete_candidates(self):
        valid = geo()
        for field in ('admin1', 'id', 'latitude', 'longitude', 'name'):
            broken = geo(123)
            del broken[field]
            for candidates in ([valid, broken], [broken, valid]):
                with self.subTest(field=field, candidates=candidates):
                    self.fake.search = candidates
                    cities = self.service.cities('Berlin')['cities']
                    self.assertEqual(cities, [dict(id='berlin', zh='柏林', name='Berlin', state='Berlin')])
        self.fake.search = [broken]
        with self.assertRaises(Unavailable):
            self.service.cities('Berlin')
        self.fake.search = []
        self.assertEqual(self.service.cities('Missing')['cities'], [])
        self.fake.city = broken
        with self.assertRaises(Unavailable):
            self.service.resolve('123')

    def test_unconfigured_history_or_client_coordinates(self):
        with self.assertRaisesRegex(Unavailable,'五年'):
            self.service.advice(self.params(end='2026-10-30'))
        self.assertEqual(self.fake.calls,[])
        for kw in [dict(latitude='1'),dict(preference='other'),dict(view='city'),dict(start='2026-10-15'),dict(end='2026-02-30'),dict(end='2026-10-1'),dict(start='2026-10-20'),dict(city_id='unknown'),dict(city_id='https://example.com')]:
            with self.subTest(kw=kw),self.assertRaises(ValueError):
                self.service.advice(self.params(**kw))
    def test_city_search_disambiguation_and_trusted_resolution(self):
        results=self.service.cities('frankfurt')['cities']
        self.assertEqual([c['state'] for c in results],['Hessen','Brandenburg'])
        self.assertEqual(self.fake.calls[-1][1]['countryCode'],'DE')
        self.assertEqual(self.fake.calls[-1][1]['name'],'frankfurt')
        self.assertEqual(self.service.cities('慕尼黑')['fixture'],False)
        self.assertEqual(self.fake.calls[-1][1]['name'],'München')
        self.service.resolve('berlin')
        self.assertEqual(self.fake.calls[-1],(GEO+'get',dict(id=2950159)))
        self.fake.city=geo(123,name='Teststadt',admin1='Hessen')
        self.assertEqual(self.service.resolve('123')['id'],'123')
        self.fake.city['country_code']='AT'
        with self.assertRaises(ValueError): self.service.resolve('123')
        self.fake.city=geo(234)
        with self.assertRaises(Unavailable):self.service.resolve('123')
    def test_missing_invalid_hours(self):
        def remove(d,index):
            for key in ('time','temperature_2m'):d['hourly'][key].pop(index)
        mutations=[lambda d:d.clear(),lambda d:d.update(error=True),lambda d:d.update(timezone='UTC'),lambda d:d['hourly'].update(time=[]),lambda d:d['hourly']['temperature_2m'].__setitem__(50,None),lambda d:d['hourly']['temperature_2m'].__setitem__(50,float('nan')),lambda d:d['hourly']['temperature_2m'].__setitem__(50,True),lambda d:d['hourly']['time'].reverse(),lambda d:d['hourly']['time'].__setitem__(50,d['hourly']['time'][49]),lambda d:remove(d,50),lambda d:remove(d,0),lambda d:d['hourly']['temperature_2m'].pop(),lambda d:d['hourly_units'].update(temperature_2m='°F')]
        for mutate in mutations:
            d=forecast(); mutate(d)
            with self.subTest(mutation=mutate),self.assertRaises(Unavailable):parse_hours(d,NOW)
        for shift in [-1,1]:
            with self.assertRaises(Unavailable):parse_hours(forecast(NOW+timedelta(days=shift)),NOW)
        # Missing last day's evening coverage, even for a shorter trip, is refused.
        d=forecast()
        for key in ('time','temperature_2m'): d['hourly'][key]=d['hourly'][key][:-3]
        with self.assertRaises(Unavailable):parse_hours(d,NOW)
    def test_edge_layers_tolerance_and_split_temperature(self):
        self.fake.data=forecast(values=[14]*14)
        for i,t in enumerate(self.fake.data['hourly']['time']):
            if datetime.fromtimestamp(t,BERLIN).hour==20:
                self.fake.data['hourly']['temperature_2m'][i]=7
        d=self.service.advice(self.params())
        self.assertTrue(any('20时' in note and '保暖夹克' in note for note in d['notices']))
        self.assertIsNone(d['packing_variation_notice'])
        f=Fake(values=[12.8]*14)
        near=Service(f,lambda:NOW).advice(self.params())
        self.assertIn('适中',near['headline'])
        self.assertTrue(any('13°C' in n for n in near['notices']))
        f=Fake(values=[24]*7+[14]*7)
        split=Service(f,lambda:NOW).advice(self.params(end='2026-10-29'))
        self.assertIsNone(split['reference_temperature_c'])
        self.assertIsNone(split['warmth_indicator_level'])
        self.assertTrue(split['packing_variation_notice'])

    def test_midnight_during_acquisition_and_transport(self):
        from unittest.mock import patch
        from web.live import fetch_json
        clock=iter([NOW,NOW+timedelta(days=1)])
        with self.assertRaisesRegex(Unavailable,'日期'):
            Service(self.fake,lambda:next(clock)).advice(self.params())
        for code in [429,500,503]:
            with patch('web.live.urlopen',side_effect=HTTPError(FORECAST,code,'failed',None,None)) as call:
                with self.assertRaises(Unavailable):fetch_json(FORECAST,{})
                self.assertEqual(call.call_count,1)
        with patch('web.live.urlopen',side_effect=TimeoutError()):
            with self.assertRaises(Unavailable):fetch_json(FORECAST,{})

    def test_dst_both_directions(self):
        for month,day,expected in [(3,25,335),(10,20,337)]:
            now=datetime(2026,month,day,10,tzinfo=BERLIN)
            data=forecast(now)
            self.assertEqual(len(data['hourly']['time']),expected)
            hours=parse_hours(data,now)
            # Every needed local daytime hour survives offset transition.
            for n in range(14):
                date=now.date()+timedelta(days=n)
                self.assertEqual(sum(d.date()==date and 9<=d.hour<=18 for d,v in hours),10)
    def test_remaining_today_and_edge_only(self):
        self.fake.data=forecast(values=[24]*14)
        # Huge past cold values must not affect future advice.
        for i,t in enumerate(self.fake.data['hourly']['time']):
            if datetime.fromtimestamp(t,BERLIN)<NOW:self.fake.data['hourly']['temperature_2m'][i]=-20
        self.assertEqual(self.service.advice(self.params(end='2026-10-16'))['reference_temperature_c'],24)
        self.fake.now=NOW.replace(hour=19,minute=30)
        d=self.service.advice(self.params(end='2026-10-16'))
        self.assertIsNone(d['reference_temperature_c'])
        self.assertIsNone(d['warmth_indicator_level'])
        self.assertIn('白天已过',d['headline'])
        self.assertIn('晚间',d['headline'])
        self.fake.now=NOW.replace(hour=22,minute=30)
        with self.assertRaises(Unavailable):self.service.advice(self.params(end='2026-10-16'))
    def test_midnight_and_late_uncertainty(self):
        from datetime import timezone
        self.fake.now=datetime(2026,10,15,22,0,tzinfo=timezone.utc)
        self.assertEqual(self.service.advice(self.params())['start'],'2026-10-16')
        d=self.service.advice(self.params(end='2026-10-29'))
        self.assertIn('第8–14天',d['caveat'])
        self.fake.now=datetime(2026,10,17,0,0,tzinfo=BERLIN)
        self.fake.data=forecast(self.fake.now)
        self.service.advice(self.params())
        self.assertEqual(sum(u==FORECAST for u,p in self.fake.calls),2)
    def test_errors_never_fallback(self):
        for error in [TimeoutError(),OSError(),HTTPError(FORECAST,429,'limit',None,None),HTTPError(FORECAST,500,'bad',None,None)]:
            def fail(u,p):raise error
            with self.subTest(error=error),self.assertRaises(Unavailable):Service(fail,lambda:NOW).advice(self.params())
        self.fake.data={'error':True}
        with self.assertRaises(Unavailable):self.service.advice(self.params())


class APITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fake=Fake()
        class TestHandler(Handler):
            service=Service(cls.fake,lambda:cls.fake.now)
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),TestHandler)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.base='http://127.0.0.1:'+str(cls.server.server_port)
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join()
    def request(self,path):
        try:
            with urlopen(self.base+path) as r:return r.status,json.load(r)
        except HTTPError as e:return e.code,json.load(e)
    def test_city_search_partial_and_unusable_http_results(self):
        original = self.fake.search
        try:
            broken = geo(123)
            del broken['admin1']
            self.fake.search = [broken, geo()]
            code, data = self.request('/api/cities?q=Berlin')
            self.assertEqual(code, 200)
            self.assertEqual(data['cities'], [dict(id='berlin', zh='柏林', name='Berlin', state='Berlin')])
            self.fake.search = [broken]
            code, data = self.request('/api/cities?q=Berlin')
            self.assertEqual(code, 503)
            self.assertNotIn('cities', data)
            self.fake.search = []
            code, data = self.request('/api/cities?q=Missing')
            self.assertEqual((code, data['cities']), (200, []))
        finally:
            self.fake.search = original

    @patch('web.fixtures.now_berlin', return_value=NOW)
    def test_routes(self, _clock):
        p=dict(view='trip',city_id='berlin',start='2026-10-16',end='2026-10-18',preference='normal')
        code,d=self.request('/api/advice?'+urlencode(p));self.assertEqual(code,200);self.assertFalse(d['fixture'])
        for extra in ['&city_id=munich','&latitude=1','&fixture=']:
            code,d=self.request('/api/advice?'+urlencode(p)+extra);self.assertEqual(code,400)
        code,d=self.request('/api/advice?'+urlencode(dict(p,end='2026-10-30')));self.assertEqual(code,503);self.assertNotIn('headline',d);self.assertEqual(d['code'],'history_incomplete')
        code,d=self.request('/api/cities?q=frankfurt');self.assertEqual(code,200);self.assertEqual(len(d['cities']),2)
        code,d=self.request('/api/advice?view=city&city_id=berlin');self.assertEqual(code,503);self.assertNotIn('headline',d)
        code,d=self.request('/api/advice?view=city&city_id=berlin&fixture=stable');self.assertEqual(code,200);self.assertTrue(d['fixture']);self.assertIsNone(d['weather_fetched_at'])
        code,d=self.request('/api/featured');self.assertEqual(code,503);self.assertNotIn('cities',d);self.assertEqual(d['code'],'temporarily_unavailable')
        code,d=self.request('/api/featured?fixture=default');self.assertEqual(code,200);self.assertTrue(d['fixture'])
        code,d=self.request('/api/advice?'+urlencode(p)+'&fixture=stable');self.assertEqual(code,200);self.assertTrue(d['fixture'])
        code,d=self.request('/api/cities?q=x&q=y');self.assertEqual(code,400)
        code,d=self.request('/api/city?city_id=berlin');self.assertEqual(code,200);self.assertEqual(d['city']['id'],'berlin')


if __name__=='__main__':unittest.main()
