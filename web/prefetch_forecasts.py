"""Operator-only daily forecast preparation. No public refresh endpoint or scheduler."""
import argparse
import json
from pathlib import Path
from web.forecasts import Cache, DirectoryStore
from web.live import Unavailable


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cities-file', required=True, help='Local JSON list of ten verified GeoNames records')
    parser.add_argument('--store-dir', default='.forecast-local', help='Local development store only')
    parser.add_argument('--timeout', type=float, default=45, help='Whole invocation seconds, maximum 60')
    args = parser.parse_args(argv)
    cache = None
    try:
        source = Path(args.cities_file)
        if source.stat().st_size > 100_000:
            raise ValueError()
        records = json.loads(source.read_text())
        if not isinstance(records, list):
            raise ValueError()
        cache = Cache(DirectoryStore(args.store_dir))
        stats = cache.prefetch(records, timeout=args.timeout)
    except (OSError, ValueError, TypeError, KeyError, Unavailable):
        stats = getattr(cache, 'stats', dict(forecast_attempts=0, geocoding_attempts=0,
                         hits=0, published=0, failed=0, complete=False))
        print(json.dumps(dict(status='unavailable', **stats), sort_keys=True))
        return 1
    print(json.dumps(dict(status='complete', **stats), sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
