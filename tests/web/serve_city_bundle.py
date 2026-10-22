"""Serve the actual bundled-data Vercel handler locally, without remote stores."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from api.index import handler
from web.server import ThreadingHTTPServer

if __name__ == '__main__':
    ThreadingHTTPServer(('127.0.0.1', 8007), handler).serve_forever()
