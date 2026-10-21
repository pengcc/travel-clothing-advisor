"""P1 configuration and immutable ten-city publication; no implicit network IO."""
from dataclasses import dataclass
from datetime import datetime
import re
from urllib.parse import urlsplit

from web.fixtures import BERLIN
from web.forecasts import Cache, FEATURED, FORMAT, key, manifest_key, pack, unpack
from web.history import encode, digest
from web.live import location, Unavailable
from web.publication import Snapshot, document, sha, VERSION
from web.readonly import service


@dataclass(frozen=True)
class Config:
    project: str
    owner: str
    store: str
    db_host: str
    db_name: str
    group: str
    records_digest: str
    code: str
    epoch: int
    domain: str = 'production/featured-v1'

    @property
    def fingerprint(self):
        return digest(dict(project=self.project, owner=self.owner, store=self.store,
                           db_host=self.db_host, db_name=self.db_name, group=self.group,
                           records=self.records_digest, domain=self.domain))

    @classmethod
    def environment(cls, env, *, worker=False):
        # Validate ALL non-secret target data before opening DB/Blob sessions.
        names = ('PROJECT_ID', 'OWNER_ID', 'STORE_ID', 'DB_HOST', 'DB_NAME',
                 'PROVIDER_GROUP', 'RECORDS_SHA256', 'CODE_VERSION', 'EPOCH')
        values = [env.get('TRAVEL_P1_'+n, '') for n in names]
        if any(not isinstance(v, str) or not v or len(v)>200 for v in values):
            raise ValueError('P1 target configuration missing')
        p, o, s, h, db, g, r, code, epoch = values
        if (not re.fullmatch(r'prj_[A-Za-z0-9]+', p) or
                not re.fullmatch(r'team_[A-Za-z0-9]+', o) or
                not re.fullmatch(r'store_[A-Za-z0-9]+', s) or
                not re.fullmatch(r'[a-z0-9.-]+', h) or '..' in h or
                not re.fullmatch(r'[a-zA-Z0-9_-]+', db) or
                not re.fullmatch(r'[a-zA-Z0-9_-]+', g) or
                not VERSION.fullmatch(r) or not re.fullmatch(r'[a-f0-9]{40}', code) or
                not epoch.isdigit() or not 0<int(epoch)<2**63 or
                env.get('TRAVEL_P1_CONFIG_SHA256') != cls(p,o,s,h,db,g,r,code,int(epoch)).fingerprint):
            raise ValueError('P1 target configuration invalid')
        if env.get('TRAVEL_PREVIEW_NAMESPACE') is not None:
            raise ValueError('Conflicting Preview configuration')
        if worker:
            if (env.get('TRAVEL_P1_ENABLED') != 'true' or
                    env.get('GITHUB_REPOSITORY') != 'pengcc/travel-clothing-advisor' or
                    env.get('GITHUB_REF') != 'refs/heads/main' or
                    env.get('GITHUB_EVENT_NAME') not in ('schedule', 'workflow_dispatch') or
                    env.get('GITHUB_SHA') != code or env.get('VERCEL')):
                raise ValueError('Worker disabled or unapproved revision')
        else:
            if (env.get('VERCEL_ENV') != 'production' or env.get('VERCEL_PROJECT_ID') != p or
                    env.get('VERCEL_ORG_ID') != o or env.get('BLOB_STORE_ID') != s or
                    env.get('TRAVEL_P1_BLOB_WRITE_TOKEN') or env.get('TRAVEL_P1_WORKER_DSN')):
                raise ValueError('Production reader identity/configuration mismatch')
        return cls(p,o,s,h,db,g,r,code,int(epoch))

    def dsn(self, value):
        u = urlsplit(value or '')
        if (u.scheme not in ('postgresql','postgres') or u.hostname != self.db_host or
                u.path != '/'+self.db_name or u.port not in (None,5432) or
                not u.username or not u.password or u.query != 'sslmode=verify-full' or u.fragment):
            raise ValueError('Dedicated TLS database target required')
        return value


def records(raw, cfg):
    if sha(raw) != cfg.records_digest:
        raise ValueError('Unapproved city metadata')
    items = document(raw)
    cities = [location(r) for r in items]
    if len(cities)!=10 or {c['id'] for c in cities} != set(FEATURED):
        raise ValueError('Exactly ten verified featured records required')
    by_id = {c['id']: (r,c) for r,c in zip(items,cities)}
    return [by_id[i][0] for i in FEATURED], [by_id[i][1] for i in FEATURED]


def object_name(cfg, version):
    if not isinstance(version,str) or not VERSION.fullmatch(version):
        raise ValueError('Invalid object digest')
    return cfg.domain+'/objects/'+version


def put_object(remote, cfg, raw):
    name = object_name(cfg, sha(raw))
    prior = remote.get(name)
    if prior is None:
        remote.put(name, raw)
    elif prior != raw:
        raise ValueError('Immutable object conflict')
    if remote.get(name) != raw:
        raise OSError('Immutable read-back failed')
    return sha(raw)


def load_source(remote, cfg, city, day, version, clock):
    raw = remote.get(object_name(cfg,version))
    if raw is None or sha(raw)!=version:
        raise ValueError('Source digest mismatch')
    cache = Cache(Snapshot({key(city,day):raw},version), clock, read_only=True)
    if cache.read(city,day) is None:
        raise ValueError('Invalid source')
    return raw


def publication(remote, cfg, raw_records, versions, clock):
    recs, cities = records(raw_records,cfg)
    day = clock().astimezone(BERLIN).date()
    if set(versions)!=set(FEATURED):
        raise ValueError('Incomplete featured version set')
    objects = {'cities.json':raw_records}
    entries = []
    for city in cities:
        raw = load_source(remote,cfg,city,day,versions[city['id']],clock)
        objects[key(city,day)] = raw
        entries.append(dict(city=city,data_version=digest(unpack(raw))))
    objects[manifest_key(day)] = pack(dict(format=FORMAT,day=day.isoformat(),entries=entries))
    app = service(Snapshot(objects,''),recs,clock)
    app.featured()  # existing full-source + advice validator
    manifest = dict(schema=1,domain=cfg.domain,day=day.isoformat(),
                    records=cfg.records_digest,sources=versions,
                    data_versions={e['city']['id']:e['data_version'] for e in entries})
    return encode(manifest), app


class StageUnavailable(Unavailable):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def production_service(control, remote, cfg, raw_records, clock=lambda:datetime.now(BERLIN)):
    day, version, health = control.snapshot()
    if version is None:
        failure=StageUnavailable(health, {
            'forecast_preparing':'精选十城今日预报正在准备，请稍后重试。',
            'quota_limited':'今日天气下载额度已用完，请稍后重试。',
            'scheduler_unavailable':'自动更新暂不可用，请稍后重试。',
        }.get(health,'今日完整预报暂不可用，请稍后重试。'))
        recs,_=records(raw_records,cfg)
        class WaitingCache(Cache):
            def featured(self,*args,**kwargs):
                raise failure
            def obtain(self,*args,**kwargs):
                raise failure
        app=service(Snapshot({},''),recs,clock)
        app.forecasts=WaitingCache(app.forecasts.store,clock,read_only=True)
        return app
    raw = remote.get(object_name(cfg,version))
    manifest = document(raw)
    if sha(raw)!=version or manifest.get('day')!=day.isoformat():
        raise ValueError('Invalid committed manifest')
    recs,cities=records(raw_records,cfg)
    if (set(manifest)!={'schema','domain','day','records','sources','data_versions'} or
            manifest['schema']!=1 or manifest['domain']!=cfg.domain or
            manifest['records']!=cfg.records_digest or
            set(manifest['sources'])!=set(FEATURED) or set(manifest['data_versions'])!=set(FEATURED) or
            any(not isinstance(v,str) or not VERSION.fullmatch(v)
                for field in ('sources','data_versions') for v in manifest[field].values()) or
            raw!=encode(manifest) or day!=clock().astimezone(BERLIN).date()):
        raise ValueError('Publication configuration/date mismatch')
    by_key={key(city,day):city for city in cities}
    entries=[dict(city=c,data_version=manifest['data_versions'][c['id']]) for c in cities]

    class PinnedStore:
        version=sha(raw)
        def get(self,name):
            if name==manifest_key(day):
                return pack(dict(format=FORMAT,day=day.isoformat(),entries=entries))
            city=by_key.get(name)
            if city is None:
                return None
            try:
                source=load_source(remote,cfg,city,day,manifest['sources'][city['id']],clock)
                if digest(unpack(source))!=manifest['data_versions'][city['id']]:
                    raise ValueError('Source body version mismatch')
                return source
            except (ValueError,TypeError,LookupError):
                raise OSError('Committed source unavailable') from None

    class FeaturedCache(Cache):
        def featured(self,app,city_id=None):
            if city_id is None:
                return super().featured(app)
            city=next((c for c in cities if c['id']==city_id),None)
            if city is None:
                raise ValueError('该城市不在精选城市列表中。')
            now=self.current(day)
            result=self.render(app,city,now,self.read(city,day))
            self.current(day)
            return result

    app=service(PinnedStore(),recs,clock)
    app.forecasts=FeaturedCache(app.forecasts.store,clock,read_only=True)
    return app
