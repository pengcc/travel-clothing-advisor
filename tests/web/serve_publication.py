"""Synthetic-only S2 browser harness; stdin controls, never HTTP writes."""
from contextlib import contextmanager
from pathlib import Path
import json
import sys
import threading
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from test_publication import PublicationTests, SCOPE
from serve_readonly import SyntheticHandler
from web.publication import publish, published_service
from web.server import ThreadingHTTPServer

if __name__ == '__main__':
    case = PublicationTests()
    case.setUp()
    first = publish(case.remote, case.manifest, case.objects, case.clock)
    @contextmanager
    def connection(scope):
        yield case.remote
    server = ThreadingHTTPServer(('127.0.0.1', 8004), SyntheticHandler)
    with patch.dict('os.environ', dict(TRAVEL_PREVIEW_NAMESPACE=SCOPE, VERCEL_ENV='preview')), \
         patch('web.blob_store.blob_session', connection), \
         patch('web.publication.published_service', side_effect=lambda r,s: published_service(r,s,case.clock)):
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        print(json.dumps(dict(event='ready', version=first, source_bytes=sum(map(len,case.objects.values())))), flush=True)
        try:
            for line in sys.stdin:
                command = line.strip()
                if command == 'publish':
                    version = publish(case.remote, *case.second(), case.clock)
                elif command == 'rollback':
                    from web.publication import announce
                    announce(case.remote, SCOPE, first, case.clock)
                    version = first
                else:
                    break
                print(json.dumps(dict(event=command, version=version)), flush=True)
        finally:
            server.shutdown(); server.server_close(); thread.join()
