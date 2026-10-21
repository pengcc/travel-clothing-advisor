"""Short PostgreSQL transactions. Runtime never creates/migrates/activates DBs."""
from contextlib import contextmanager
from datetime import timedelta
from time import monotonic

from web.fixtures import BERLIN
from web.forecasts import FEATURED


class Control:
    def __init__(self, cfg, dsn, *, connect=None, readonly=False):
        self.cfg, self.dsn, self.readonly = cfg, cfg.dsn(dsn), readonly
        self.connect = connect

    @contextmanager
    def transaction(self, *, write=False):
        if write and self.readonly:
            raise ValueError('Reader cannot mutate control state')
        try:
            if self.connect is None:
                import psycopg
                connect = psycopg.connect
            else:
                connect = self.connect
            with connect(self.dsn, connect_timeout=2,
                         options='-c statement_timeout=1800 -c lock_timeout=1 -c idle_in_transaction_session_timeout=2000') as conn:
                if not write:
                    conn.execute('SET TRANSACTION READ ONLY')
                started=monotonic()
                class BoundedTransaction:
                    def execute(self,query,params=None):
                        remaining=2-(monotonic()-started)
                        if remaining<=0:
                            raise OSError('Transaction deadline exceeded')
                        # Update server deadline before each statement, rather
                        # than allowing N statements each their own 1.8 seconds.
                        conn.execute('SET LOCAL statement_timeout = '+str(max(1,int(remaining*1000))))
                        return conn.execute(query,params)
                yield BoundedTransaction()
                if monotonic()-started>=2:
                    raise OSError('Transaction deadline exceeded')
        except (ImportError, ValueError, OSError):
            raise OSError('P1 database unavailable') from None
        except Exception:
            # Never surface DSNs, server diagnostics or credential-bearing errors.
            raise OSError('P1 transaction failed; reconcile state before retry') from None

    def check(self, conn, *, lock=False):
        cfg = self.cfg
        row = conn.execute('SELECT enabled,epoch,code_version,config_digest,provider_group, '
                           'aggregate_day_limit,aggregate_month_limit,aggregate_minute_limit,heartbeat '
                           'FROM runtime_control WHERE id=true'+(' FOR UPDATE NOWAIT' if lock else '')).fetchone()
        now = conn.execute('SELECT clock_timestamp()').fetchone()[0]
        if (row is None or not row[0] or row[1:5] != (cfg.epoch,cfg.code,cfg.fingerprint,cfg.group)):
            raise ValueError('P1 control disabled or mismatched')
        return row, now, now.astimezone(BERLIN).date()

    def reconcile(self):
        with self.transaction(write=True) as c:
            row, now, day = self.check(c,lock=True)
            c.execute('UPDATE runtime_control SET heartbeat=%s WHERE id=true',(now,))
            # Bounded audit retention. Never delete current/previous-month usage.
            c.execute("DELETE FROM attempts WHERE day<%s",(day-timedelta(days=30),))
            c.execute("DELETE FROM jobs WHERE day<%s",(day-timedelta(days=30),))
            c.execute("DELETE FROM publications WHERE day<%s",(day-timedelta(days=30),))
            previous=(day.replace(day=1)-timedelta(days=1)).replace(day=1)
            for prefix,cutoff in (('minute:',str(day-timedelta(days=2))),
                                  ('day:',str(previous)),('featured:',str(previous)),
                                  ('month:',previous.strftime('%Y-%m'))):
                c.execute('DELETE FROM budget_usage WHERE provider_group=%s AND period LIKE %s AND period<%s',
                          (self.cfg.group,prefix+'%',prefix+cutoff))
            # Prior days can never be claimed/published, but retain charged attempts.
            for city in FEATURED:
                c.execute('INSERT INTO jobs(domain,day,city_id,epoch) VALUES(%s,%s,%s,%s) '
                          'ON CONFLICT DO NOTHING',(self.cfg.domain,day,city,self.cfg.epoch))
            rows = c.execute('SELECT city_id,version FROM jobs WHERE domain=%s AND day=%s AND epoch=%s',
                             (self.cfg.domain,day,self.cfg.epoch)).fetchall()
            return day,dict(rows)

    def claim(self, day):
        with self.transaction(write=True) as c:
            limits,now,today = self.check(c,lock=True)
            if day!=today:
                return None
            # Fewest previous attempts first: every city gets its initial chance.
            row = c.execute('SELECT city_id,generation FROM jobs WHERE domain=%s AND day=%s AND epoch=%s '
                            'AND version IS NULL AND (lease_until IS NULL OR lease_until<%s) '
                            'AND (retry_at IS NULL OR retry_at<=%s) '
                            'ORDER BY attempts,city_id LIMIT 1 FOR UPDATE NOWAIT',
                            (self.cfg.domain,day,self.cfg.epoch,now,now)).fetchone()
            if row is None:
                return None
            windows = [('featured:'+day.isoformat(),30),('day:'+day.isoformat(),limits[5]),
                       ('month:'+day.strftime('%Y-%m'),limits[6]),
                       ('minute:'+now.strftime('%Y-%m-%dT%H:%M'),limits[7])]
            # Control row serializes all envs of the one provider group.
            counts=[c.execute('SELECT count(*) FROM attempts WHERE provider_group=%s AND day=%s',
                              (self.cfg.group,day)).fetchone()[0]]
            counts += counts[:]
            counts.append(c.execute('SELECT count(*) FROM attempts WHERE provider_group=%s AND day>=%s',
                                    (self.cfg.group,day.replace(day=1))).fetchone()[0])
            counts.append(c.execute("SELECT count(*) FROM attempts WHERE provider_group=%s AND charged_at>=date_trunc('minute',%s::timestamptz)",
                                    (self.cfg.group,now)).fetchone()[0])
            for (period,limit),charged in zip(windows,counts):
                used = c.execute('SELECT used FROM budget_usage WHERE provider_group=%s AND period=%s',
                                 (self.cfg.group,period)).fetchone()
                if (used[0] if used else 0)<charged:
                    raise ValueError('Ledger missing or undercounted; recovery required')
                if used is not None and used[0]>=limit:
                    return None
            for period,_ in windows:
                c.execute('INSERT INTO budget_usage VALUES(%s,%s,1) ON CONFLICT(provider_group,period) '
                          'DO UPDATE SET used=budget_usage.used+1',(self.cfg.group,period))
            city,generation = row[0],row[1]+1
            c.execute('UPDATE jobs SET generation=%s,attempts=attempts+1,lease_until=%s,retry_at=NULL '
                      'WHERE domain=%s AND day=%s AND city_id=%s',
                      (generation,now+timedelta(seconds=150),self.cfg.domain,day,city))
            c.execute('INSERT INTO attempts VALUES(%s,%s,%s,%s,%s,%s)',
                      (self.cfg.domain,day,city,generation,self.cfg.group,now))
            return city,generation

    def valid(self, c, day, city, generation):
        _,now,today = self.check(c,lock=True)
        row = c.execute('SELECT generation,lease_until,epoch FROM jobs WHERE domain=%s AND day=%s AND city_id=%s '
                        'FOR UPDATE NOWAIT',(self.cfg.domain,day,city)).fetchone()
        return (today==day and row is not None and row[0]==generation and
                row[1] is not None and row[1]>now and row[2]==self.cfg.epoch),now

    def verify_claim(self, day, city, generation):
        with self.transaction(write=True) as c:
            valid,_ = self.valid(c,day,city,generation)
            if not valid:
                raise ValueError('Expired claim')

    def finish(self, day, city, generation, version=None, *, cooldown=300):
        with self.transaction(write=True) as c:
            valid,now = self.valid(c,day,city,generation)
            if not valid:
                return False
            c.execute('UPDATE jobs SET version=%s,lease_until=NULL,retry_at=%s '
                      'WHERE domain=%s AND day=%s AND city_id=%s',
                      (version,None if version else now+timedelta(seconds=max(300,cooldown)),
                       self.cfg.domain,day,city))
            return True

    def commit(self, day, versions, version):
        with self.transaction(write=True) as c:
            _,now,today = self.check(c,lock=True)
            current = dict(c.execute('SELECT city_id,version FROM jobs WHERE domain=%s AND day=%s AND epoch=%s',
                                    (self.cfg.domain,day,self.cfg.epoch)).fetchall())
            if today!=day or set(current)!=set(FEATURED) or current!=versions or any(v is None for v in current.values()):
                raise ValueError('Incomplete or stale publication')
            c.execute('INSERT INTO publications VALUES(%s,%s,%s,%s,%s) ON CONFLICT(domain,day) '
                      'DO UPDATE SET epoch=EXCLUDED.epoch,version=EXCLUDED.version,committed_at=EXCLUDED.committed_at',
                      (self.cfg.domain,day,self.cfg.epoch,version,now))

    def snapshot(self):
        with self.transaction() as c:
            row,now,day = self.check(c)
            pub = c.execute('SELECT version FROM publications WHERE domain=%s AND day=%s AND epoch=%s',
                            (self.cfg.domain,day,self.cfg.epoch)).fetchone()
            if pub:
                return day,pub[0],'complete'
            exhausted=False
            for period,limit in [('featured:'+day.isoformat(),30),('day:'+day.isoformat(),row[5]),
                                 ('month:'+day.strftime('%Y-%m'),row[6]),
                                 ('minute:'+now.strftime('%Y-%m-%dT%H:%M'),row[7])]:
                used=c.execute('SELECT used FROM budget_usage WHERE provider_group=%s AND period=%s',
                               (self.cfg.group,period)).fetchone()
                exhausted=exhausted or bool(used and used[0]>=limit)
            count = c.execute('SELECT count(*) FROM jobs WHERE domain=%s AND day=%s AND epoch=%s',
                              (self.cfg.domain,day,self.cfg.epoch)).fetchone()[0]
            healthy = row[8] is not None and (now-row[8]).total_seconds()<=10800
            status = ('scheduler_unavailable' if not healthy else
                      'quota_limited' if exhausted else
                      'forecast_preparing' if count==10 and now.astimezone(BERLIN).hour<12 else
                      'temporarily_unavailable')
            return day,None,status
