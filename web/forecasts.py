"""Local shared daily source snapshots; no user advice or trip inputs are stored.

Store adapters are the same atomic, nonblocking, single-host primitives used by
history. Hosted object storage and distributed admission remain Phase 2D.
"""
from contextlib import nullcontext
from datetime import date, datetime, time
import json
from time import monotonic

from web.fixtures import BERLIN, CITIES, window
from web.live import IDS, FORECAST, Unavailable, location, parse_hours, fetch_json
from web.history import Store, MemoryStore, DirectoryStore, encode, digest, transport

FORMAT = dict(schema=1, request_version='hourly-14d-v1', model='best_match',
              variable='temperature_2m', unit='celsius', timezone='Europe/Berlin',
              timeformat='unixtime', forecast_days=14)
LEDGER = 'forecast/control/admission-v1.json'
FEATURED = tuple(c['id'] for c in CITIES[:10])


def identity(city, day):
    # Reapply the provider metadata boundary; coordinates never come from a URL.
    ident = str(IDS.get(city['id'], city['id']))
    checked = location(dict(id=int(ident), name=city['name'], admin1=city['state'],
                            country_code='DE', feature_code='PPL',
                            latitude=city['latitude'], longitude=city['longitude']))
    return dict(FORMAT, city_id=ident,
                coordinates=[checked['latitude'], checked['longitude']], day=day.isoformat())


def key(city, day):
    ident = identity(city, day)
    return f"forecast/hourly-14d-v1/{ident['city_id']}/{digest(ident)}/{day.isoformat()}.json"


def manifest_key(day):
    return f'forecast/featured-v1/{day.isoformat()}.json'


def unpack(raw):
    if not isinstance(raw, bytes) or len(raw) > 200_000:
        raise ValueError('Invalid snapshot size')
    obj = json.loads(raw)
    if obj['sha256'] != digest(obj['body']):
        raise ValueError('Invalid checksum')
    return obj['body']


def pack(body):
    return encode(dict(body=body, sha256=digest(body)))


class Cache:
    def __init__(self, store, clock=lambda: datetime.now(BERLIN), *, daily_limit=42,
                 cooldown=300, timer=monotonic, read_only=False):
        if type(daily_limit) is not int or not 1 <= daily_limit <= 42 or cooldown <= 0:
            raise ValueError('Invalid forecast limits')
        self.store, self.clock = store, clock
        self.read_only = read_only
        self.daily_limit, self.cooldown, self.timer = daily_limit, cooldown, timer

    def current(self, day):
        now = self.clock().astimezone(BERLIN)
        if now.date() != day:
            raise Unavailable('德国日期已变化，请重新查询。')
        return now

    def read(self, city, day):
        """A corrupt entry is a repairable miss; IO outages must fail closed."""
        raw = self.store.get(key(city, day))
        if raw is None:
            return None
        try:
            body = unpack(raw)
            acquired = datetime.fromisoformat(body['weather_fetched_at'])
            now = self.current(day)
            if (body['identity'] != identity(city, day) or body['source'] != FORECAST or
                    acquired.tzinfo is None or acquired.astimezone(BERLIN).date() != day or acquired > now):
                raise ValueError()
            parse_hours(body['response'], datetime.combine(day, time(), BERLIN))
            return body['response'], acquired, digest(body)
        except (ValueError, KeyError, TypeError, OverflowError, Unavailable):
            return None

    def read_snapshot(self, city, day):
        """Read-only: validate the snapshot filed under `day` against that day, not today.

        Same checks as `read` (identity, source, checksum, acquired on that day, not
        in the future, hour coverage anchored at `day`), but without requiring
        `day` to be the current Berlin date. Never downloads or writes.
        """
        raw = self.store.get(key(city, day))
        if raw is None:
            return None
        try:
            body = unpack(raw)
            acquired = datetime.fromisoformat(body['weather_fetched_at'])
            now = self.clock().astimezone(BERLIN)
            if (body['identity'] != identity(city, day) or body['source'] != FORECAST or
                    acquired.tzinfo is None or acquired.astimezone(BERLIN).date() != day or acquired > now):
                raise ValueError()
            parse_hours(body['response'], datetime.combine(day, time(), BERLIN))
            return body['response'], acquired, digest(body)
        except (ValueError, KeyError, TypeError, OverflowError, Unavailable):
            return None

    def reserve(self, day):
        """Charge before IO, including failed attempts. Lock held by caller."""
        now = self.current(day)
        raw = self.store.get(LEDGER)
        try:
            ledger = unpack(raw) if raw is not None else dict(day=day.isoformat(), attempts=0, cooldown_until=0)
            if (set(ledger) != {'day', 'attempts', 'cooldown_until'} or
                    date.fromisoformat(ledger['day']).isoformat() != ledger['day'] or
                    ledger['day'] > day.isoformat() or type(ledger['attempts']) is not int or ledger['attempts'] < 0 or
                    type(ledger['cooldown_until']) not in (int, float) or
                    not 0 <= ledger['cooldown_until'] < 10**12):
                raise ValueError()
            if ledger['day'] != day.isoformat():
                ledger.update(day=day.isoformat(), attempts=0)
        except (ValueError, KeyError, TypeError) as exc:
            raise Unavailable('预报用量记录无效，需管理员检查。') from exc
        if ledger['attempts'] >= self.daily_limit or ledger['cooldown_until'] > now.timestamp():
            raise Unavailable('预报下载预算或冷却限制，请稍后重试。')
        ledger['attempts'] += 1
        self.store.put(LEDGER, pack(ledger))
        return ledger

    def load_locked(self, city, day, provider, deadline, stats):
        self.current(day)
        cached = self.read(city, day)
        if cached is not None:
            stats['hits'] += 1
            return cached
        remaining = deadline-self.timer()
        if remaining <= 0:
            raise Unavailable('预报准备已超时。')
        ledger = self.reserve(day)
        stats['forecast_attempts'] += 1
        try:
            data = provider(FORECAST, dict(latitude=city['latitude'], longitude=city['longitude'],
                            hourly='temperature_2m', forecast_days=14, timezone='Europe/Berlin',
                            timeformat='unixtime', temperature_unit='celsius', models='best_match'),
                            min(4, remaining))
            acquired = self.current(day)
            parse_hours(data, datetime.combine(day, time(), BERLIN))
            body = dict(identity=identity(city, day), source=FORECAST,
                        weather_fetched_at=acquired.isoformat(), response=data)
            if self.timer() >= deadline:
                raise Unavailable('预报准备已超时。')
            encoded = pack(body)
            if len(encoded) > 200_000:
                raise ValueError('Oversized snapshot')
            self.store.put(key(city, day), encoded)
            self.current(day)
            stats['published'] += 1
            return data, acquired, digest(body)
        except (LookupError, ValueError, TypeError, KeyError, OSError, TimeoutError) as exc:
            stats['failed'] += 1
            ledger['cooldown_until'] = self.clock().timestamp()+self.cooldown
            self.store.put(LEDGER, pack(ledger))
            raise Unavailable('预报获取、校验或存储失败，暂不提供穿衣建议。') from exc

    def obtain(self, city, now, fetch):
        """At most one missing city per personal request, no retries, 12s total.

        Injected two-argument providers must be bounded themselves. Real network
        uses the existing size/wall-time bounded transport with remaining time.
        """
        if self.read_only:
            try:
                cached = self.read(city, now.date())
                self.current(now.date())
                if cached is None:
                    raise Unavailable('这个城市今日预报尚未准备好，暂不提供穿衣建议。')
                return cached
            except OSError as exc:
                raise Unavailable('预报存储暂不可用。') from exc
        provider = transport if fetch is fetch_json else lambda u, p, t: fetch(u, p)
        try:
            with self.store.exclusive():
                return self.load_locked(city, now.date(), provider, self.timer()+12,
                                        dict(hits=0, forecast_attempts=0, published=0, failed=0))
        except OSError as exc:
            raise Unavailable('预报存储暂不可用。') from exc

    def prefetch(self, records, provider=transport, *, timeout=45):
        """Prepare 1–10 selected verified cities with the existing cache pipeline."""
        if not 0 < timeout <= 60:
            raise ValueError('Timeout must be in (0, 60]')
        cities = [location(raw) for raw in records]
        if not 1 <= len(cities) <= 10 or len({c['id'] for c in cities}) != len(cities):
            raise ValueError('Supply 1–10 distinct verified GeoNames records')
        cities.sort(key=lambda c: FEATURED.index(c['id']) if c['id'] in FEATURED else len(FEATURED))
        stats = dict(forecast_attempts=0, geocoding_attempts=0, hits=0, published=0, failed=0, complete=False)
        self.stats = stats
        day = self.clock().astimezone(BERLIN).date()
        deadline = self.timer()+timeout
        try:
            with self.store.exclusive():
                entries = []
                for city in cities:
                    data, acquired, version = self.load_locked(city, day, provider, deadline, stats)
                    entries.append(dict(city=city, data_version=version))
                # Derive all advice before publication, using one clock instant.
                now = self.current(day)
                from web.live import Service
                service = Service(clock=lambda: now, forecast_cache=self)
                for entry in entries:
                    self.render(service, entry['city'], now, self.read(entry['city'], day))
                if self.timer() >= deadline:
                    raise Unavailable('预报准备已超时。')
                self.current(day)
                # Selected runs prepare source objects, not partial replacements
                # for the legacy ten-city publication. Its reader revalidates
                # every source version, so a changed source fails closed until
                # a full canonical run republishes the manifest.
                if [entry['city']['id'] for entry in entries] == list(FEATURED):
                    body = dict(format=FORMAT, day=day.isoformat(), entries=entries)
                    self.store.put(manifest_key(day), pack(body))
                self.current(day)
                stats['complete'] = True
                return stats
        except OSError as exc:
            raise Unavailable('预报存储暂不可用。') from exc

    def render(self, service, city, now, cached):
        w = window(now)
        if cached is None:
            raise Unavailable('精选城市完整预报尚未准备好。')
        return service.forecast_advice(city, dict(view='city', start=w['today'],
                    end=w['forecast_end'], preference='normal'), now, cached, generated=now)

    def featured(self, service, city_id=None):
        if city_id is not None and city_id not in FEATURED:
            raise ValueError('该城市不在精选城市列表中。')
        now = self.clock().astimezone(BERLIN)
        day = now.date()
        try:
            with nullcontext() if self.read_only else self.store.exclusive():
                body = unpack(self.store.get(manifest_key(day)))
                if body['format'] != FORMAT or body['day'] != day.isoformat():
                    raise ValueError()
                entries = body['entries']
                if len(entries) != 10 or [e['city']['id'] for e in entries] != list(FEATURED):
                    raise ValueError()
                results = []
                # Revalidate the whole publication even for a single city detail.
                for entry in entries:
                    city = entry['city']
                    cached = self.read(city, day)
                    if cached is None or cached[2] != entry['data_version']:
                        raise ValueError()
                    results.append(self.render(service, city, now, cached))
                self.current(day)
                if city_id is not None:
                    return next(d for d in results if d['city']['id'] == city_id)
                return dict(**window(now), fixture=False, data_status='fresh',
                            data_version=digest(body), cities=results,
                            weather_fetched_at=min(d['weather_fetched_at'] for d in results))
        except (OSError, ValueError, KeyError, TypeError, StopIteration) as exc:
            raise Unavailable('精选城市今日完整预报暂不可用，请稍后重试。') from exc
