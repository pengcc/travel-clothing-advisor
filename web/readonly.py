"""Prepared immutable dataset adapter. No provider calls or writable store API."""
from datetime import datetime
from pathlib import Path
import json

from web.fixtures import BERLIN, CITIES
from web.forecasts import Cache
from web.history import Library
from web.live import Service, Unavailable, location


class ReadOnlyDirectoryStore:
    """Read a prepared tree; never create directories, locks or control files.

    Operators must keep the tree immutable for the lifetime of a service.
    Dynamic object publication is a separate S2 concern.
    """
    def __init__(self, root):
        self.root = Path(root).resolve()

    def get(self, name):
        path = (self.root / name).resolve()
        if self.root not in path.parents:
            raise ValueError('Object outside dataset')
        try:
            return path.read_bytes()
        except FileNotFoundError:
            return None


def no_provider(*args, **kwargs):
    raise Unavailable('只读服务不提供在线天气下载或城市解析。')


def service(store, records, clock=lambda: datetime.now(BERLIN), *, independent_cities=False):
    """Validated operator records. Legacy remote publications opt into their
    all-city publication contract by default; bundles select independent cities.
    """
    return Service(no_provider, clock, trusted_records=records, independent_cities=independent_cities,
                   forecast_cache=Cache(store, clock, read_only=True),
                   history=Library(store, clock, read_only=True))


def prepared_service(root, clock=lambda: datetime.now(BERLIN)):
    store = ReadOnlyDirectoryStore(root)
    try:
        raw = store.get('cities.json')
        if raw is None or len(raw) > 200_000:
            raise ValueError()
        records = json.loads(raw)
        if not isinstance(records, list) or len(records) != 10:
            raise ValueError()
        if {location(record)['id'] for record in records} != {c['id'] for c in CITIES[:10]}:
            raise ValueError()
        return service(store, records, clock, independent_cities=True)
    except (OSError, ValueError, TypeError, KeyError, LookupError) as exc:
        raise Unavailable('只读数据集或可信城市资料尚未准备好。') from exc
