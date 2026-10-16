"""Local-only Phase 2A UI server. Run: python3 -m web.server"""
import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from web.fixtures import CITIES, advice, featured, window
from web.live import Service, public_city

LIVE = Service()

ROOT = Path(__file__).parent
STATIC = {'/static/style.css': ('style.css', 'text/css'),
          '/static/app.js': ('app.js', 'text/javascript'),
          '/static/components.js': ('components.js', 'text/javascript')}


class Handler(BaseHTTPRequestHandler):
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
            query = parse_qs(url.query, keep_blank_values=True)
            if any(len(v) != 1 for v in query.values()):
                raise ValueError('查询参数不能重复。')
            p = {k: v[0] for k, v in query.items()}
            if url.path in STATIC:
                name, mime = STATIC[url.path]
                return self.send_bytes(200, (ROOT / 'static' / name).read_bytes(), mime)
            if url.path == '/api/context':
                return self.send_json(200, dict(window(), fixture_mode=self.fixtures_only))
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
                return self.send_json(200, featured(p.get('fixture', 'default')))
            if url.path == '/api/advice':
                if set(p) - {'view','city_id','start','end','preference','fixture'}:
                    raise ValueError('查询参数无效。')
                if self.fixtures_only or 'fixture' in p or p.get('view') == 'city':
                    return self.send_json(200, advice(p, p.get('fixture', 'default')))
                return self.send_json(200, self.service.advice(p))
            self.send_json(404, dict(error='页面不存在。'))
        except ValueError as exc:
            self.send_json(400, dict(error=str(exc)))
        except LookupError as exc:
            self.send_json(503, dict(error=str(exc)))

    def send_json(self, status, data):
        self.send_bytes(status, json.dumps(data, ensure_ascii=False).encode(), 'application/json')

    def send_bytes(self, status, body, mime):
        self.send_response(status)
        self.send_header('Content-Type', mime + '; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(body)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixtures', action='store_true', help='Explicit offline Phase 1 testing mode')
    parser.add_argument('--port', type=int, default=8000)
    args = parser.parse_args()
    Handler.fixtures_only = args.fixtures
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    print(f'Local travel UI: http://127.0.0.1:{args.port}', flush=True)
    server.serve_forever()
