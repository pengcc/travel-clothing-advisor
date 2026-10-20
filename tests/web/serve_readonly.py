"""Synthetic S1 browser harness. No real data or upstream calls."""
from pathlib import Path
import sys
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from test_readonly import ReadOnlyTests
from api.index import handler
from web.server import ThreadingHTTPServer

if __name__ == '__main__':
    case = ReadOnlyTests()
    case.setUp()
    class SyntheticHandler(handler):
        service = case.service
    with patch('api.index.prepared_service', return_value=case.service):
        print('S1 synthetic-only browser harness http://127.0.0.1:8003', flush=True)
        ThreadingHTTPServer(('127.0.0.1', 8003), SyntheticHandler).serve_forever()
