"""Offline Phase 2B acceptance: synthetic provider hours, no network downloads."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import date, datetime, time, timedelta
import gzip
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from web.fixtures import BERLIN
from web.history import (ARCHIVE, LEDGER, DirectoryStore, Downloader, Library,
                         MemoryStore, bounds, digest, encode, expected_times,
                         key, months, plan, provider_hours, windows)
from web.live import Service, Unavailable, location
from test_live import Fake, NOW, geo

CITY = location(geo())


def month_data(month, value=14, edges=None):
    times = expected_times(month)
    temps = [(edges if edges is not None and (datetime.fromtimestamp(t,BERLIN).hour<9 or datetime.fromtimestamp(t,BERLIN).hour>18) else
              value(datetime.fromtimestamp(t,BERLIN)) if callable(value) else value) for t in times]
    return dict(timezone='Europe/Berlin',hourly_units=dict(temperature_2m='°C'),
                hourly=dict(time=times, temperature_2m=temps))


class Provider:
    def __init__(self):
        self.calls=[]
        self.value=14
        self.edge=None
        self.fail=None
    def __call__(self,url,p,timeout):
        self.calls.append((url,deepcopy(p),timeout))
        if self.fail: raise self.fail
        month=(date.fromisoformat(p['start_date'])+timedelta(days=1)).strftime('%Y-%m')
        return month_data(month,self.value,self.edge)


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.now=NOW
        self.store=MemoryStore()
        self.library=Library(self.store,lambda:self.now)
        self.provider=Provider()
    def worker(self,**kw):
        return Downloader(self.library,self.provider,**dict(dict(batch=120,daily=240,monthly=600,max_blocks=20),**kw))
    def jobs(self,start='2026-11-02',end='2026-11-05',city=CITY):
        return [(city,m) for m in months(windows(date.fromisoformat(start),date.fromisoformat(end)))]
    def advice(self,start='2026-11-02',end='2026-11-05',preference='normal',**kw):
        # November is inside +29 when Germany today is October 16.
        service=Service(Fake(),lambda:self.now,history=self.library,**kw)
        return service.advice(dict(view='trip',city_id='berlin',start=start,end=end,preference=preference))
    def test_reuse_overlap_sensitivity_and_month_extension(self):
        worker=self.worker()
        worker.fill(self.jobs())
        self.assertEqual(worker.stats['http_requests'],5)
        self.assertEqual(worker.stats['equivalent_calls'],30)
        d=self.advice()
        self.assertEqual(d['mode'],'historical_reference')
        self.assertEqual(d['data_status'],'complete')
        self.assertIn('ERA5',d['source'])
        self.assertIn('五年',d['caveat'])
        self.assertIsNone(d['packing_variation_notice'])
        self.assertEqual(d['warmth_indicator_level'],4)
        self.assertEqual(d['weather_fetched_at'],NOW.isoformat(timespec='seconds'))
        self.now+=timedelta(minutes=1)
        other=self.advice('2026-11-03','2026-11-06','cold')
        self.assertEqual(d['data_version'],other['data_version'])
        self.assertEqual(d['weather_fetched_at'],other['weather_fetched_at'])
        self.assertNotEqual(d['advice_generated_at'],other['advice_generated_at'])
        self.assertNotEqual(d['layers'],other['layers'])
        worker.fill(self.jobs('2026-11-03','2026-11-06'))
        self.assertEqual(worker.stats['http_requests'],0)
        worker.fill(self.jobs('2026-11-29','2026-12-03'))
        self.assertEqual(worker.stats['http_requests'],5)
        self.assertEqual(worker.stats['hits'],5)
        othercity=location(geo(2867714,name='München',latitude=48.14,longitude=11.58))
        worker.fill(self.jobs(city=othercity))
        self.assertEqual(worker.stats['http_requests'],5)
        for url,p,timeout in self.provider.calls:
            self.assertEqual(url,ARCHIVE)
            self.assertEqual(p['models'],'era5')
            self.assertEqual(p['hourly'],'temperature_2m')
            self.assertEqual(p['timeformat'],'unixtime')
            self.assertNotIn('daily',p)
            self.assertLessEqual(timeout,4)
    def test_date_mapping_acceptance_and_months(self):
        for start,end,first,fourth in [
            ('2026-12-29','2027-01-03',('2025-12-29','2026-01-03'),('2022-12-29','2023-01-03')),
            ('2028-02-28','2028-03-01',('2027-02-28','2027-03-02'),('2024-02-28','2024-03-01')),
            ('2028-02-29','2028-03-02',('2027-02-28','2027-03-02'),('2024-02-29','2024-03-02')),
        ]:
            a,b=map(date.fromisoformat,(start,end))
            ranges=windows(a,b)
            self.assertEqual(tuple(d.isoformat() for d in ranges[0]),first)
            self.assertEqual(tuple(d.isoformat() for d in ranges[3]),fourth)
            self.assertEqual(len(ranges),5)
            for x,y in ranges:
                self.assertEqual((y-x).days,(b-a).days)
                seq=[x+timedelta(days=n) for n in range((b-a).days+1)]
                self.assertEqual(len(set(seq)),len(seq))
                self.assertIn(y.strftime('%Y-%m'),months(ranges))
            self.now=datetime(2029,1,1,tzinfo=BERLIN)
            worker=self.worker(batch=240,daily=1000,monthly=2000)
            worker.fill([(CITY,m) for m in months(ranges)])
            days,_,_=self.library.sample(CITY,a,b)
            self.assertEqual(len(days),5*((b-a).days+1))
            missing=months(ranges)[-1]
            self.store.objects.pop(key(CITY,missing))
            with self.assertRaises(Unavailable):self.library.sample(CITY,a,b)
    def test_dst_full_month_validation(self):
        for month,expected in [('2025-03',743),('2025-10',745)]:
            d=month_data(month)
            self.assertEqual(len(d['hourly']['time']),expected)
            hours=provider_hours(d,month)
            self.assertEqual(len(hours['time']),expected)
            self.library.publish(CITY,month,d)
            self.assertIsNotNone(self.library.read(CITY,month))
            # Boundary padding survives fixed offset upstream range behavior.
            padded=deepcopy(d)
            padded['hourly']['time']=[d['hourly']['time'][0]-3600]+d['hourly']['time']+[d['hourly']['time'][-1]+3600]
            padded['hourly']['temperature_2m']=[14]*(expected+2)
            self.assertEqual(provider_hours(padded,month),hours)
            mutations=[lambda x:x['hourly']['time'].reverse(),
                lambda x:x['hourly']['time'].__setitem__(20,x['hourly']['time'][19]),
                lambda x:x['hourly']['temperature_2m'].__setitem__(20,None),
                lambda x:x['hourly']['temperature_2m'].__setitem__(20,True),
                lambda x:x['hourly']['temperature_2m'].__setitem__(20,float('nan')),
                lambda x:x['hourly']['temperature_2m'].__setitem__(20,70),
                lambda x:x['hourly']['temperature_2m'].pop(),
                lambda x:x['hourly_units'].update(temperature_2m='°F'),
                lambda x:x.update(timezone='UTC')]
            for mutate in mutations:
                broken=deepcopy(d);mutate(broken)
                with self.assertRaises(Unavailable):provider_hours(broken,month)
            broken=deepcopy(d)
            for field in broken['hourly']:broken['hourly'][field].pop()
            with self.assertRaises(Unavailable):self.library.publish(CITY,month,broken)
    def test_partial_restart_and_corruption(self):
        worker=self.worker(max_blocks=2)
        with self.assertRaises(Unavailable):worker.fill(self.jobs())
        self.assertEqual(worker.stats['published'],2)
        with self.assertRaises(Unavailable):self.advice()
        self.worker().fill(self.jobs())
        self.assertEqual(len(self.provider.calls),5)
        k=key(CITY,'2025-11')
        saved=self.store.objects[k]
        for bad in (b'bad',gzip.compress(b'{}'),gzip.compress(b'null')):
            self.store.objects[k]=bad
            with self.assertRaises(Unavailable):self.advice()
        self.store.objects[k]=saved
        block=json.loads(gzip.decompress(saved))
        block['body']['identity']['model']='best_match'
        block['sha256']=digest(block['body'])
        self.store.objects[k]=gzip.compress(encode(block))
        self.assertIsNone(self.library.read(CITY,'2025-11'))
        self.worker().fill(self.jobs())
        self.assertEqual(len(self.provider.calls),6)
        changed=dict(CITY,latitude=52.521)
        self.assertNotEqual(key(changed,'2025-11'),k)
        with self.assertRaises(Unavailable):self.library.sample(changed,date(2026,11,2),date(2026,11,5))
    def test_storage_outage_and_no_partial_publication(self):
        with patch.object(self.store,'get',side_effect=OSError()):
            with self.assertRaises(Unavailable):self.advice()
            with self.assertRaises(Unavailable):self.worker().fill(self.jobs())
        original=self.store.put
        def fail_month(k,v):
            if k.endswith('.gz'): raise OSError()
            original(k,v)
        with patch.object(self.store,'put',side_effect=fail_month):
            with self.assertRaises(Unavailable):self.worker().fill(self.jobs())
        self.assertFalse(any(k.endswith('.gz') for k in self.store.objects))
        self.assertEqual(json.loads(self.store.get(LEDGER))['days']['2026-10-16'],6)
    def test_quota_persistence_cooldown_and_no_retry(self):
        for status in (429,500,503):
            self.setUp()
            self.provider.fail=HTTPError(ARCHIVE,status,'upstream message',{'Retry-After':'600'},None)
            worker=self.worker()
            with self.assertRaises(Unavailable):worker.fill(self.jobs())
            self.assertEqual(len(self.provider.calls),1)
            self.assertEqual(worker.stats['failed'],1)
            self.provider.fail=None
            with self.assertRaises(Unavailable):self.worker().fill(self.jobs())
            self.assertEqual(len(self.provider.calls),1)
            self.now+=timedelta(seconds=601)
            self.worker().fill(self.jobs())
            self.assertEqual(len(self.provider.calls),6)
        self.setUp()
        with self.assertRaises(Unavailable):self.worker(batch=5).fill(self.jobs())
        self.assertEqual(len(self.provider.calls),0)
        with self.assertRaises(Unavailable):self.worker(daily=6).fill(self.jobs())
        with self.assertRaises(Unavailable):self.worker(daily=6).fill(self.jobs())
        self.assertEqual(len(self.provider.calls),1)
        self.now+=timedelta(days=1)
        with self.assertRaises(Unavailable):self.worker(monthly=6).fill(self.jobs())
        self.assertEqual(len(self.provider.calls),1)
        self.now=datetime(2026,11,1,tzinfo=BERLIN)
        self.worker().fill(self.jobs())
        self.assertEqual(len(self.provider.calls),5)
        self.store.objects[LEDGER]=b'{}'
        with self.assertRaises(Unavailable):self.worker().fill(self.jobs(city=dict(CITY,latitude=50)))
    def test_deadline_and_budgeted_on_demand(self):
        worker=self.worker(timer=lambda:0)
        def delayed(u,p,t):
            worker.timer=lambda:13
            return month_data('2021-11')
        worker.provider=delayed
        with self.assertRaises(Unavailable):worker.fill(self.jobs())
        self.assertEqual(worker.stats['published'],0)
        self.setUp()
        with self.assertRaises(Unavailable):self.advice(history_downloader=self.worker(),history_max_missing=1)
        self.assertEqual(len(self.provider.calls),0)
        d=self.advice(history_downloader=self.worker(),history_max_missing=5)
        self.assertEqual(d['mode'],'historical_reference')
        self.assertEqual(len(self.provider.calls),5)
    def test_recent_year_unavailable_no_substitution(self):
        self.now=datetime(2026,1,3,tzinfo=BERLIN)
        jobs=self.jobs('2027-01-03','2027-01-07')
        with self.assertRaises(Unavailable):self.worker().fill(jobs)
        self.assertEqual(len(self.provider.calls),4)
        self.assertIsNone(self.library.read(CITY,'2026-01'))  # latest required month is still incomplete; no older substitute
    def test_historical_winter_and_no_future_date_claims(self):
        self.provider.value=lambda d: 0 if d.year in (2021,2022) else 24
        self.worker().fill(self.jobs())
        d=self.advice()
        self.assertEqual(d['warmth_indicator_level'],2)
        self.assertIn('冬季保暖外套',d['packing_variation_notice'])
        self.assertIn('保暖内搭',d['layers'])
        for field in ('headline','layers','packing_variation_notice','packing_variation_summary','notices','caveat'):
            self.assertNotIn('2026-11',str(d[field]))
        # equal observed split, including intra-year variation, has no invented median level.
        self.store=MemoryStore();self.library=Library(self.store,lambda:self.now)
        self.provider.value=lambda d: 24 if d.day%2 else 0
        self.worker().fill(self.jobs())
        d=self.advice()
        self.assertIsNone(d['warmth_indicator_level'])
        self.assertIsNone(d['reference_temperature_c'])
        for field in ('headline','packing_variation_notice','packing_variation_summary'):
            self.assertIn('冬季保暖外套',d[field])
        self.assertIn('保暖内搭',d['layers'])
        self.assertIn('短袖',d['layers'])
    def test_near_13_headline_preserves_cold_outlier_outerwear(self):
        for typical, main, outlier, outer in (
            (13.2,4,0,'冬季保暖外套'),
            (13.2,4,8,'保暖夹克或轻羽绒'),
            (12.8,5,0,'冬季保暖外套'),
        ):
            for preference in ('normal','cold','hot'):
                with self.subTest(typical=typical,outlier=outlier,preference=preference):
                    self.setUp()
                    self.provider.value=lambda d: outlier if d.year in (2021,2022) else typical
                    self.worker().fill(self.jobs())
                    d=self.advice(preference=preference)
                    self.assertEqual(d['warmth_indicator_level'],main)
                    self.assertEqual(d['reference_temperature_c'],typical)
                    for field in ('headline','packing_variation_notice','packing_variation_summary'):
                        self.assertIn(outer,d[field])
                    self.assertIn('历史偏冷情况另备',d['layers'])
                    self.assertTrue(any('13°C' in n for n in d['notices']))
                    self.assertEqual(d['mode'],'historical_reference')
                    self.assertNotIn('2026-11',d['headline']+d['packing_variation_notice'])

    def test_near_13_override_without_meaningful_cold_outlier(self):
        # Stable, tiny boundary noise, and warm-only variation retain tolerance copy.
        for typical, other in ((13.2,13.2),(12.8,12.8),(13.2,12.8),(13.2,24)):
            with self.subTest(typical=typical,other=other):
                self.setUp()
                self.provider.value=lambda d: other if d.year in (2021,2022) else typical
                self.worker().fill(self.jobs())
                d=self.advice()
                self.assertEqual(d['headline'],'建议带保暖程度适中的外套；怕冷可用轻羽绒替代')
                self.assertTrue(any('13°C' in n for n in d['notices']))
                self.assertEqual(bool(d['packing_variation_notice']),other==24)

    def test_historical_edges_and_tolerance(self):
        self.provider.edge=0
        self.worker().fill(self.jobs())
        d=self.advice()
        self.assertIsNone(d['packing_variation_notice'])
        self.assertTrue(any('冬季保暖外套' in n for n in d['notices']))
        self.store=MemoryStore();self.library=Library(self.store,lambda:self.now)
        self.provider.edge=None;self.provider.value=12.8
        self.worker().fill(self.jobs())
        d=self.advice()
        self.assertIn('适中',d['headline'])
        self.assertTrue(any('13°C' in n for n in d['notices']))
    def test_race_single_worker_and_atomic_local_store_restart(self):
        entered,release=threading.Event(),threading.Event()
        def blocking(u,p,t):
            entered.set();release.wait(2)
            return self.provider(u,p,t)
        worker=self.worker();worker.provider=blocking
        with ThreadPoolExecutor(2) as pool:
            future=pool.submit(worker.fill,self.jobs())
            self.assertTrue(entered.wait(2))
            with self.assertRaises(Unavailable):self.worker().fill(self.jobs())
            with self.assertRaises(Unavailable):self.advice()
            release.set();future.result()
        self.assertEqual(len(self.provider.calls),5)
        with tempfile.TemporaryDirectory() as root:
            a,b=DirectoryStore(root),DirectoryStore(root)
            with a.exclusive():
                with self.assertRaises(Unavailable):
                    with b.exclusive():pass
            lib=Library(a,lambda:self.now)
            w=Downloader(lib,self.provider,batch=30,max_blocks=5)
            w.fill(self.jobs())
            lib2=Library(b,lambda:self.now)
            before=len(self.provider.calls)
            self.assertEqual(len(lib2.sample(CITY,date(2026,11,2),date(2026,11,5))[0]),20)
            self.assertEqual(len(self.provider.calls),before)
            self.assertFalse(list(Path(root).rglob('tmp*')))
    def test_rollover_planner_priority_all_cities_and_leap(self):
        for today in (date(2026,12,20),date(2027,1,1),date(2028,2,1)):
            cities=[CITY,dict(CITY,id='2867714')]
            priority=plan(cities,today)
            full=plan(cities,today,True)
            self.assertEqual(full[:len(priority)],priority)
            for n in range(30):
                required=months(windows(today+timedelta(days=n),today+timedelta(days=29)))
                self.assertTrue(all((c,m) in priority for c in cities for m in required))
            self.assertEqual(len({key(c,m) for c,m in full}),len(full))
    def test_manual_command_offline_plan_and_resume(self):
        from contextlib import redirect_stdout
        from io import StringIO
        from web.prefetch_history import main
        with tempfile.TemporaryDirectory() as root:
            manifest=Path(root)/'cities.json'
            manifest.write_text(json.dumps([geo()]))
            output=StringIO()
            with patch('web.history.urlopen',side_effect=AssertionError('Network forbidden')):
                with redirect_stdout(output):
                    code=main(['--store',root,'--cities-file',str(manifest),'--today','2026-10-16'])
            stats=json.loads(output.getvalue())
            self.assertEqual(code,0)
            self.assertEqual(stats['http_requests'],0)
            self.assertEqual(stats['featured_cities'],1)
            self.assertEqual(stats['missing'],10)  # October and November, five years
            self.assertEqual(stats['equivalent_calls'],60)
            lib=Library(DirectoryStore(root),lambda:NOW)
            Downloader(lib,self.provider,batch=6,max_blocks=1).fill([(CITY,'2021-10')])
            output=StringIO()
            with redirect_stdout(output):
                main(['--store',root,'--cities-file',str(manifest),'--today','2026-10-16'])
            self.assertEqual(json.loads(output.getvalue())['missing'],9)

    def test_invalid_saved_checksum_coverage_and_size(self):
        self.worker().fill(self.jobs())
        k=key(CITY,'2025-11');saved=self.store.objects[k]
        corrupt=json.loads(gzip.decompress(saved));corrupt['sha256']='bad'
        self.store.objects[k]=gzip.compress(encode(corrupt))
        self.assertIsNone(self.library.read(CITY,'2025-11'))
        corrupt=json.loads(gzip.decompress(saved))
        for field in corrupt['body']['hourly']:corrupt['body']['hourly'][field].pop(100)
        corrupt['sha256']=digest(corrupt['body'])
        self.store.objects[k]=gzip.compress(encode(corrupt))
        self.assertIsNone(self.library.read(CITY,'2025-11'))
        self.store.objects[k]=gzip.compress(b' '*200_001)
        self.assertIsNone(self.library.read(CITY,'2025-11'))

    def test_midnight_during_read_fails(self):
        self.worker().fill(self.jobs())
        times=iter([NOW,NOW+timedelta(days=1)])
        service=Service(Fake(),lambda:next(times),history=self.library)
        with self.assertRaisesRegex(Unavailable,'日期'):
            service.advice(dict(view='trip',city_id='berlin',start='2026-11-02',end='2026-11-05',preference='normal'))



class HistoricalAPITests(unittest.TestCase):
    def test_real_transport_against_loopback_only(self):
        from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
        from web.history import transport
        class JSONHandler(BaseHTTPRequestHandler):
            def log_message(self,*args): pass
            def do_GET(self):
                body=encode(month_data('2025-11'))
                self.send_response(200)
                self.send_header('Content-Length',str(len(body)))
                self.end_headers();self.wfile.write(body)
        server=ThreadingHTTPServer(('127.0.0.1',0),JSONHandler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            data=transport(f'http://127.0.0.1:{server.server_port}',{},2)
            self.assertEqual(provider_hours(data,'2025-11'),month_data('2025-11')['hourly'])
        finally:
            server.shutdown();server.server_close();thread.join()

    def test_http_historical_result_and_unavailable(self):
        from http.server import ThreadingHTTPServer
        from urllib.request import urlopen
        from urllib.error import HTTPError
        from web.server import Handler
        library=Library(MemoryStore(),lambda:NOW)
        provider=Provider()
        jobs=[(CITY,m) for m in months(windows(date(2026,11,2),date(2026,11,5)))]
        Downloader(library,provider,batch=30,max_blocks=5).fill(jobs)
        class TestHandler(Handler):
            service=Service(Fake(),lambda:NOW,history=library)
        server=ThreadingHTTPServer(('127.0.0.1',0),TestHandler)
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        url=f'http://127.0.0.1:{server.server_port}/api/advice?view=trip&city_id=berlin&start=2026-11-02&end=2026-11-05&preference=normal'
        try:
            with urlopen(url) as response:
                data=json.load(response)
            self.assertEqual(data['mode'],'historical_reference')
            self.assertFalse(data['fixture'])
            self.assertEqual(len(provider.calls),5)
            library.store.objects.pop(key(CITY,'2025-11'))
            with self.assertRaises(HTTPError) as error:urlopen(url)
            self.assertEqual(error.exception.code,503)
            self.assertNotIn('headline',json.load(error.exception))
            self.assertEqual(len(provider.calls),5)
        finally:
            server.shutdown();server.server_close();thread.join()


if __name__=='__main__': unittest.main()
