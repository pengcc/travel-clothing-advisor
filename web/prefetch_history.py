"""Manual local history worker. Defaults to offline planning; --download opts into IO.

A resolved city manifest is required (GeoNames provider records; no personal data).
Creating/maintaining it is explicit and separate from month downloads.
"""
import argparse
from datetime import date, datetime
import json
from pathlib import Path

from web.fixtures import BERLIN, CITIES
from web.history import DirectoryStore, Library, Downloader, plan
from web.live import IDS, location, Unavailable


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--store', default='.history-local')
    parser.add_argument('--cities-file', required=True, help='JSON list of server-verified GeoNames /v1/get records')
    parser.add_argument('--today', type=date.fromisoformat, help='Offline plan date only')
    parser.add_argument('--full-years', action='store_true', help='Append annual backfill after priority months')
    parser.add_argument('--download', action='store_true', help='Explicit live IO; obtain separate approval before use')
    parser.add_argument('--batch-calls', type=int, default=30)
    parser.add_argument('--daily-calls', type=int, default=60)
    parser.add_argument('--monthly-calls', type=int, default=600)
    parser.add_argument('--max-blocks', type=int, default=5)
    parser.add_argument('--timeout', type=float, default=30)
    args = parser.parse_args(argv)
    if args.download and args.today:
        parser.error('--today is only allowed for offline planning')
    raw = json.loads(Path(args.cities_file).read_text())
    if not isinstance(raw,list):
        parser.error('cities-file must be a list')
    cities = [location(item) for item in raw]
    if len({c['id'] for c in cities}) != len(cities):
        parser.error('duplicate city IDs')
    # Featured cities always precede additional German cities in each priority tier.
    featured = [c['id'] for c in CITIES[:10]]
    cities.sort(key=lambda c: featured.index(c['id']) if c['id'] in featured else len(featured))
    today = args.today or datetime.now(BERLIN).date()
    library = Library(DirectoryStore(args.store))
    jobs = plan(cities,today,args.full_years)
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
