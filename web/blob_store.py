"""Optional private Vercel Blob candidate, scoped to an isolated S2 trial.

SDK import is lazy: bundled S1/local paths and standard-library tests need none.
Dedicated Preview credentials enter only the SDK factory, never output.
"""
from contextlib import contextmanager
import base64
from pathlib import Path
import re
from time import monotonic, time

from web.publication import LIMIT, document, namespace


PROJECT_LINK = Path(__file__).resolve().parents[1]/'.vercel/project.json'
PUBLISHER_PROJECT = 'travel-clothing-advisor'


def publisher_identity(token):
    """Screen CLI identity against the operator-verified repo link before Blob IO.

    This is a restrictive claims preflight, not signature verification. Blob must
    authenticate the SAME unchanged bearer on every operation; edited/forged
    claims cannot authorize a write. Never use claims to select a credential,
    endpoint or project link, and never resolve ambient SDK credentials.
    """
    try:
        if not isinstance(token, str) or len(token) > 16_384:
            raise ValueError()
        parts = token.split('.')
        if len(parts) != 3 or any(not re.fullmatch(r'[A-Za-z0-9_-]+', p) for p in parts):
            raise ValueError()
        def decode(part):
            return base64.b64decode(part+'='*(-len(part) % 4), altchars=b'-_', validate=True)
        header, claims = (document(decode(p)) for p in parts[:2])
        decode(parts[2])
        with PROJECT_LINK.open('rb') as stream:
            link = document(stream.read(16_385))
        if not isinstance(link, dict) or not isinstance(header, dict) or not isinstance(claims, dict):
            raise ValueError()
        if (header.get('alg') != 'RS256' or header.get('typ') != 'JWT' or
                not isinstance(header.get('kid'), str) or not header['kid'].strip()):
            raise ValueError()
        for name in ('iss', 'aud', 'sub', 'owner', 'owner_id', 'project', 'project_id', 'environment'):
            if not isinstance(claims.get(name), str) or not claims[name].strip():
                raise ValueError()
        owner = claims['owner']
        if (not re.fullmatch(r'[a-zA-Z0-9_-]+', owner) or
                claims['environment'] != 'preview' or claims['project'] != PUBLISHER_PROJECT or
                not isinstance(link.get('projectId'), str) or not link['projectId'].startswith('prj_') or
                not isinstance(link.get('orgId'), str) or not link['orgId'].startswith('team_') or
                claims['project_id'] != link['projectId'] or claims['owner_id'] != link['orgId'] or
                claims['iss'] not in ('https://oidc.vercel.com', 'https://oidc.vercel.com/'+owner) or
                claims['aud'] != 'https://vercel.com/'+owner or
                claims['sub'] != f'owner:{owner}:project:{PUBLISHER_PROJECT}:environment:preview'):
            raise ValueError()
        now = time()
        if (any(type(claims.get(n)) is not int for n in ('iat', 'nbf', 'exp')) or
                not claims['iat'] <= now or not claims['nbf'] <= now < claims['exp'] or
                not claims['iat'] <= claims['exp']):
            raise ValueError()
    except (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError):
        raise OSError('Local Preview OIDC identity or verified project link invalid') from None


class BlobReader:
    """The hosted adapter exposes only get; no put, lock, retry or provider."""
    def __init__(self, sdk, scope, seconds=12):
        self.sdk, self.scope = sdk, namespace(scope)
        self.deadline = monotonic()+seconds
        self.stats = dict(reads=0, writes=0, read_bytes=0, written_bytes=0, io_ms=0)

    def check(self, name):
        if (not name.startswith(self.scope+'/') or
                any(p in ('', '.', '..') for p in name.split('/'))):
            raise ValueError('Object outside Preview namespace')
        if monotonic() >= self.deadline:
            raise OSError('Object operation deadline exceeded')

    def get(self, name):
        self.check(name)
        started = monotonic()
        self.stats['reads'] += 1
        try:
            with self.sdk.stream_blob(name, access='private') as download:
                body = bytearray()
                for chunk in download:
                    self.check(name)
                    if len(body)+len(chunk) > LIMIT:
                        raise OSError('Object size limit exceeded')
                    body.extend(chunk)
                self.check(name)
                self.stats['read_bytes'] += len(body)
                return bytes(body)
        except self.sdk.BlobNotFoundError:
            return None
        except Exception:
            # SDK errors can carry request URLs, headers or credential context.
            raise OSError('Private object read unavailable') from None
        finally:
            self.stats['io_ms'] += round((monotonic()-started)*1000, 3)


class BlobPublisher(BlobReader):
    def put(self, name, raw, *, overwrite):
        self.check(name)
        if not isinstance(raw, bytes) or not 0 < len(raw) <= LIMIT:
            raise ValueError('Invalid upload size')
        started = monotonic()
        self.stats['writes'] += 1
        try:
            self.sdk.put_blob(name, raw, access='private', add_random_suffix=False,
                              allow_overwrite=overwrite, cache_control_max_age=60,
                              content_type='application/octet-stream')
            self.stats['written_bytes'] += len(raw)
        except Exception:
            raise OSError('Private object write failed; inspect state before retry') from None
        finally:
            self.stats['io_ms'] += round((monotonic()-started)*1000, 3)


@contextmanager
def blob_session(scope, *, publisher=False, request_headers=None):
    """Explicit SDK session: no redirects, retries, env proxy or endpoint override."""
    namespace(scope)
    try:
        import httpx2
        from vercel.api import session
        from vercel.blob import sync as sdk
    except ImportError:
        raise OSError('Optional Blob SDK unavailable; requires Python >=3.10 and requirements.txt') from None
    # Explicit credentials avoid the SDK's default token/CLI/file/cache fallback.
    # Runtime OIDC is delivered on the current Vercel request, not a build env var.
    import os
    trial_store = os.environ.get('TRAVEL_PREVIEW_BLOB_STORE_ID')
    if not trial_store:
        raise OSError('Dedicated Preview Blob configuration missing')
    environment = os.environ.get('VERCEL_ENV')
    if publisher:
        if (environment not in (None, 'development') or os.environ.get('VERCEL') or
                os.environ.get('VERCEL_TARGET_ENV') == 'production' or
                request_headers is not None):
            raise OSError('Blob publication requires a local publisher')
        connected_store = os.environ.get('BLOB_STORE_ID', '')
        if (not connected_store or not trial_store.removeprefix('store_') or
                connected_store.removeprefix('store_') != trial_store.removeprefix('store_')):
            raise OSError('Preview Blob store configuration mismatch')
        # CLI-provided short-lived OIDC only; never invoke SDK ambient resolution.
        trial_token = os.environ.get('VERCEL_OIDC_TOKEN')
        kind = sdk.CredentialKind.OIDC
    else:
        connected_store = os.environ.get('BLOB_STORE_ID', '')
        # The SDK accepts IDs with or without the store_ prefix.
        if (environment != 'preview' or
                connected_store.removeprefix('store_') != trial_store.removeprefix('store_')):
            raise OSError('Preview Blob store configuration mismatch')
        trial_token = (request_headers or {}).get('x-vercel-oidc-token')
        kind = sdk.CredentialKind.OIDC
    if not trial_token or not trial_token.strip():
        raise OSError('Dedicated Preview Blob credentials missing')
    if publisher:
        publisher_identity(trial_token)
    options = sdk.SyncBlobServiceOptions(
        base_url='https://vercel.com/api/blob',
        credentials_factory=lambda: sdk.BlobCredentials(
            token=trial_token, store_id=trial_store, kind=kind))
    try:
        with session(service_options=[options], httpx_client_factory=lambda: httpx2.Client(
                timeout=4, follow_redirects=False, trust_env=False)):
            cls = BlobPublisher if publisher else BlobReader
            yield cls(sdk, scope, seconds=60 if publisher else 12)
    except (ValueError, OSError):
        raise
    except Exception:
        raise OSError('Private object session unavailable') from None
