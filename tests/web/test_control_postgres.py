"""Opt-in REAL PostgreSQL tests: never fall back to an application DSN.

Requires TRAVEL_P1_TEST_DSN and TRAVEL_P1_TEST_ALLOW_SCHEMA_CREATE=true.
Creates/drops only a fresh p1_test_<uuid> schema in that explicitly selected DB.
No weather/Blob calls. No database/server/role provisioning.
"""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
import os
import unittest
import uuid
from urllib.parse import urlsplit

from test_lifecycle import CFG
from web.control_store import Control
from web.forecasts import FEATURED


@unittest.skipUnless(os.environ.get('TRAVEL_P1_TEST_DSN') and
                     os.environ.get('TRAVEL_P1_TEST_ALLOW_SCHEMA_CREATE')=='true',
                     'Explicit isolated PostgreSQL test target not authorized/configured')
class PostgresTests(unittest.TestCase):
    def setUp(self):
        import psycopg
        self.psycopg=psycopg
        self.dsn=os.environ['TRAVEL_P1_TEST_DSN']
        u=urlsplit(self.dsn)
        if not u.hostname or 'test' not in u.path.lower() or u.query!='sslmode=verify-full':
            self.fail('Dedicated TLS database name containing test required')
        self.cfg=replace(CFG,db_host=u.hostname,db_name=u.path[1:])
        self.schema='p1_test_'+uuid.uuid4().hex
        with psycopg.connect(self.dsn) as c:
            c.execute('CREATE SCHEMA '+self.schema)
            c.execute('SET search_path TO '+self.schema)
            c.execute(Path('sql/001_featured.sql').read_text())
            c.execute('INSERT INTO runtime_control(id,enabled,epoch,code_version,config_digest,provider_group,'
                      'aggregate_day_limit,aggregate_month_limit,aggregate_minute_limit) '
                      'VALUES(true,true,1,%s,%s,%s,42,1000,42)',
                      (self.cfg.code,self.cfg.fingerprint,self.cfg.group))
        self.addCleanup(self.cleanup)
        self.control=Control(self.cfg,self.dsn,connect=self.connect)
        self.day,_=self.control.reconcile()

    def connect(self,dsn,**kwargs):
        # Independent connection on every transaction, isolated search_path.
        opts=kwargs.pop('options','')+' -c search_path='+self.schema
        return self.psycopg.connect(dsn,options=opts,**kwargs)

    def cleanup(self):
        with self.psycopg.connect(self.dsn) as c:
            c.execute('DROP SCHEMA '+self.schema+' CASCADE')

    def test_two_connections_unique_claim_and_precharge(self):
        def claim(_):
            try:
                return Control(self.cfg,self.dsn,connect=self.connect).claim(self.day)
            except OSError:
                return None  # NOWAIT collision is an intentional bounded refusal
        with ThreadPoolExecutor(max_workers=2) as pool:
            claims=[r for r in pool.map(claim,range(2)) if r]
        self.assertGreaterEqual(len(claims),1)
        self.assertEqual(len({r[0] for r in claims}),len(claims))
        with self.control.transaction() as c:
            count=c.execute('SELECT count(*) FROM attempts').fetchone()[0]
            used=c.execute("SELECT used FROM budget_usage WHERE period LIKE 'featured:%'").fetchone()[0]
        self.assertEqual(count,len(claims))
        self.assertEqual(used,count)

    def test_thirtieth_attempt_and_rollback(self):
        with self.control.transaction(write=True) as c:
            c.execute('INSERT INTO budget_usage VALUES(%s,%s,29)',(self.cfg.group,'featured:'+str(self.day)))
        self.assertIsNotNone(self.control.claim(self.day))
        self.assertIsNone(self.control.claim(self.day))
        with self.assertRaises(OSError):
            with self.control.transaction(write=True) as c:
                c.execute('UPDATE budget_usage SET used=0')
                raise OSError('Simulated abort')
        with self.control.transaction() as c:
            used=c.execute('SELECT used FROM budget_usage WHERE period=%s',('featured:'+str(self.day),)).fetchone()[0]
        self.assertEqual(used,30)

    def test_expired_generation_cannot_commit_and_partial_refused(self):
        city,generation=self.control.claim(self.day)
        with self.control.transaction(write=True) as c:
            c.execute("UPDATE jobs SET lease_until=clock_timestamp()-interval '1 second' WHERE city_id=%s",(city,))
        self.assertFalse(self.control.finish(self.day,city,generation,'a'*64))
        with self.assertRaises(OSError):
            self.control.commit(self.day,dict.fromkeys(FEATURED,'a'*64),'b'*64)
        self.assertIsNone(self.control.snapshot()[1])

    def test_missing_ledger_does_not_reset_charged_attempts(self):
        self.control.claim(self.day)
        with self.control.transaction(write=True) as c:
            c.execute('DELETE FROM budget_usage')
        with self.assertRaises(OSError):
            self.control.claim(self.day)

    def test_disabled_epoch_and_full_commit(self):
        versions={}
        for _ in FEATURED:
            city,generation=self.control.claim(self.day)
            self.assertTrue(self.control.finish(self.day,city,generation,'a'*64))
            versions[city]='a'*64
        self.control.commit(self.day,versions,'b'*64)
        self.assertEqual(self.control.snapshot()[1],'b'*64)
        with self.control.transaction(write=True) as c:
            c.execute('UPDATE runtime_control SET epoch=2')
        with self.assertRaises(OSError):
            self.control.claim(self.day)
