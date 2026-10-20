"""S2 bounded, single-publisher sample; no provider or user write endpoints.

A dataset contains one trusted city, one forecast and one archive month. Readers
pin and validate a complete immutable version per request. This is NOT a queue,
quota coordinator, transactional pointer update or a complete five-year dataset.
"""
from datetime import datetime
import hashlib
import json
import re

from web.fixtures import BERLIN
from web.forecasts import key as forecast_key
from web.history import encode, Library, key as history_key
from web.live import Unavailable
from web.readonly import service

LIMIT = 200_000
NAMESPACE = re.compile(r'preview/[a-z0-9][a-z0-9-]{0,47}')
VERSION = re.compile(r'[a-f0-9]{64}')
MESSAGE = '独立发布的数据集尚未准备好或校验失败，暂不可用。'


def namespace(value):
    if not isinstance(value, str) or not NAMESPACE.fullmatch(value):
        raise ValueError('Expected isolated preview/<trial-name> namespace')
    return value


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def document(raw):
    if not isinstance(raw, bytes) or not 0 < len(raw) <= LIMIT:
        raise ValueError('Invalid object size')
    def pairs(items):
        result = {}
        for k, v in items:
            if k in result:
                raise ValueError('Duplicate JSON field')
            result[k] = v
        return result
    return json.loads(raw, object_pairs_hook=pairs)


class Snapshot:
    """get-only in-memory view of exactly one checked publication version."""
    def __init__(self, objects, version):
        self._objects = dict(objects)
        self.version = version

    def get(self, name):
        return self._objects.get(name)


def validate(manifest, objects, scope, clock):
    """Reuse source validators, including identity, date, hours and inner hash."""
    if (not isinstance(manifest, dict) or set(manifest) !=
            {'schema', 'namespace', 'day', 'city_id', 'month', 'objects'} or
            type(manifest['schema']) is not int or manifest['schema'] != 1 or
            manifest['namespace'] != namespace(scope) or
            manifest['day'] != clock().astimezone(BERLIN).date().isoformat()):
        raise ValueError('Invalid manifest or expired Germany day')
    entries = manifest['objects']
    if not isinstance(entries, dict) or len(entries) != 3 or set(entries) != set(objects):
        raise ValueError('Expected exactly three sample objects')
    for name, entry in entries.items():
        raw = objects[name]
        if (not isinstance(raw, bytes) or not isinstance(entry, dict) or
                set(entry) != {'sha256', 'bytes'} or type(entry['bytes']) is not int or
                not 0 < entry['bytes'] <= LIMIT or len(raw) != entry['bytes'] or
                sha(raw) != entry['sha256']):
            raise ValueError('Object checksum/size mismatch')
    records = document(objects['cities.json'])
    if not isinstance(records, list) or len(records) != 1:
        raise ValueError('Expected one trusted sample city')
    snapshot = Snapshot(objects, sha(encode(manifest)))
    app = service(snapshot, records, clock)
    city = app.resolve(manifest['city_id'])
    # No arbitrary paths or control/ledger objects can be fetched or published.
    expected = {'cities.json', forecast_key(city, clock().astimezone(BERLIN).date()),
                history_key(city, manifest['month'])}
    if set(entries) != expected:
        raise ValueError('Unexpected sample objects')
    if app.forecasts.read(city, clock().astimezone(BERLIN).date()) is None:
        raise ValueError('Invalid forecast')
    if Library(snapshot, clock, read_only=True).read(city, manifest['month']) is None:
        raise ValueError('Invalid archive month')
    if manifest['day'] != clock().astimezone(BERLIN).date().isoformat():
        raise ValueError('Germany date changed during validation')
    return app


def prepare(source, records, city_id, month, scope, clock=lambda: datetime.now(BERLIN)):
    """Select only the sample objects; never copy ledgers or an entire cache."""
    namespace(scope)
    selected = service(Snapshot({}, ''), records, clock).resolve(city_id)
    # Resolve trusted metadata through the existing normalization boundary.
    from web.live import location
    chosen = [r for r in records if location(r)['id'] == selected['id']]
    if len(chosen) != 1:
        raise ValueError('Expected one matching trusted record')
    day = clock().astimezone(BERLIN).date()
    names = (forecast_key(selected, day), history_key(selected, month))
    objects = {'cities.json': encode(chosen)}
    for name in names:
        objects[name] = source.get(name)
    if any(not isinstance(raw, bytes) or not 0 < len(raw) <= LIMIT for raw in objects.values()):
        raise ValueError('Missing or oversized sample source')
    manifest = dict(schema=1, namespace=scope, day=day.isoformat(), city_id=selected['id'],
                    month=month, objects={n:dict(sha256=sha(b), bytes=len(b)) for n,b in objects.items()})
    validate(manifest, objects, scope, clock)
    return manifest, objects


def load_version(remote, scope, version, clock=lambda: datetime.now(BERLIN)):
    namespace(scope)
    if not isinstance(version, str) or not VERSION.fullmatch(version):
        raise ValueError('Invalid publication version')
    prefix = f'{scope}/versions/{version}/'
    raw = remote.get(prefix+'manifest.json')
    manifest = document(raw)
    if sha(raw) != version or raw != encode(manifest):
        raise ValueError('Manifest checksum mismatch')
    # Validate paths before IO; only the three names derived from trusted city
    # metadata can be accessed. Fetch cities first, then source validators run.
    entries = manifest.get('objects') if isinstance(manifest, dict) else None
    if not isinstance(entries, dict) or len(entries) != 3 or 'cities.json' not in entries:
        raise ValueError('Invalid manifest entries')
    if any(not isinstance(n, str) or not re.fullmatch(r'[a-zA-Z0-9_./-]{1,240}', n)
           or any(p in ('', '.', '..') for p in n.split('/')) for n in entries):
        raise ValueError('Unsafe object name')
    objects = {n: remote.get(prefix+n) for n in entries}
    app = validate(manifest, objects, scope, clock)
    return app, manifest, objects


def published_service(remote, scope, clock=lambda: datetime.now(BERLIN)):
    try:
        pointer = document(remote.get(namespace(scope)+'/current.json'))
        if (not isinstance(pointer, dict) or set(pointer) != {'schema', 'namespace', 'version'} or
                type(pointer['schema']) is not int or pointer['schema'] != 1 or pointer['namespace'] != scope):
            raise ValueError('Invalid pointer')
        app, _, _ = load_version(remote, scope, pointer['version'], clock)
        return app
    except (OSError, ValueError, TypeError, KeyError, LookupError, OverflowError) as exc:
        raise Unavailable(MESSAGE) from exc


def announce(remote, scope, version, clock=lambda: datetime.now(BERLIN)):
    """Read-back before switching, also used for same-day rollback.

    Only ONE trusted publisher may call this for the namespace. The pointer PUT
    is not compare-and-set. An ambiguous write error requires operator read-back,
    never a blind retry. CDN stale reads may still return an older valid version.
    """
    load_version(remote, scope, version, clock)
    remote.put(scope+'/current.json', encode(dict(schema=1, namespace=scope, version=version)),
               overwrite=True)


def publish(remote, manifest, objects, clock=lambda: datetime.now(BERLIN)):
    scope = manifest['namespace']
    validate(manifest, objects, scope, clock)
    raw = encode(manifest)
    version = sha(raw)
    prefix = f'{scope}/versions/{version}/'
    # Resume is safe only when existing immutable bytes match exactly. Neither
    # an incomplete upload nor a failed read-back can announce a version.
    for name, body in list(objects.items()) + [('manifest.json', raw)]:
        existing = remote.get(prefix+name)
        if existing is None:
            remote.put(prefix+name, body, overwrite=False)
        elif existing != body:
            raise ValueError('Immutable version conflict')
    announce(remote, scope, version, clock)
    return version
