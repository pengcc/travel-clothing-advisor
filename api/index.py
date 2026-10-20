"""Vercel Python entry; imports no provider data and never starts a server."""
from pathlib import Path
from urllib.parse import urlsplit

from web.live import Unavailable
from web.readonly import prepared_service, service, ReadOnlyDirectoryStore
from web.server import Handler

DATASET = Path(__file__).resolve().parents[1] / '.preview-data'


class handler(Handler):
    allow_fixtures = False
    service = service(ReadOnlyDirectoryStore(DATASET), [])

    def do_GET(self):
        # Serve the UI/context even before operator data is available, so the
        # existing error panel can explain unavailable advice.
        path = urlsplit(self.path).path
        if path == '/' or path.startswith('/static/') or path == '/api/context':
            return super().do_GET()
        try:
            self.service = prepared_service(DATASET)
        except Unavailable as exc:
            return self.send_json(503, dict(error=str(exc), code=exc.code))
        return super().do_GET()
