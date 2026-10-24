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
from web.readonly import ReadOnlyDirectoryStore


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
    f = valid_objects([forecasts, bundle], cities, clock)
    if len(f) != 10:
        raise ValueError('Export requires ten valid same-day forecasts')
    objects.update(f)
    # Routine exports retain accepted Git history bytes; local data only adds
    # missing months or repairs invalid Git objects. Forecast priority is unchanged.
    objects.update(valid_objects([bundle, history], cities, clock, history=True))
    with tempfile.TemporaryDirectory(prefix='.data-export-', dir=bundle.parent) as temporary:
        stage = Path(temporary) / 'next'
        stage.mkdir()
        for name, raw in objects.items():
            path = stage / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        if (len(valid_objects([stage], cities, clock)) != 10 or
                valid_objects([stage], cities, clock, history=True) != {
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
    parser.add_argument('command', choices=['update', 'status', 'export'])
    parser.add_argument('--forecast-dir', default='.forecast-local')
    parser.add_argument('--history-dir', default='.history-local')
    parser.add_argument('--bundle-dir', default='weather-data')
    args = parser.parse_args(argv)
    clock = lambda: datetime.now(BERLIN)
    try:
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


if __name__ == '__main__':
    raise SystemExit(main())
