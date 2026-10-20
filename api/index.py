"""Vercel Python entry; imports no provider data and never starts a server."""
import os
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
            scope = os.environ.get('TRAVEL_PREVIEW_NAMESPACE')
            if scope is None:
                self.service = prepared_service(DATASET)
            else:
                if os.environ.get('VERCEL_ENV') != 'preview':
                    raise Unavailable('独立数据发布仅供受保护的 Preview 验证。')
                from web.blob_store import blob_session
                from web.publication import published_service
                with blob_session(scope) as remote:
                    self.service = published_service(remote, scope)
        except (OSError, ValueError):
            return self.send_json(503, dict(error='独立数据存储尚未配置或暂不可用。', code='temporarily_unavailable'))
        except Unavailable as exc:
            return self.send_json(503, dict(error=str(exc), code=exc.code))
        return super().do_GET()

    def send_json(self, status, data):
        store = self.service.forecasts.store
        version = getattr(store, 'version', None)
        if status == 200 and version:
            data = dict(data, dataset_version=version)
        return super().send_json(status, data)
