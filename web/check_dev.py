"""Read-only local launch preflight; never prepares stores or calls providers."""
import argparse
import os
from contextlib import nullcontext
from pathlib import Path

from web.forecasts import Cache
from web.live import Service, Unavailable
from web.prefetch_history import ReadOnlyDirectoryStore


class ForecastInspectionStore(ReadOnlyDirectoryStore):
    def exclusive(self):
        # Atomic files can be inspected without creating a worker lock. This is
        # an observation, not a locked snapshot or a promise about later reads.
        return nullcontext()


def check(history_dir, forecast_dir, emit=print):
    ready = True
    for label, root in (('History', history_dir), ('Forecast', forecast_dir)):
        try:
            path = Path(root)
            if not path.is_dir():
                raise OSError()
            # Check directory listing access, not only existence.
            with os.scandir(path) as entries:
                next(entries, None)
        except OSError:
            emit(f'{label} directory missing or unreadable. See web/README.md local preparation; no directory was created.')
            ready = False
    if not ready:
        emit('Local server was not started. Prepare stores explicitly; no downloads or writes were performed. For offline fixtures use make demo.')
        return False

    try:
        # A library is trip-specific; the generic launch cannot certify coverage.
        blocks = Path(history_dir).glob('history/era5/temp-v1/*/*/*.json.gz')
        first = next(blocks, None)
        if first is None:
            emit('History library is unprepared (no month blocks). Prepare it explicitly; see web/README.md.')
            ready = False
        else:
            with first.open('rb') as handle:
                handle.read(1)
            emit('History blocks found; exact-trip coverage is NOT validated. Use web.prefetch_history --check for your city and dates.')
    except OSError:
        emit('History blocks are unreadable. Check local preparation and access.')
        ready = False

    try:
        cache = Cache(ForecastInspectionStore(forecast_dir))
        cache.featured(Service(forecast_cache=cache))
        emit('Forecast: complete Germany-today featured publication validated (read-only).')
    except (OSError, Unavailable):
        emit('Forecast publication missing, stale, incomplete, invalid or unreadable. Prepare today explicitly with web.prefetch_forecasts; see web/README.md.')
        ready = False
    if not ready:
        emit('Local server was not started. No downloads or cache writes were performed. For offline fixtures use make demo.')
    return ready


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--history-dir', required=True)
    parser.add_argument('--forecast-dir', required=True)
    args = parser.parse_args(argv)
    return 0 if check(args.history_dir, args.forecast_dir) else 1


if __name__ == '__main__':
    raise SystemExit(main())
