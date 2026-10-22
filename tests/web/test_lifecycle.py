"""P1 OFFLINE fixtures: synthetic metadata/weather, no remote credentials."""
from dataclasses import replace
from datetime import timedelta
import os
import unittest
from unittest.mock import patch

from test_forecasts import RECORDS
from test_live import NOW, forecast
from web.forecasts import FEATURED
from web.history import encode
from web.lifecycle import Config,records,production_service,object_name,StageUnavailable
from web.publication import sha
from web.live import Unavailable
from web.refresh_weather import run,main
from web.production_store import Reader,Publisher,reader_identity


RAW=encode(RECORDS)
CFG=Config('prj_test','team_test','store_test','db.example.test','weather','shared',sha(RAW),'a'*40,1)


class Remote:
    def __init__(self):
        self.objects={}
        self.reads=0
    def get(self,name):
        self.reads+=1
        return self.objects.get(name)
    def put(self,name,raw):
        if name in self.objects:
            raise ValueError()
        self.objects[name]=raw


class ControlFixture:
    """Business flow ONLY; deliberately does not emulate PostgreSQL locking."""
    def __init__(self,now):
        self.now=now
        self.day=now.date()
        self.versions=dict.fromkeys(FEATURED)
        self.claimed=set()
        self.generation=0
        self.committed=None
        self.fail_city=None
    def reconcile(self):
        if self.day!=self.now.date():
            self.day=self.now.date()
            self.versions=dict.fromkeys(FEATURED)
            self.claimed=set()
            self.committed=None
        return self.day,dict(self.versions)
    def claim(self,day):
        city=next((c for c in FEATURED if not self.versions[c] and c not in self.claimed),None)
        if city is None:
            return None
        self.claimed.add(city)
        self.generation+=1
        return city,self.generation
    def verify_claim(self,*args):
        pass
    def finish(self,day,city,generation,version=None,**kw):
        self.versions[city]=version
        return True
    def commit(self,day,versions,version):
        assert all(versions.values())
        self.committed=version
    def snapshot(self):
        return self.day,self.committed,'forecast_preparing'


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.now=NOW
        self.control=ControlFixture(self.now)
        self.remote=Remote()
        self.calls=[]
    def provider(self,url,p,timeout):
        self.calls.append(p)
        return forecast(self.now)
    def cycle(self):
        return run(self.control,self.remote,CFG,RAW,provider=self.provider,clock=lambda:self.now)
    def app(self):
        return production_service(self.control,self.remote,CFG,RAW,clock=lambda:self.now)
    def test_ten_city_commit_rerun_and_shared_personal_source(self):
        self.assertTrue(self.cycle()['complete'])
        app=self.app()
        featured=app.featured()
        self.assertEqual(len(featured['cities']),10)
        self.assertEqual(len(self.calls),10)
        self.assertTrue(self.cycle()['complete'])
        self.assertEqual(len(self.calls),10)
        personal=app.advice(dict(view='trip',city_id='berlin',start=self.now.date().isoformat(),
                               end=(self.now.date()+timedelta(days=2)).isoformat(),preference='cold'))
        self.assertEqual(personal['data_version'],featured['cities'][0]['data_version'])
        self.assertEqual(app.city_advice(dict(view='city',city_id='berlin')),featured['cities'][0])
        with self.assertRaises(Exception):
            app.resolve('freiburg')
    def test_single_city_reads_only_its_source_after_pinned_manifest(self):
        self.cycle()
        self.remote.reads=0
        app=self.app()
        self.assertEqual(self.remote.reads,1)
        app.city_advice(dict(view='city',city_id='berlin'))
        self.assertEqual(self.remote.reads,2)
        app.featured()
        self.assertEqual(self.remote.reads,12)

    def test_nine_not_complete_then_next_cycle_reuses_nine(self):
        count=0
        def fail(url,p,timeout):
            nonlocal count
            count+=1
            if count==10:
                raise OSError()
            return self.provider(url,p,timeout)
        result=run(self.control,self.remote,CFG,RAW,provider=fail,clock=lambda:self.now)
        self.assertFalse(result['complete'])
        self.assertIsNone(self.control.committed)
        with self.assertRaises(StageUnavailable) as caught:
            self.app().featured()
        self.assertEqual(caught.exception.code,'forecast_preparing')
        self.control.claimed.clear()
        self.assertTrue(self.cycle()['complete'])
        self.assertEqual(len(self.calls),10)

    def test_personal_trip_preserves_uncommitted_publication_health(self):
        trip=dict(view='trip',city_id='berlin',start=self.now.date().isoformat(),
                  end=(self.now.date()+timedelta(days=2)).isoformat(),preference='cold')
        for health in ('forecast_preparing','quota_limited','scheduler_unavailable'):
            with self.subTest(health=health), patch.object(
                    self.control,'snapshot',return_value=(self.now.date(),None,health)):
                app=self.app()
                with self.assertRaises(StageUnavailable) as featured:
                    app.featured()
                with patch.object(app.history,'sample',wraps=app.history.sample) as history:
                    with self.assertRaises(StageUnavailable) as personal:
                        app.advice(trip)
                    history.assert_not_called()
                self.assertIs(personal.exception,featured.exception)
                self.assertEqual(personal.exception.code,health)
                self.assertTrue(str(personal.exception))
                self.assertEqual(self.remote.reads,0)
                self.assertEqual(self.calls,[])

    def test_midnight_and_corruption_refuse_advice(self):
        self.cycle()
        version=self.control.committed
        source_name=object_name(CFG,self.control.versions['berlin'])
        source=self.remote.objects[source_name]
        self.remote.objects[source_name]=b'{}'
        with self.assertRaises(Unavailable):
            self.app().advice(dict(view='trip',city_id='berlin',start=self.now.date().isoformat(),
                                  end=(self.now.date()+timedelta(days=1)).isoformat(),preference='normal'))
        self.remote.objects[source_name]=source
        self.now+=timedelta(days=1)
        with self.assertRaises(ValueError):
            self.app()
        self.now-=timedelta(days=1)
        self.remote.objects[object_name(CFG,version)]=b'{}'
        with self.assertRaises(ValueError):
            self.app()
    def test_unapproved_or_partial_metadata_rejected_before_claim(self):
        with self.assertRaises(ValueError):
            run(self.control,self.remote,CFG,encode(RECORDS[:9]),provider=self.provider)
        self.assertEqual(self.control.generation,0)
    def test_upload_failure_cannot_commit(self):
        self.remote.put=lambda *a: (_ for _ in ()).throw(OSError())
        self.assertFalse(self.cycle()['complete'])
        self.assertIsNone(self.control.committed)
    def test_disabled_no_connection_or_provider(self):
        with patch.dict(os.environ,{},clear=True),patch('web.control_store.Control') as db:
            self.assertEqual(main(),0)
            db.assert_not_called()
    def environment(self):
        names=('PROJECT_ID','OWNER_ID','STORE_ID','DB_HOST','DB_NAME','PROVIDER_GROUP',
               'RECORDS_SHA256','CODE_VERSION','EPOCH')
        values=(CFG.project,CFG.owner,CFG.store,CFG.db_host,CFG.db_name,CFG.group,
                CFG.records_digest,CFG.code,str(CFG.epoch))
        return dict({('TRAVEL_P1_'+n):v for n,v in zip(names,values)},
                    TRAVEL_P1_CONFIG_SHA256=CFG.fingerprint,TRAVEL_P1_ENABLED='true',
                    GITHUB_REPOSITORY='pengcc/travel-clothing-advisor',GITHUB_REF='refs/heads/main',
                    GITHUB_EVENT_NAME='schedule',GITHUB_SHA=CFG.code)
    def test_wrong_repo_ref_revision_flag_or_config_zero_io(self):
        env=self.environment()
        self.assertEqual(Config.environment(env,worker=True),CFG)
        for k,v in [('GITHUB_REPOSITORY','fork/repo'),('GITHUB_REF','refs/pull/1/merge'),
                    ('GITHUB_SHA','b'*40),('TRAVEL_P1_ENABLED','TRUE'),('GITHUB_EVENT_NAME','push'),
                    ('TRAVEL_P1_STORE_ID','store_wrong'),('TRAVEL_PREVIEW_NAMESPACE','preview/trial')]:
            with self.subTest(k=k),patch.dict(os.environ,dict(env,**{k:v}),clear=True),patch('web.control_store.Control') as db:
                self.assertEqual(main(),0 if k=='TRAVEL_P1_ENABLED' else 1)
                db.assert_not_called()
    def test_dsn_target_and_reader_paths(self):
        for dsn in ['postgresql://u:p@wrong/weather?sslmode=verify-full',
                    'postgresql://u:p@db.example.test/weather?sslmode=require']:
            with self.assertRaises(ValueError):
                CFG.dsn(dsn)
        r=Reader(None,CFG)
        self.assertFalse(hasattr(r,'put'))
        for path in ['preview/trial/current.json',CFG.domain+'/current.json','https://evil.test']:
            with self.assertRaises(ValueError):
                r.get(path)
        with self.assertRaises(ValueError):
            reader_identity('forged',CFG)

class ProductionEntryTests(unittest.TestCase):
    def test_real_handler_keeps_lazy_reads_inside_explicit_session(self):
        from contextlib import contextmanager
        from http.server import ThreadingHTTPServer
        import json
        import threading
        from urllib.request import urlopen
        from api.index import handler
        case=LifecycleTests()
        case.setUp()
        case.cycle()
        active=[False]
        get=case.remote.get
        def checked(name):
            if not active[0]:
                raise OSError('SDK session already closed')
            return get(name)
        case.remote.get=checked
        @contextmanager
        def session(*args,**kwargs):
            active[0]=True
            try:
                yield case.remote
            finally:
                active[0]=False
        original=production_service
        class TestHandler(handler):
            pass
        server=ThreadingHTTPServer(('127.0.0.1',0),TestHandler)
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        try:
            with patch.dict(os.environ,{'TRAVEL_P1_READER':'true','TRAVEL_P1_RECORDS_JSON':RAW.decode()}), \
                 patch('web.lifecycle.Config.environment',return_value=CFG), \
                 patch('web.control_store.Control',return_value=case.control), \
                 patch('web.production_store.production_session',session), \
                 patch('web.lifecycle.production_service',side_effect=lambda *a:original(*a,clock=lambda:NOW)):
                with urlopen('http://127.0.0.1:'+str(server.server_port)+'/api/featured') as response:
                    data=json.load(response)
                    self.assertEqual(len(data['cities']),10)
                    self.assertEqual(data['dataset_version'],case.control.committed)
        finally:
            server.shutdown();server.server_close();thread.join()
        self.assertFalse(active[0])
