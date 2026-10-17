"""Offline browser acceptance server; synthetic provider, no upstream network.

python3 tests/web/serve_forecasts.py [--port 8002]
"""
import argparse
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from test_live import NOW, Fake, geo
from test_forecasts import RECORDS
from web.forecasts import Cache, MemoryStore
from web.live import Service
from web.server import Handler, ThreadingHTTPServer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8002)
    args = parser.parse_args()
    fake = Fake()
    cache = Cache(MemoryStore(), lambda: NOW)
    cache.prefetch(RECORDS, lambda u,p,t: fake(u,p))
    def provider(url, params):
        if url.endswith('/get'):
            return geo(int(params['id']))
        return fake(url, params)
    Handler.service = Service(provider, lambda: NOW, forecast_cache=cache)
    print('Offline synthetic provider: 10 forecast attempts; prefetch rerun ' +
          str(cache.prefetch(RECORDS, lambda u,p,t: fake(u,p))), flush=True)
    ThreadingHTTPServer(('127.0.0.1', args.port), Handler).serve_forever()


if __name__ == '__main__':
    main()
