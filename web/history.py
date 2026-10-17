"""Versioned ERA5 month library. No network IO occurs unless Downloader is invoked.

Stores implement get/put/exclusive; put must atomically replace a whole object.
The exclusive admission lock and quota ledger cover ONE store, not an account
or independent machines. A hosted adapter needs a real shared coordinator.
"""
from calendar import monthrange
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta
import gzip
import hashlib
import io
import json
import math
import os
import zlib
from pathlib import Path
from threading import Lock
from time import monotonic
from typing import Protocol
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import urlopen

from web.fixtures import BERLIN
from web.live import IDS, Unavailable, number

ARCHIVE = 'https://archive-api.open-meteo.com/v1/archive'
FORMAT = dict(schema=1, model='era5', variable='temperature_2m', unit='°C',
              timezone='Europe/Berlin', timeformat='unixtime')
LEDGER = 'control/usage-v1.json'


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(encode(value)).hexdigest()


def windows(start, end):
    """Anchor the start; preserve N local calendar days, including leap approximations."""
    length = (end-start).days
    if length < 0 or length > 29:
        raise ValueError('Historical trips must contain 1–30 calendar days')
    result = []
    for year in range(start.year-1, start.year-6, -1):
        day = min(start.day, monthrange(year, start.month)[1])
        first = date(year, start.month, day)
        result.append((first, first+timedelta(days=length)))
    return result


def months(ranges):
    result = set()
    for start, end in ranges:
        cursor = start.replace(day=1)
        while cursor <= end:
            result.add(cursor.strftime('%Y-%m'))
            cursor = (cursor+timedelta(days=32)).replace(day=1)
    return sorted(result)


def bounds(month):
    first = date.fromisoformat(month+'-01')
    last = first.replace(day=monthrange(first.year, first.month)[1])
    return first, last


def identity(city, month):
    provider_id = IDS.get(city['id'], city['id'])
    if not str(provider_id).isascii() or not str(provider_id).isdigit():
        raise ValueError('Expected resolved GeoNames ID')
    coordinates = [city['latitude'], city['longitude']]
    if not all(number(v) for v in coordinates):
        raise ValueError('Expected resolved coordinates')
    bounds(month)
    return dict(FORMAT, city_id=str(provider_id), coordinates=coordinates, month=month)


def key(city, month):
    ident = identity(city, month)
    return f"history/era5/temp-v1/{ident['city_id']}/{digest(ident['coordinates'])[:24]}/{month}.json.gz"


def expected_times(month):
    first, last = bounds(month)
    start = datetime.combine(first, time(), BERLIN)
    stop = datetime.combine(last+timedelta(days=1), time(), BERLIN)
    return list(range(int(start.timestamp()), int(stop.timestamp()), 3600))


def provider_hours(data, month):
    """Validate the provider's continuous UTC sequence, then trim boundary padding.

    The API uses a single offset for range boundaries. Request padded dates and
    convert every epoch via ZoneInfo to retain both DST folds and full months.
    """
    try:
        if data.get('error') or data['timezone'] != 'Europe/Berlin' or data['hourly_units']['temperature_2m'] != '°C':
            raise ValueError()
        times, temps = data['hourly']['time'], data['hourly']['temperature_2m']
        if not isinstance(times, list) or not isinstance(temps, list) or not times or len(times) != len(temps):
            raise ValueError()
        if any(type(t) is not int or t % 3600 for t in times) or any(b-a != 3600 for a,b in zip(times,times[1:])):
            raise ValueError()
        if any(not number(v) or not -90 <= v <= 65 for v in temps):
            raise ValueError()
        expected = expected_times(month)
        indexed = dict(zip(times, temps))
        return dict(time=expected, temperature_2m=[indexed[t] for t in expected])
    except (KeyError, TypeError, ValueError, AttributeError, OverflowError) as exc:
        raise Unavailable('历史月份小时资料不完整或格式无效。') from exc


class Store(Protocol):
    def get(self, name: str): ...  # bytes or None, OSError on outage
    def put(self, name: str, data: bytes): ...  # atomic complete-object publication
    def exclusive(self): ...  # nonblocking context manager, shared with readers


class MemoryStore:
    def __init__(self):
        self.objects = {}
        self.lock = Lock()

    def get(self, name):
        return self.objects.get(name)

    def put(self, name, data):
        self.objects[name] = data

    @contextmanager
    def exclusive(self):
        if not self.lock.acquire(blocking=False):
            raise Unavailable('历史资料正在维护，请稍后重试。')
        try:
            yield
        finally:
            self.lock.release()


class DirectoryStore:
    """Explicit local development adapter; never a production container cache."""
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, name):
        path = (self.root/name).resolve()
        if self.root not in path.parents:
            raise ValueError('Object outside store')
        return path

    def get(self, name):
        try:
            return self.path(name).read_bytes()
        except FileNotFoundError:
            return None

    def put(self, name, data):
        import tempfile
        path = self.path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = None
        try:
            with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as out:
                temp = out.name
                out.write(data)
                out.flush()
                os.fsync(out.fileno())
            os.replace(temp, path)
            temp = None
        finally:
            if temp is not None:
                os.unlink(temp)

    @contextmanager
    def exclusive(self):
        import fcntl
        with (self.root/'.worker.lock').open('a') as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise Unavailable('历史资料正在维护，请稍后重试。') from exc
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)


class Library:
    def __init__(self, store, clock=lambda: datetime.now(BERLIN)):
        self.store, self.clock = store, clock

    def read(self, city, month):
        """Missing/corrupt entries are misses; storage outages fail closed."""
        raw = self.store.get(key(city, month))
        if raw is None:
            return None
        try:
            if len(raw) > 200_000:
                raise ValueError()
            with gzip.GzipFile(fileobj=io.BytesIO(raw)) as stream:
                decoded = stream.read(200_001)
            if len(decoded) > 200_000:
                raise ValueError()
            block = json.loads(decoded)
            body = block['body']
            acquired = datetime.fromisoformat(body['fetched_at'])
            if acquired.tzinfo is None or acquired > self.clock():
                raise ValueError()
            if body['identity'] != identity(city, month) or body['source'] != ARCHIVE or block['sha256'] != digest(body):
                raise ValueError()
            h = body['hourly']
            if h['time'] != expected_times(month):
                raise ValueError()
            provider_hours(dict(timezone=FORMAT['timezone'], hourly_units=dict(temperature_2m='°C'), hourly=h), month)
            if bounds(month)[1] > acquired.astimezone(BERLIN).date()-timedelta(days=6):
                raise ValueError()
            return block
        except (ValueError, KeyError, TypeError, OSError, EOFError, OverflowError, zlib.error, Unavailable):
            return None

    def publish(self, city, month, data):
        hourly = provider_hours(data, month)
        acquired = self.clock().astimezone(BERLIN)
        if bounds(month)[1] > acquired.date()-timedelta(days=6):
            raise Unavailable('必要历史月份尚未完整发布，请稍后重试。')
        body = dict(identity=identity(city, month), source=ARCHIVE,
                    fetched_at=acquired.isoformat(timespec='seconds'), hourly=hourly)
        block = dict(body=body, sha256=digest(body))
        self.store.put(key(city, month), gzip.compress(encode(block), mtime=0))
        return block

    def sample(self, city, start, end, downloader=None, max_missing=0):
        ranges = windows(start, end)
        needed = months(ranges)
        try:
            with self.store.exclusive():
                blocks = {m:self.read(city,m) for m in needed}
                missing = [m for m,b in blocks.items() if b is None]
                if missing:
                    if downloader is None or len(missing) > max_missing:
                        raise Unavailable('过去五年同期历史资料尚未齐备，请稍后重试；暂不提供穿衣建议。')
                    downloader.fill_locked([(city,m) for m in missing])
                    blocks = {m:self.read(city,m) for m in needed}
                if not all(blocks.values()):
                    raise Unavailable('过去五年同期历史资料不完整，请稍后重试。')
                indexed = {}
                for block in blocks.values():
                    h = block['body']['hourly']
                    indexed.update(zip(h['time'], h['temperature_2m']))
                days, edges = [], []
                for first, last in ranges:
                    for n in range((last-first).days+1):
                        day = first+timedelta(days=n)
                        vals = {h:indexed[int(datetime.combine(day,time(h),BERLIN).timestamp())] for h in range(6,23)}
                        from statistics import median
                        days.append((day.isoformat(), median(vals[h] for h in range(9,19))))
                        edges.extend((day.isoformat(),v) for h,v in vals.items() if h<9 or h>18)
                return days, edges, blocks
        except OSError as exc:
            raise Unavailable('历史资料存储暂不可用。') from exc


def transport(url, params, timeout):
    # Read time and connect time share a wall-clock deadline; response size is bounded.
    deadline = monotonic()+timeout
    with urlopen(url+'?'+urlencode(params), timeout=timeout) as response:
        chunks, size = [], 0
        while True:
            if monotonic() >= deadline:
                raise TimeoutError()
            # read1 performs at most one underlying read, unlike read(size).
            if response.isclosed():
                break
            response.fp.raw._sock.settimeout(max(0.001, deadline-monotonic()))
            chunk = response.read1(65536)
            if not chunk:
                break
            size += len(chunk)
            if size > 1_000_000:
                raise ValueError('Oversized response')
            chunks.append(chunk)
        return json.loads(b''.join(chunks))


class Downloader:
    """Serial, single-store admission; failed attempts stay charged. No auto retries."""
    def __init__(self, library, provider=transport, *, batch=6, daily=60, monthly=600,
                 max_blocks=5, timeout=12, request_timeout=4, cooldown=300,
                 timer=monotonic):
        if any(v <= 0 for v in (batch,daily,monthly,max_blocks,timeout,request_timeout,cooldown)):
            raise ValueError('Limits must be positive')
        self.library, self.provider = library, provider
        self.batch, self.daily, self.monthly = batch,daily,monthly
        self.max_blocks, self.timeout, self.request_timeout = max_blocks,timeout,request_timeout
        self.cooldown, self.timer = cooldown,timer
        self.stats = {}

    @staticmethod
    def cost(month):
        first,last = bounds(month)
        # 2 padded days, one variable/model/location; rounded up with 2x safety margin.
        return 2*math.ceil(((last-first).days+3)/14)

    def fill(self, jobs):
        try:
            with self.library.store.exclusive():
                return self.fill_locked(jobs)
        except OSError as exc:
            raise Unavailable('历史资料存储暂不可用。') from exc

    def fill_locked(self, jobs):
        self.stats = dict(http_requests=0, equivalent_calls=0, hits=0, published=0, failed=0)
        started = self.timer()
        store = self.library.store
        raw = store.get(LEDGER)
        try:
            ledger = json.loads(raw) if raw is not None else dict(days={}, months={}, cooldown_until=0)
            if set(ledger) != {'days','months','cooldown_until'} or not number(ledger['cooldown_until']):
                raise ValueError()
            for k in ('days','months'):
                if not isinstance(ledger[k],dict) or any(type(v) is not int or v<0 for v in ledger[k].values()):
                    raise ValueError()
        except (ValueError, TypeError) as exc:
            raise Unavailable('历史用量记录无效，需管理员检查；不继续下载。') from exc
        for city,month in jobs:
            if self.library.read(city,month) is not None:
                self.stats['hits'] += 1
                continue
            now = self.library.clock().astimezone(BERLIN)
            if self.timer()-started >= self.timeout:
                raise Unavailable('历史资料补取达到总时限，请稍后重试。')
            if bounds(month)[1] > now.date()-timedelta(days=6):
                raise Unavailable('必要历史月份尚未完整发布，请稍后重试。')
            day, mon = now.date().isoformat(), now.strftime('%Y-%m')
            cost = self.cost(month)
            if now.timestamp() < ledger['cooldown_until']:
                raise Unavailable('历史资料服务冷却中，请稍后重试。')
            if (self.stats['published'] >= self.max_blocks or self.stats['equivalent_calls']+cost > self.batch or
                ledger['days'].get(day,0)+cost > self.daily or ledger['months'].get(mon,0)+cost > self.monthly):
                raise Unavailable('历史资料补取预算已用完，请稍后重试。')
            ledger['days'][day] = ledger['days'].get(day,0)+cost
            ledger['months'][mon] = ledger['months'].get(mon,0)+cost
            store.put(LEDGER, encode(ledger))  # reserve durably BEFORE network IO
            self.stats['http_requests'] += 1
            self.stats['equivalent_calls'] += cost
            first,last = bounds(month)
            params = dict(latitude=city['latitude'], longitude=city['longitude'], models='era5',
                          hourly='temperature_2m', temperature_unit='celsius', timezone='Europe/Berlin',
                          timeformat='unixtime', start_date=(first-timedelta(days=1)).isoformat(),
                          end_date=(last+timedelta(days=1)).isoformat())
            try:
                remaining = self.timeout-(self.timer()-started)
                if remaining <= 0:
                    raise TimeoutError()
                data = self.provider(ARCHIVE, params, min(self.request_timeout,remaining))
                if self.timer()-started >= self.timeout:
                    raise TimeoutError()
                self.library.publish(city,month,data)
                self.stats['published'] += 1
            except (OSError, ValueError, Unavailable, TimeoutError) as exc:
                self.stats['failed'] += 1
                # HTTPError is an OSError. Honor a longer numeric Retry-After.
                retry = self.cooldown
                if isinstance(exc, HTTPError) and exc.headers:
                    try:
                        retry = max(retry, float(exc.headers.get('Retry-After',retry)))
                    except ValueError:
                        pass
                ledger['cooldown_until'] = self.library.clock().timestamp()+retry
                store.put(LEDGER, encode(ledger))
                raise Unavailable('历史月份下载或验证失败，已暂停补取，请稍后重试。') from exc
        return self.stats.copy()


def plan(cities, today, full_years=False):
    """Relevant actual mapped months first, across ALL cities; then annual backfill."""
    relevant = set()
    for n in range(30):
        relevant.update(months(windows(today+timedelta(days=n),today+timedelta(days=29))))
    priority = [(c,m) for c in cities for m in sorted(relevant, reverse=True)]
    if full_years:
        other = [f'{y}-{m:02d}' for y in range(today.year-1,today.year-6,-1) for m in range(1,13)]
        priority.extend((c,m) for c in cities for m in other if m not in relevant)
    return priority
