"""Loopback Vercel handler; --synthetic is deterministic and never fetches weather."""
import argparse
import os
from datetime import timedelta
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from api.index import handler
from web.server import ThreadingHTTPServer


def synthetic_server():
    from test_forecasts import RECORDS
    from test_history import month_data
    from test_live import NOW, forecast
    from web.bundle_data import prepare
    from web.forecasts import Cache
    from web.history import Library, MemoryStore, months, windows
    from web.live import location
    from web.readonly import prepared_service

    now = [NOW]
    clock = lambda: now[0]
    store = MemoryStore()
    Cache(store, clock).prefetch(RECORDS[:1], lambda *a: forecast(NOW))
    library = Library(store, clock)
    for record in RECORDS[:2]:
        for month in months(windows(NOW.date(), NOW.date()+timedelta(days=29))):
            library.publish(location(record), month, month_data(month))

    class SyntheticHandler(handler):
        def do_POST(self):
            # Synthetic server only: temporary clock/config/metadata failure injection.
            # No provider, retained data or production endpoint.
            if self.path not in ('/__test/reset', '/__test/advance', '/__test/config-conflict', '/__test/bad-metadata'):
                return self.send_json(404, {})
            if self.path.endswith('reset'):
                now[0] = NOW
                os.environ.pop('TRAVEL_P1_READER', None)
                (target / 'cities.json').write_bytes(metadata)
            elif self.path.endswith('advance'):
                now[0] += timedelta(days=1)
            elif self.path.endswith('config-conflict'):
                os.environ['TRAVEL_P1_READER'] = 'true'
            else:
                (target / 'cities.json').write_bytes(b'[]')
            return self.send_json(200, {})

    with tempfile.TemporaryDirectory(dir=Path(__file__).parents[2]) as root:
        target = Path(root)/'bundle'
        prepare(RECORDS, store, store, target, clock)
        metadata = (target / 'cities.json').read_bytes()
        SyntheticHandler.service = prepared_service(target, clock)
        with patch.dict('os.environ', {'VERCEL_ENV': 'production'}, clear=True), \
             patch('api.index.DATASET', target), \
             patch('api.index.prepared_service', side_effect=lambda root: prepared_service(root, clock)):
            ThreadingHTTPServer(('127.0.0.1', 8007), SyntheticHandler).serve_forever()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--synthetic', action='store_true')
    if parser.parse_args().synthetic:
        synthetic_server()
    else:
        ThreadingHTTPServer(('127.0.0.1', 8007), handler).serve_forever()
