"""Synthetic S1 browser harness. No real data or upstream calls."""
from pathlib import Path
import sys
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from test_readonly import ReadOnlyTests
from api.index import handler
from web.server import ThreadingHTTPServer

TEST_NOTICE = '合成数据，仅供测试；非真实天气或历史资料'


class SyntheticHandler(handler):
    """Label synthetic transport output without replacing cache/rule execution."""
    def send_json(self, status, data):
        def label(value):
            if isinstance(value, dict):
                result = {k: label(v) for k, v in value.items()}
                if 'fixture' in result:
                    result['fixture'] = True
                if 'source' in result:
                    result['source'] = TEST_NOTICE
                return result
            if isinstance(value, list):
                return [label(item) for item in value]
            return value
        return super().send_json(status, label(data))

    def send_bytes(self, status, body, mime):
        if mime == 'text/html':
            banner = ('<div id="synthetic-test-notice" role="note" '
                      'style="background:#fff1b8;color:#332600;padding:12px;text-align:center">'
                      + TEST_NOTICE + '</div>')
            body = body.replace(b'<body>', ('<body>' + banner).encode())
        elif mime == 'text/javascript' and self.path.split('?')[0] == '/static/app.js':
            # Preserve link parameters, but make the clipboard payload test-only too.
            body = body.replace(b'copy(location.origin + location.pathname + link(',
                                ('copy(' + repr(TEST_NOTICE + '\n') +
                                 ' + location.origin + location.pathname + link(').encode())
        return super().send_bytes(status, body, mime)


if __name__ == '__main__':
    case = ReadOnlyTests()
    case.setUp()
    SyntheticHandler.service = case.service
    with patch('api.index.prepared_service', return_value=case.service):
        print('S1 synthetic-only browser harness http://127.0.0.1:8003', flush=True)
        ThreadingHTTPServer(('127.0.0.1', 8003), SyntheticHandler).serve_forever()
