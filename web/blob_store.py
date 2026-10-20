"""Optional private Vercel Blob candidate, scoped to an isolated S2 trial.

SDK import is lazy: bundled S1/local paths and standard-library tests need none.
Dedicated Preview credentials enter only the SDK factory, never output.
"""
from contextlib import contextmanager
from time import monotonic

from web.publication import LIMIT, namespace


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
def blob_session(scope, *, publisher=False):
    """Explicit SDK session: no redirects, retries, env proxy or endpoint override."""
    namespace(scope)
    try:
        import httpx2
        from vercel.api import session
        from vercel.blob import sync as sdk
    except ImportError:
        raise OSError('Optional Blob SDK unavailable; requires Python >=3.10 and requirements.txt') from None
    # Dedicated trial credentials only; never inherit a Production/default Blob
    # token or trigger the SDK's local CLI/OIDC credential refresh fallback.
    import os
    trial_store = os.environ.get('TRAVEL_PREVIEW_BLOB_STORE_ID')
    trial_token = os.environ.get('TRAVEL_PREVIEW_BLOB_TOKEN')
    if not trial_store or not trial_token:
        raise OSError('Dedicated Preview Blob configuration missing')
    options = sdk.SyncBlobServiceOptions(
        base_url='https://vercel.com/api/blob',
        credentials_factory=lambda: sdk.BlobCredentials(token=trial_token, store_id=trial_store))
    try:
        with session(service_options=[options], httpx_client_factory=lambda: httpx2.Client(
                timeout=4, follow_redirects=False, trust_env=False)):
            cls = BlobPublisher if publisher else BlobReader
            yield cls(sdk, scope, seconds=60 if publisher else 12)
    except (ValueError, OSError):
        raise
    except Exception:
        raise OSError('Private object session unavailable') from None
