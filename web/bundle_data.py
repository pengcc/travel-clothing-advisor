"""Export only validated weather objects from existing local caches, without IO to providers."""
import argparse
from datetime import date, datetime
import json
from pathlib import Path

from web.fixtures import BERLIN
from web.forecasts import Cache, key as forecast_key
from web.history import Library, encode, key as history_key, months, windows
from web.live import location
from web.readonly import ReadOnlyDirectoryStore


def prepare(records, forecasts, history, destination, clock=lambda: datetime.now(BERLIN)):
    cities = [location(r) for r in records]
    if not cities or len({c['id'] for c in cities}) != len(cities):
        raise ValueError('Expected distinct verified city records')
    now = clock().astimezone(BERLIN)
    from web.fixtures import window
    w = window(now)
    objects = {'cities.json': encode(records)}
    cache = Cache(forecasts, clock, read_only=True)
    library = Library(history, clock, read_only=True)
    for city in cities:
        if cache.read(city, now.date()) is not None:
            name = forecast_key(city, now.date())
            objects[name] = forecasts.get(name)
        # Export individually valid months; the reader still requires all five
        # complete samples for the requested window, including after midnight.
        for month in months(windows(date.fromisoformat(w['today']), date.fromisoformat(w['max_date']))):
            if library.read(city, month) is not None:
                name = history_key(city, month)
                objects[name] = history.get(name)
    if clock().astimezone(BERLIN).date() != now.date():
        raise ValueError('Germany date changed; retry export')
    destination = Path(destination)
    if destination.exists():
        raise ValueError('Use a new destination; replace the reviewed bundle explicitly')
    for name, data in objects.items():
        path = destination / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return len(objects)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cities-file', required=True)
    parser.add_argument('--forecast-dir', default='.forecast-local')
    parser.add_argument('--history-dir', default='.history-local')
    parser.add_argument('--output', required=True, help='New directory; existing directories are never overwritten')
    args = parser.parse_args(argv)
    source = Path(args.cities_file)
    if source.stat().st_size > 200_000:
        raise ValueError('Oversized city manifest')
    records = json.loads(source.read_text())
    if not isinstance(records, list):
        raise ValueError('Expected city list')
    count = prepare(records, ReadOnlyDirectoryStore(args.forecast_dir),
                    ReadOnlyDirectoryStore(args.history_dir), args.output)
    print(json.dumps(dict(validated_objects=count)))


if __name__ == '__main__':
    main()
