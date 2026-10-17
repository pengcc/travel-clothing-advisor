"""Manual local history worker. Defaults to offline planning; --download opts into IO.

A resolved city manifest is required (GeoNames provider records; no personal data).
Creating it with --resolve-cities makes LIVE GeoNames requests and requires separate approval.
"""
import argparse
from datetime import date, datetime
import json
from pathlib import Path

from web.fixtures import BERLIN, CITIES
from web.history import DirectoryStore, Library, Downloader, plan, windows, months
from web.live import GEO, IDS, fetch_json, location, Unavailable


class ReadOnlyDirectoryStore(DirectoryStore):
    """Inspection only: no directory creation, lock file, ledger or writes.

    Objects are atomically replaced by the worker. A report is an observation,
    not a locked snapshot or a guarantee about a later request.
    """
    def __init__(self, root):
        self.root = Path(root).resolve()
        if not self.root.is_dir():
            raise OSError('Store directory unavailable')

    def put(self, name, data):
        raise OSError('Read-only store')

    def exclusive(self):
        raise OSError('Read-only inspection does not acquire a worker lock')


def coverage(cities, start, end, store):
    needed = months(windows(start, end))
    report = dict(status='unconfigured' if store is None else 'complete',
                  required_months=needed, cities=[], http_requests=0)
    if store is None:
        return report
    try:
        library = Library(ReadOnlyDirectoryStore(store))
    except OSError:
        report['status'] = 'unreadable'
        return report
    for city in cities:
        blocks = {}
        for month in needed:
            try:
                blocks[month] = 'valid' if library.read(city, month) else 'missing_or_invalid'
            except OSError:
                blocks[month] = 'unreadable'
        report['cities'].append(dict(city_id=city['id'], months=blocks,
            missing_equivalent_calls=sum(Downloader.cost(m) for m,s in blocks.items()
                                         if s == 'missing_or_invalid')))
    states = {s for c in report['cities'] for s in c['months'].values()}
    report['status'] = ('unreadable' if 'unreadable' in states else
                        'incomplete' if 'missing_or_invalid' in states else 'complete')
    return report


def resolve_manifest(city_ids, destination, fetch=fetch_json):
    """Explicit live initialization, validate every record before publishing a new file."""
    records = []
    for city_id in city_ids:
        provider_id = IDS[city_id]
        raw = fetch(GEO+'get', dict(id=provider_id))
        location(raw)
        if raw['id'] != provider_id:
            raise Unavailable('City identity mismatch')
        # Retain only the provider fields consumed by location(), never arbitrary payloads.
        records.append({k:raw[k] for k in
                        ('id','name','admin1','country_code','feature_code','latitude','longitude')})
    # Never overwrite an operator's existing trusted manifest.
    with Path(destination).open('x') as output:
        json.dump(records, output, ensure_ascii=False)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--store', help='Actual history directory; omitted --check reports unconfigured')
    parser.add_argument('--cities-file', required=True, help='JSON list of server-verified GeoNames /v1/get records')
    parser.add_argument('--resolve-cities', action='store_true', help='LIVE GeoNames initialization; separate approval required; creates cities-file')
    parser.add_argument('--city-id', action='append', choices=list(IDS), help='Select known city; repeat for several cities')
    parser.add_argument('--check', action='store_true', help='Read-only exact-trip coverage; no writes or requests')
    parser.add_argument('--start', type=date.fromisoformat)
    parser.add_argument('--end', type=date.fromisoformat)
    parser.add_argument('--today', type=date.fromisoformat, help='Offline plan date only')
    parser.add_argument('--full-years', action='store_true', help='Append annual backfill after priority months')
    parser.add_argument('--download', action='store_true', help='Explicit live IO; obtain separate approval before use')
    parser.add_argument('--batch-calls', type=int, default=30)
    parser.add_argument('--daily-calls', type=int, default=60)
    parser.add_argument('--monthly-calls', type=int, default=600)
    parser.add_argument('--max-blocks', type=int, default=5)
    parser.add_argument('--timeout', type=float, default=30)
    args = parser.parse_args(argv)
    if args.resolve_cities:
        if args.download or args.check or args.start or args.end or args.today or args.full_years:
            parser.error('--resolve-cities cannot be combined with planning, checking or downloading')
        selected = args.city_id or [c['id'] for c in CITIES[:10]]
        if len(set(selected)) != len(selected):
            parser.error('duplicate city IDs')
        try:
            if Path(args.cities_file).exists():
                parser.error('cities-file already exists; choose a new destination')
            resolve_manifest(selected, args.cities_file)
        except (OSError, ValueError, Unavailable):
            print(json.dumps(dict(status='metadata_unavailable')))
            return 1
        print(json.dumps(dict(status='complete', geocoding_requests=len(selected))))
        return 0
    if bool(args.start) != bool(args.end) or (args.check and not args.start):
        parser.error('--start and --end are required together; --check requires both')
    if args.check and args.download:
        parser.error('--check cannot download')
    if args.start and (args.today or args.full_years):
        parser.error('exact-trip dates cannot be combined with --today or --full-years')
    if args.start:
        try:
            needed = months(windows(args.start, args.end))
        except ValueError:
            parser.error('Historical trips must contain 1–30 calendar days')
    if args.download and args.today:
        parser.error('--today is only allowed for offline planning')
    try:
        raw = json.loads(Path(args.cities_file).read_text())
        if not isinstance(raw, list):
            parser.error('cities-file must be a list')
        cities = [location(item) for item in raw]
    except (OSError, ValueError, Unavailable):
        parser.error('cities-file unavailable or contains invalid city metadata')
    if len({c['id'] for c in cities}) != len(cities):
        parser.error('duplicate city IDs')
    if not cities:
        parser.error('cities-file must contain at least one verified record')
    if args.city_id:
        selected = set(args.city_id)
        if selected - {c['id'] for c in cities}:
            parser.error('selected cities are absent from verified manifest')
        cities = [c for c in cities if c['id'] in selected]
    if args.check:
        report = coverage(cities, args.start, args.end, args.store)
        print(json.dumps(report, sort_keys=True))
        return 0 if report['status'] == 'complete' else 1
    # Featured cities always precede additional German cities in each priority tier.
    featured = [c['id'] for c in CITIES[:10]]
    cities.sort(key=lambda c: featured.index(c['id']) if c['id'] in featured else len(featured))
    today = args.today or datetime.now(BERLIN).date()
    library = Library(DirectoryStore(args.store or '.history-local'))
    jobs = ([(c,m) for c in cities for m in needed] if args.start else
            plan(cities,today,args.full_years))
    worker = Downloader(library,batch=args.batch_calls,daily=args.daily_calls,
                        monthly=args.monthly_calls,max_blocks=args.max_blocks,timeout=args.timeout)
    if not args.download:
        with library.store.exclusive():
            missing = [(c,m) for c,m in jobs if library.read(c,m) is None]
        print(json.dumps(dict(blocks=len(jobs), missing=len(missing),
                              equivalent_calls=sum(worker.cost(m) for _,m in missing),
                              featured_cities=sum(c['id'] in featured for c in cities),
                              http_requests=0),sort_keys=True))
        return 0
    try:
        worker.fill(jobs)
        status = 'complete'
    except (Unavailable, OSError):
        status = 'paused'  # No provider messages, paths, trip inputs, or headers in logs.
    print(json.dumps(dict(status=status,**worker.stats),sort_keys=True))
    return 0 if status=='complete' else 1


if __name__ == '__main__':
    raise SystemExit(main())
