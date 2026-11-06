"""Manual local data maintenance; status/export never contact providers."""
import argparse
from datetime import datetime
import json
import os
import fcntl
from pathlib import Path
import shutil
import tempfile

from web.fixtures import BERLIN, CITIES
from web.forecasts import Cache, key as forecast_key
from web.history import (bounds, Library, DirectoryStore, Downloader, BackfillPaused,
                         key as history_key, plan, encode)
from web.live import location, Unavailable
from web.readonly import ReadOnlyDirectoryStore, HISTORY_CITIES, history_city_records


def history_records_at(root):
    """History-only cities beside the featured ten; trust-anchored, empty when the manifest is absent."""
    path = Path(root) / HISTORY_CITIES
    records = history_city_records(path.read_bytes() if path.exists() else None)
    return records, [location(r) for r in records]


def history_cities_at(root):
    """Featured ten plus history-only cities, for history inventory, backfill and export."""
    return records_at(root)[1] + history_records_at(root)[1]


def records_at(root):
    raw = (Path(root) / 'cities.json').read_bytes()
    if len(raw) > 200_000:
        raise ValueError('Oversized city manifest')
    records = json.loads(raw)
    cities = [location(r) for r in records]
    if len(cities) != 10 or {c['id'] for c in cities} != {c['id'] for c in CITIES[:10]}:
        raise ValueError('Expected the ten trusted cities')
    return records, cities


def valid_objects(roots, cities, clock, *, history=False):
    """Validate each source independently; the first root has precedence."""
    result = {}
    day = clock().astimezone(BERLIN).date()
    for root in reversed(roots):
        store = ReadOnlyDirectoryStore(root)
        for city in cities:
            names = (Path(root).glob(history_key(city, '2000-01').rsplit('/', 1)[0] + '/*.json.gz')
                     if history else [Path(root) / forecast_key(city, day)])
            for path in names:
                month = path.name.removesuffix('.json.gz')
                try:
                    if history:
                        bounds(month)
                    name = history_key(city, month) if history else forecast_key(city, day)
                except ValueError:
                    continue
                raw = store.get(name)
                # Validate the very bytes retained, avoiding a second-source read race.
                class Snapshot:
                    def get(self, _):
                        return raw
                snapshot = Library(Snapshot(), clock, read_only=True) if history else Cache(Snapshot(), clock, read_only=True)
                if snapshot.read(city, month if history else day) is not None:
                    result[name] = raw
    return result


def status(cities, forecasts, history, bundle, clock):
    day = clock().astimezone(BERLIN).date()
    f = valid_objects([forecasts, bundle], cities, clock)
    h = valid_objects([history, bundle], cities, clock, history=True)
    jobs = plan(cities, day)
    rows = []
    for city in cities:
        prefix = history_key(city, '2000-01').rsplit('/', 1)[0] + '/'
        missing = [m for c, m in jobs if c == city and history_key(c, m) not in h]
        rows.append(dict(city_id=city['id'], valid_months=sorted(
            n.rsplit('/', 1)[1].removesuffix('.json.gz') for n in h if n.startswith(prefix)),
            recent_missing=missing, pending_blocks=len(missing)))
    if clock().astimezone(BERLIN).date() != day:
        raise ValueError('Germany date changed; retry')
    return dict(day=day.isoformat(), valid_forecasts=len(f), total_cities=10,
                pending_blocks=sum(r['pending_blocks'] for r in rows), cities=rows)


def update(records, cities, forecasts, history, bundle, clock):
    roots = [Path(p).resolve() for p in (forecasts, history, bundle)]
    if any(a == b or a in b.parents or b in a.parents
           for i, a in enumerate(roots) for b in roots[i+1:]):
        raise ValueError('Use distinct, non-nested cache and bundle directories')
    # Seed only validated source objects. Keep all admission state in local stores.
    for root, historical in ((forecasts, False), (history, True)):
        store = DirectoryStore(root)
        with store.exclusive():
            for name, raw in valid_objects([root, bundle], cities, clock, history=historical).items():
                if store.get(name) != raw:
                    store.put(name, raw)
    cache = Cache(DirectoryStore(forecasts), clock)
    forecast_ok = False
    try:
        cache.prefetch(records)
        forecast_ok = True
    except (Unavailable, OSError, ValueError):
        pass
    worker = Downloader(Library(DirectoryStore(history), clock), batch=30, timeout=30)
    state = 'complete'
    try:
        worker.fill(plan(cities, clock().astimezone(BERLIN).date()))
    except BackfillPaused:
        state = 'paused_limit'
    except (Unavailable, OSError):
        state = 'paused_unavailable'
    forecast_ok = forecast_ok and len(valid_objects([forecasts, bundle], cities, clock)) == 10
    return dict(forecast_complete=forecast_ok, history_status=state,
                history=worker.stats), forecast_ok and state != 'paused_unavailable'


def tree(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in Path(root).rglob('*') if p.is_file()}


def export(records, cities, forecasts, history, bundle, clock):
    # Serialize cooperating exporters without creating any lock/cache metadata.
    fd = os.open(Path(bundle).parent, os.O_RDONLY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return _export(records, cities, forecasts, history, bundle, clock)
    finally:
        os.close(fd)


def _export(records, cities, forecasts, history, bundle, clock):
    """Stage, revalidate and swap a complete bundle, restoring on any failed swap."""
    bundle = Path(bundle)
    day = clock().astimezone(BERLIN).date()
    roots = [Path(p).resolve() for p in (forecasts, history, bundle)]
    if bundle.is_symlink() or any(a == b or a in b.parents or b in a.parents
                                  for i, a in enumerate(roots) for b in roots[i+1:]):
        raise ValueError('Use distinct, non-nested cache and bundle directories')
    before = tree(bundle)
    if json.loads(before.get('cities.json', b'null')) != records:
        raise ValueError('City manifest changed; retry export')
    objects = {'cities.json': encode(records)}
    if 'README.md' in before:
        objects['README.md'] = before['README.md']
    # The history-only manifest is owned by reviewed code; keep it and its cities' valid history.
    extra_records, extra = history_records_at(bundle)
    if extra_records:
        objects[HISTORY_CITIES] = before[HISTORY_CITIES]
    f = valid_objects([forecasts, bundle], cities, clock)
    if len(f) != 10:
        raise ValueError('Export requires ten valid same-day forecasts')
    objects.update(f)
    # Routine exports retain accepted Git history bytes; local data only adds
    # missing months or repairs invalid Git objects. Forecast priority is unchanged.
    objects.update(valid_objects([bundle, history], cities + extra, clock, history=True))
    with tempfile.TemporaryDirectory(prefix='.data-export-', dir=bundle.parent) as temporary:
        stage = Path(temporary) / 'next'
        stage.mkdir()
        for name, raw in objects.items():
            path = stage / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        if (len(valid_objects([stage], cities, clock)) != 10 or
                valid_objects([stage], cities + extra, clock, history=True) != {
                    n: b for n, b in objects.items() if n.startswith('history/')}):
            raise ValueError('Staged validation failed')
        if clock().astimezone(BERLIN).date() != day or tree(bundle) != before:
            raise ValueError('Date or destination changed; retry export')
        backup = Path(temporary) / 'previous'
        bundle.rename(backup)
        try:
            stage.rename(bundle)
            if clock().astimezone(BERLIN).date() != day:
                raise ValueError('Germany date changed; retry export')
        except BaseException:
            if bundle.exists():
                shutil.rmtree(bundle)
            backup.rename(bundle)
            raise
    return dict(added=len(objects.keys() - before.keys()),
                changed=sum(before[n] != objects[n] for n in objects.keys() & before.keys()),
                removed=len(before.keys() - objects.keys()), validated_objects=len(objects))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['update', 'status', 'export', 'forecast-update', 'forecast-export'])
    parser.add_argument('--output', help='New independent destination for forecast-only commands')
    parser.add_argument('--forecast-dir', default='.forecast-local')
    parser.add_argument('--history-dir', default='.history-local')
    parser.add_argument('--bundle-dir', default='weather-data')
    args = parser.parse_args(argv)
    clock = lambda: datetime.now(BERLIN)
    try:
        if args.command in ('forecast-update', 'forecast-export'):
            if not args.output:
                raise ValueError('New output directory required')
            if args.command == 'forecast-update':
                result = forecast_update(args.bundle_dir, args.output, clock)
            else:
                result = forecast_export(args.forecast_dir, args.bundle_dir, args.output, clock,
                                         clock().astimezone(BERLIN).date())
            print(json.dumps(result, sort_keys=True))
            return 0
        records, cities = records_at(args.bundle_dir)
        params = (cities, args.forecast_dir, args.history_dir, args.bundle_dir, clock)
        if args.command == 'status':
            result, ok = status(*params), True
        elif args.command == 'update':
            result, ok = update(records, *params)
        else:
            result, ok = export(records, *params), True
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0 if ok else 1
    except (OSError, ValueError, TypeError, KeyError, Unavailable):
        print('Data command failed: metadata, storage or validation unavailable; retry after checking inputs.')
        return 1


# Reviewed city-manifest bytes at main d4d91261ab11007cc7114e227880c6ab4dceec77.
# Deliberately not derived from the manifest being checked.
TRUSTED_CITIES_SHA256 = 'a83aff9040b65aea52e319f465c35e65b170a100fcfeef6f8e59a7965e0775ac'


def trusted_records(root):
    import hashlib
    if hashlib.sha256((Path(root) / 'cities.json').read_bytes()).hexdigest() != TRUSTED_CITIES_SHA256:
        raise ValueError('City trust anchor changed; separate review required')
    return records_at(root)


class Superseded(ValueError):
    """An entire candidate batch is older than an existing valid source."""


def forecast_batch(root, clock, day, *, required=True):
    """Strict automation boundary: corrupt/ambiguous sources are not cache misses."""
    from datetime import timezone
    _, cities = trusted_records(root)
    store = ReadOnlyDirectoryStore(root)
    cache = Cache(store, clock, read_only=True)
    expected = {forecast_key(c, day): c for c in cities}
    # Reject unrecognised same-day source paths rather than misreading identity drift as absence.
    for path in (Path(root) / 'forecast').rglob(day.isoformat() + '.json'):
        name = str(path.relative_to(root))
        if name not in expected:
            raise ValueError('Unexpected same-day forecast identity')
    result = {}
    for name, city in expected.items():
        raw = store.get(name)
        if raw is None and not required:
            continue
        cached = cache.read(city, day)
        if cached is None:
            raise ValueError('Invalid or missing forecast source')
        result[name] = (raw, cached[1].astimezone(timezone.utc))
    if clock().astimezone(BERLIN).date() != day:
        raise ValueError('Germany day changed')
    return result


def no_regression(candidate, existing):
    for name, (raw, acquired) in existing.items():
        new_raw, new_acquired = candidate[name]
        if acquired > new_acquired:
            raise Superseded('superseded')
        if acquired == new_acquired and raw != new_raw:
            raise ValueError('Equal acquisition time with conflicting bytes')


def history_hashes(root, clock):
    """Keep every history path, including unknown objects; fail on corrupt gzip/JSON."""
    import gzip
    import hashlib
    from web.history import digest
    result = {}
    _, cities = trusted_records(root)
    from web.live import IDS
    known = {str(IDS.get(c['id'], c['id'])): c for c in cities}
    library = Library(ReadOnlyDirectoryStore(root), clock, read_only=True)
    for path in (Path(root) / 'history').rglob('*'):
        if path.is_symlink():
            raise ValueError('History symlink')
        if not path.is_file():
            continue
        raw = path.read_bytes()
        name = str(path.relative_to(root))
        if name.endswith('.json.gz'):
            # Unknown version objects are retained verbatim, but must be readable.
            import io
            with gzip.GzipFile(fileobj=io.BytesIO(raw)) as stream:
                decoded = stream.read(200_001)
            if len(decoded) > 200_000:
                raise ValueError('Oversized history')
            block = json.loads(decoded)
            if block.get('sha256') != digest(block['body']):
                raise ValueError('Corrupt historical checksum')
            ident = block['body']['identity']
            city = known.get(ident.get('city_id'))
            if city and name.startswith('history/era5/temp-v1/'):
                month = path.name.removesuffix('.json.gz')
                if name != history_key(city, month) or library.read(city, month) is None:
                    raise ValueError('Corrupt historical source')
        result[name] = hashlib.sha256(raw).hexdigest()
    return result


def forecast_update(bundle, destination, clock, provider=None):
    """Ten NEW acquisitions only; no history, GeoNames, seeds or retained ledger edits."""
    from web.history import transport
    bundle, destination = Path(bundle), Path(destination)
    a, b = bundle.resolve(), destination.resolve()
    if a == b or a in b.parents or b in a.parents or destination.exists():
        raise ValueError('Use a new independent forecast store')
    records, _ = trusted_records(bundle)  # Before any provider IO.
    day = clock().astimezone(BERLIN).date()
    history_hashes(bundle, clock)
    with tempfile.TemporaryDirectory(prefix='.forecast-batch-', dir=destination.parent) as temporary:
        store = Path(temporary) / 'sources'
        stats = Cache(DirectoryStore(store), clock, daily_limit=10).prefetch(
            records, provider=provider or transport, timeout=45)
        trusted_records(bundle)
        # Only source objects leave the ephemeral store, never its admission/manifest/lock.
        destination.mkdir()
        try:
            for city in records_at(bundle)[1]:
                name = forecast_key(city, day)
                path = destination / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes((store / name).read_bytes())
            (destination / 'cities.json').write_bytes((bundle / 'cities.json').read_bytes())
            forecast_batch(destination, clock, day)
        except BaseException:
            shutil.rmtree(destination)
            raise
    return stats


def forecast_export(sources, bundle, destination, clock, day, branch=None):
    """Offline assembly on exact latest main; no writes to either input tree."""
    sources, bundle, destination = map(Path, (sources, bundle, destination))
    roots = [p.resolve() for p in (sources, bundle, destination)]
    if destination.exists() or any(a == b or a in b.parents or b in a.parents
                                  for i, a in enumerate(roots) for b in roots[i+1:]):
        raise ValueError('Use distinct non-nested trees and a new destination')
    before = tree(bundle)
    hashes = history_hashes(bundle, clock)
    candidate = forecast_batch(sources, clock, day)
    no_regression(candidate, forecast_batch(bundle, clock, day, required=False))
    if branch is not None:
        no_regression(candidate, forecast_batch(branch, clock, day, required=False))
    _, cities = trusted_records(bundle)
    prefixes = tuple(forecast_key(c, day).rsplit('/', 2)[0] + '/' for c in cities)
    objects = {n: raw for n, raw in before.items() if not n.startswith(prefixes)}
    objects.update({n: raw for n, (raw, _) in candidate.items()})
    try:
        for name, raw in objects.items():
            path = destination / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        forecast_batch(destination, clock, day)
        if history_hashes(destination, clock) != hashes or tree(bundle) != before:
            raise ValueError('History or base changed')
        if {n: b for n, b in tree(destination).items() if not n.startswith('forecast/')} != {
                n: b for n, b in before.items() if not n.startswith('forecast/')}:
            raise ValueError('Non-forecast difference')
    except BaseException:
        if destination.exists():
            shutil.rmtree(destination)
        raise
    return dict(cities=10, history_changes=0)


if __name__ == '__main__':
    raise SystemExit(main())
