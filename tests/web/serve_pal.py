"""Synthetic 穿衣小伙伴 browser harness (Issue #101). No real data, no upstream calls.

Run: python3 tests/web/serve_pal.py   (http://127.0.0.1:8008/pal  or  /pal/berlin, /pal/munich, ...)
Uses the real Berlin clock with a synthetic same-day snapshot so the page's own
timestamp checks behave like production; every response is labelled fixture:true.
"""
from datetime import datetime
from pathlib import Path
import sys
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from test_forecasts import RECORDS
from test_pal import put_snapshot
from api.index import handler
from web.live import location
from web.fixtures import BERLIN
from web.history import MemoryStore
from web.readonly import service
from web.server import ThreadingHTTPServer


class SyntheticHandler(handler):
    def send_json(self, status, data):
        if isinstance(data, dict) and 'days' in data:
            data = dict(data, fixture=True)
        return super().send_json(status, data)


def synthetic_service():
    clock = lambda: datetime.now(BERLIN)
    store = MemoryStore()
    now = clock()
    for record in RECORDS[:10]:                      # every featured city, so every /pal/<city> page has data
        put_snapshot(store, now.date(), now, city=location(record))
    svc = service(store, RECORDS, clock, independent_cities=True)
    svc.fetch = lambda *a, **k: (_ for _ in ()).throw(AssertionError('provider called'))
    return svc


if __name__ == '__main__':
    svc = synthetic_service()
    SyntheticHandler.service = svc
    with patch('api.index.prepared_service', return_value=svc):
        print('穿衣小伙伴 synthetic harness http://127.0.0.1:8008/pal/berlin', flush=True)
        ThreadingHTTPServer(('127.0.0.1', 8008), SyntheticHandler).serve_forever()
