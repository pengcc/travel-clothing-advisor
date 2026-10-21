"""Default-inert P1 hourly worker. No DB bootstrap, geocoding or CLI fallback."""
from datetime import datetime
from email.utils import parsedate_to_datetime
import os
from pathlib import Path
from time import monotonic
from urllib.error import HTTPError

from web.fixtures import BERLIN
from web.forecasts import identity,pack
import json
from urllib.parse import urlencode
from urllib.request import build_opener, ProxyHandler, HTTPRedirectHandler
from web.live import FORECAST,parse_hours
from web.lifecycle import Config,records,publication,put_object


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        return None


def weather_transport(url,params,timeout):
    """One charged HTTP attempt: no ambient proxies, redirects or retries."""
    if url!=FORECAST or not 0<timeout<=4:
        raise ValueError('Invalid provider request')
    deadline=monotonic()+timeout
    opener=build_opener(ProxyHandler({}),NoRedirect())
    with opener.open(url+'?'+urlencode(params),timeout=timeout) as response:
        raw=bytearray()
        while not response.isclosed():
            if monotonic()>=deadline:
                raise TimeoutError()
            response.fp.raw._sock.settimeout(max(0.001,deadline-monotonic()))
            chunk=response.read1(65536)
            if not chunk:
                break
            raw.extend(chunk)
            if len(raw)>200000:
                raise ValueError('Oversized weather response')
        return json.loads(raw)


def run(control, remote, cfg, raw_records, *, provider=weather_transport,
        clock=lambda:datetime.now(BERLIN), timer=monotonic):
    _,cities = records(raw_records,cfg)
    by_id = {c['id']:c for c in cities}
    deadline = timer()+120
    day,versions = control.reconcile()
    attempts=0
    for _ in range(10):
        if timer()+20>=deadline:
            break
        claim = control.claim(day)
        if claim is None:
            break
        ident,generation = claim
        city=by_id[ident]
        control.verify_claim(day,ident,generation)
        attempts+=1
        cooldown=300
        try:
            data=provider(FORECAST,dict(latitude=city['latitude'],longitude=city['longitude'],
                          hourly='temperature_2m',forecast_days=14,timezone='Europe/Berlin',
                          timeformat='unixtime',temperature_unit='celsius',models='best_match'),4)
            acquired=clock().astimezone(BERLIN)
            if acquired.date()!=day or timer()>=deadline:
                raise ValueError('Date/deadline changed')
            parse_hours(data,acquired)
            raw=pack(dict(identity=identity(city,day),source=FORECAST,
                          weather_fetched_at=acquired.isoformat(),response=data))
            control.verify_claim(day,ident,generation)
            version=put_object(remote,cfg,raw)
        except (OSError,ValueError,LookupError,TypeError,KeyError) as exc:
            if isinstance(exc,HTTPError):
                retry=exc.headers.get('Retry-After','')
                if retry.isdigit():
                    cooldown=max(300,int(retry))
                elif retry:
                    try:
                        cooldown=max(300,int((parsedate_to_datetime(retry)-clock()).total_seconds()))
                    except (ValueError,TypeError):
                        pass
            control.finish(day,ident,generation,cooldown=cooldown)
            continue
        control.finish(day,ident,generation,version)
    # Reconcile committed city state, including a prior ambiguous finish commit.
    current_day,versions=control.reconcile()
    complete=False
    if current_day==day and all(versions.values()) and timer()+8<deadline:
        raw,_=publication(remote,cfg,raw_records,versions,clock)
        version=put_object(remote,cfg,raw)
        control.commit(day,versions,version)
        complete=True
    return dict(complete=complete,attempts=attempts,
                failed_checkpoint=not complete and clock().astimezone(BERLIN).hour>=12)


def main():
    if os.environ.get('TRAVEL_P1_ENABLED')!='true':
        print('P1 disabled; no external operations.')
        return 0
    try:
        cfg=Config.environment(os.environ,worker=True)
        # Explicit input path; no ambient cache or fixture metadata discovery.
        path=Path(os.environ.get('TRAVEL_P1_RECORDS_FILE',''))
        with path.open('rb') as stream:
            raw=stream.read(200001)
        records(raw,cfg)
        dsn=cfg.dsn(os.environ.get('TRAVEL_P1_WORKER_DSN'))
        if not os.environ.get('TRAVEL_P1_BLOB_WRITE_TOKEN'):
            raise ValueError('Missing worker credential')
        from web.control_store import Control
        from web.production_store import production_session
        control=Control(cfg,dsn)
        # Verify activation before the first Blob/provider operation.
        with control.transaction() as c:
            control.check(c)
        with production_session(cfg,publisher=True) as remote:
            result=run(control,remote,cfg,raw)
        print('P1 cycle:',result)  # only bounded counters; never exception text
        return 1 if result['failed_checkpoint'] else 0
    except Exception:
        print('P1 cycle failed; configuration, control or data unavailable. No unsafe fallback.')
        return 1


if __name__=='__main__':
    raise SystemExit(main())
