"""P1 synthetic browser harness. No HTTP mutation or real provider/DB/Blob."""
from pathlib import Path
import json
import sys
import threading
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from test_lifecycle import LifecycleTests,CFG,RAW
from serve_readonly import SyntheticHandler
from web.lifecycle import production_service
from web.server import ThreadingHTTPServer

if __name__=='__main__':
    case=LifecycleTests()
    case.setUp()
    case.cycle()
    complete=case.control.committed
    state=['complete']
    def app(*args):
        return production_service(case.control,case.remote,CFG,RAW,clock=lambda:case.now)
    case.control.snapshot=lambda:(case.control.day,complete if state[0]=='complete' else None,state[0])
    SyntheticHandler.service=app()
    server=ThreadingHTTPServer(('127.0.0.1',8005),SyntheticHandler)
    with patch('api.index.prepared_service',side_effect=app):
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        print(json.dumps(dict(event='ready')),flush=True)
        try:
            for line in sys.stdin:
                if line.strip()=='stop':
                    break
                state[0]=line.strip()
                print(json.dumps(dict(event=state[0])),flush=True)
        finally:
            server.shutdown();server.server_close();thread.join()
