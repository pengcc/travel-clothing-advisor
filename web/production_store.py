"""Separate Production immutable Blob capability; S2 Preview guards stay intact."""
import base64
from contextlib import contextmanager
import os
import re
from time import monotonic,time

from web.publication import document,LIMIT
from web.live import Unavailable


def reader_identity(token,cfg):
    # Restrictive screening only. Blob authenticates the SAME bearer/signature.
    try:
        parts=token.split('.')
        if len(token)>16384 or len(parts)!=3 or any(not re.fullmatch(r'[A-Za-z0-9_-]+',p) for p in parts):
            raise ValueError()
        header,claims=[document(base64.urlsafe_b64decode(p+'='*(-len(p)%4))) for p in parts[:2]]
        owner=claims['owner']
        if (header.get('alg')!='RS256' or header.get('typ')!='JWT' or not header.get('kid') or
                claims['environment']!='production' or claims['project_id']!=cfg.project or
                claims['owner_id']!=cfg.owner or claims['project']!='travel-clothing-advisor' or
                claims['aud']!='https://vercel.com/'+owner or
                claims['iss'] not in ('https://oidc.vercel.com','https://oidc.vercel.com/'+owner) or
                claims['sub']!=f'owner:{owner}:project:travel-clothing-advisor:environment:production' or
                any(type(claims.get(k)) is not int for k in ('iat','nbf','exp')) or
                not claims['iat']<=time() or not claims['nbf']<=time()<claims['exp']):
            raise ValueError()
    except Exception:
        raise ValueError('Production request identity invalid') from None


class Reader:
    def __init__(self,sdk,cfg,seconds=12):
        self.sdk,self.cfg,self.deadline=sdk,cfg,monotonic()+seconds
        self.stats=dict(reads=0,writes=0,read_bytes=0,written_bytes=0)

    def check(self,name):
        if (not re.fullmatch(re.escape(self.cfg.domain)+r'/objects/[a-f0-9]{64}',name) or
                monotonic()>=self.deadline):
            raise ValueError('Invalid immutable object operation')

    def get(self,name):
        self.check(name)
        try:
            self.stats['reads']+=1
            with self.sdk.stream_blob(name,access='private') as response:
                raw=bytearray()
                for chunk in response:
                    self.check(name)
                    raw.extend(chunk)
                    if len(raw)>LIMIT:
                        raise ValueError('Object too large')
                self.check(name)
                self.stats['read_bytes']+=len(raw)
                return bytes(raw)
        except self.sdk.BlobNotFoundError:
            return None
        except Exception:
            raise OSError('Production immutable read unavailable') from None


class Publisher(Reader):
    def put(self,name,raw):
        self.check(name)
        if not isinstance(raw,bytes) or not 0<len(raw)<=LIMIT:
            raise ValueError('Invalid immutable bytes')
        try:
            self.stats['writes']+=1
            self.sdk.put_blob(name,raw,access='private',add_random_suffix=False,
                              allow_overwrite=False,content_type='application/octet-stream')
            self.stats['written_bytes']+=len(raw)
        except Exception:
            raise OSError('Immutable write uncertain; reconcile before retry') from None


@contextmanager
def production_session(cfg,*,publisher=False,request_headers=None):
    # Caller must first validate Config and DB activation. Never resolve ambient
    # credentials, CLI refresh, URLs or a Preview namespace.
    if publisher:
        from web.lifecycle import Config as ConfigEnv
        if ConfigEnv.environment(os.environ,worker=True)!=cfg or request_headers is not None:
            raise ValueError('Invalid worker target')
        token=os.environ.get('TRAVEL_P1_BLOB_WRITE_TOKEN','')
        prefix='vercel_blob_rw_'+cfg.store.removeprefix('store_')+'_'
        if not token.startswith(prefix) or len(token)<=len(prefix):
            raise ValueError('Dedicated store credential mismatch')
    else:
        from web.lifecycle import Config as ConfigEnv
        if ConfigEnv.environment(os.environ)!=cfg:
            raise ValueError('Invalid reader target')
        token=(request_headers or {}).get('x-vercel-oidc-token','')
        reader_identity(token,cfg)
    try:
        import httpx2
        from vercel.api import session
        from vercel.blob import sync as sdk
        options=sdk.SyncBlobServiceOptions(base_url='https://vercel.com/api/blob',
                    credentials_factory=lambda:sdk.BlobCredentials(token=token,store_id=cfg.store,
                        kind=sdk.CredentialKind.READ_WRITE if publisher else sdk.CredentialKind.OIDC))
        with session(service_options=[options],httpx_client_factory=lambda:httpx2.Client(
                timeout=4,follow_redirects=False,trust_env=False)):
            yield (Publisher(sdk,cfg,120) if publisher else Reader(sdk,cfg))
    except (ValueError,OSError,Unavailable):
        raise
    except Exception:
        raise OSError('Production object session unavailable') from None
