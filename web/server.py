"""Local-only travel UI server. Run: python3 -m web.server"""
import argparse
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from web.fixtures import CITIES, advice, featured, pal, window
from web.live import Service, public_city, Unavailable

LIVE = Service()

ROOT = Path(__file__).parent
STATIC = {'/static/style.css': ('style.css', 'text/css'),
          '/static/app.js': ('app.js', 'text/javascript'),
          '/static/components.js': ('components.js', 'text/javascript')}
PAL_PAGES = ('/pal/berlin', '/pal/berlin/')
for _name, _mime in (('pal.js', 'text/javascript'), ('pal-audio.js', 'text/javascript'),
                     ('pal.css', 'text/css'), ('manifest.webmanifest', 'application/manifest+json'),
                     ('apple-touch-icon.png', 'image/png'), ('icon-192.png', 'image/png')):
    STATIC[f'/static/pal/{_name}'] = (f'pal/{_name}', _mime)


def local_store(root):
    """Validate configured directory access, independently of weather readiness."""
    from web.history import DirectoryStore
    store = DirectoryStore(root)
    # Listing requires read permission; resolving '.' inside requires search
    # permission too. Neither operation writes or inspects weather contents.
    with os.scandir(store.root) as entries:
        next(entries, None)
    os.stat(str(store.root) + '/.')
    return store

ICON_NAMES = {*(f'warmth-l{level}' for level in range(1, 7)),
              'alert-cold', 'alert-hot', 'alert-variation', 'alert-variation-landscape'}
for density in ('1x', '2x'):
    for name in ICON_NAMES:
        for extension in ('png', 'webp'):
            relative = f'icons/warmth/{density}/{name}.{extension}'
            STATIC[f'/static/{relative}'] = (relative, f'image/{extension}')


class Handler(BaseHTTPRequestHandler):
    allow_fixtures = True
    fixtures_only = False
    service = LIVE
    # Do not log query strings (trip inputs) or request headers.
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        url = urlsplit(self.path)
        try:
            if url.path == '/':
                return self.send_bytes(200, (ROOT / 'templates/index.html').read_bytes(), 'text/html')
            if url.path in PAL_PAGES:
                return self.send_bytes(200, (ROOT / 'templates/pal.html').read_bytes(), 'text/html')
            query = parse_qs(url.query, keep_blank_values=True)
            if any(len(v) != 1 for v in query.values()):
                raise ValueError('查询参数不能重复。')
            p = {k: v[0] for k, v in query.items()}
            if not self.allow_fixtures and 'fixture' in p:
                raise ValueError('只读服务不提供模拟数据。')
            if url.path in STATIC:
                name, mime = STATIC[url.path]
                try:
                    body = (ROOT / 'static' / name).read_bytes()
                except FileNotFoundError:
                    return self.send_json(404, dict(error='图片或文件不存在。'))
                return self.send_bytes(200, body, mime)
            if url.path == '/api/context':
                return self.send_json(200, dict(window(self.service.clock()), fixture_mode=self.fixtures_only, **getattr(self, 'context_extra', {})))
            if url.path == '/api/cities':
                if set(p) - {'q', 'fixture'}:
                    raise ValueError('查询参数无效。')
                q = p.get('q', '').strip().casefold()
                if not self.fixtures_only and 'fixture' not in p:
                    return self.send_json(200, self.service.cities(q))
                cities = [c for c in CITIES if not q or any(q in v.casefold() for v in [c['zh'], c['name'], *c['aliases']])]
                return self.send_json(200, dict(cities=cities, fixture=True))
            if url.path == '/api/city':
                if set(p) != {'city_id'}:
                    raise ValueError('查询参数无效。')
                return self.send_json(200, dict(city=public_city(self.service.resolve(p['city_id']))))
            if url.path == '/api/featured':
                if set(p) - {'fixture'}:
                    raise ValueError('查询参数无效。')
                return self.send_json(200, featured(p.get('fixture', 'default'), self.service.clock()) if self.fixtures_only or 'fixture' in p else self.service.featured())
            if url.path == '/api/pal':
                if p:
                    raise ValueError('查询参数无效。')
                return self.send_json(200, pal(self.service.clock()) if self.fixtures_only else self.service.pal())
            if url.path == '/api/advice':
                if set(p) - {'view','city_id','start','end','preference','fixture'}:
                    raise ValueError('查询参数无效。')
                if self.fixtures_only or 'fixture' in p:
                    return self.send_json(200, advice(p, p.get('fixture', 'default'), self.service.clock()))
                return self.send_json(200, self.service.city_advice(p) if p.get('view') == 'city' else self.service.advice(p))
            self.send_json(404, dict(error='页面不存在。'))
        except ValueError as exc:
            self.send_json(400, dict(error=str(exc), code="invalid_request"))
        except LookupError as exc:
            self.send_json(503, dict(error=str(exc), code=getattr(exc, "code", "temporarily_unavailable")))

    def send_json(self, status, data):
        self.send_bytes(status, json.dumps(data, ensure_ascii=False).encode(), 'application/json')

    def send_bytes(self, status, body, mime):
        self.send_response(status)
        self.send_header('Content-Type', mime if mime.startswith('image/') else mime + '; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(body)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixtures', action='store_true', help='Explicit offline Phase 1 testing mode')
    parser.add_argument('--history-dir', help='Explicit local history library (read-only in web requests; no downloads)')
    parser.add_argument('--forecast-dir', help='Explicit local shared daily forecast store')
    parser.add_argument('--port', type=int, default=8000)
    args = parser.parse_args()
    Handler.fixtures_only = args.fixtures
    from web.history import Library
    from web.forecasts import Cache
    records = []
    for root in (args.forecast_dir, args.history_dir):
        if root:
            try:
                from web.live import location
                raw = (Path(root) / 'cities.json').read_bytes()
                candidate = json.loads(raw) if len(raw) <= 200_000 else []
                if not isinstance(candidate, list):
                    raise ValueError('Expected city list')
                for record in candidate:
                    location(record)
                records.extend(candidate)
            except (OSError, ValueError, TypeError, Unavailable):
                pass
    Handler.service = Service(featured_records=records,
        history=Library(local_store(args.history_dir)) if args.history_dir else None,
        forecast_cache=Cache(local_store(args.forecast_dir)) if args.forecast_dir else None)
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    print(f'Local travel UI: http://127.0.0.1:{args.port}', flush=True)
    server.serve_forever()
