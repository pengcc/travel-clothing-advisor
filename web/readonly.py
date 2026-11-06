"""Prepared immutable dataset adapter. No provider calls or writable store API."""
from datetime import datetime
import hashlib
from pathlib import Path
import json

from web.fixtures import BERLIN, CITIES
from web.forecasts import Cache
from web.history import Library
from web.live import Service, Unavailable, location

HISTORY_CITIES = 'history-cities.json'
# Reviewed bytes of weather-data/history-cities.json: history-only cities, never featured and never
# forecast-prepared. Like the cities.json anchor in data_commands, changing the manifest needs this
# constant changed in the same reviewed code PR; data PRs only touch weather-data/history/.
TRUSTED_HISTORY_CITIES_SHA256 = '7f5067ccf6f59729646702226def076fb7fa481d7b7d1e7cff42dfcf68a221e4'


def history_city_records(raw):
    """Additional history-only city records; an absent manifest means none."""
    if raw is None:
        return []
    if len(raw) > 200_000 or hashlib.sha256(raw).hexdigest() != TRUSTED_HISTORY_CITIES_SHA256:
        raise ValueError('History city trust anchor changed; separate review required')
    records = json.loads(raw)
    if not isinstance(records, list):
        raise ValueError('Invalid history city manifest')
    ids = [location(record)['id'] for record in records]
    if len(set(ids)) != len(ids) or set(ids) & {c['id'] for c in CITIES[:10]}:
        raise ValueError('Invalid history city manifest')
    return records


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
        # Featured ten stay exact above; history-only cities only add selectable cities.
        return service(store, records + history_city_records(store.get(HISTORY_CITIES)), clock,
                       independent_cities=True)
    except (OSError, ValueError, TypeError, KeyError, LookupError) as exc:
        raise Unavailable('只读数据集或可信城市资料尚未准备好。') from exc
