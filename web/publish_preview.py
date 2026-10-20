"""Local single-publisher CLI. Dry-run by default; no downloads or HTTP route."""
import argparse
from contextlib import contextmanager
import fcntl
import json
from pathlib import Path

from web.history import encode
from web.publication import LIMIT, announce, document, namespace, prepare, publish, sha
from web.readonly import ReadOnlyDirectoryStore


@contextmanager
def publisher_lock(path):
    # Local serialization only. Operators must ensure no other host publishes to
    # this namespace. Never claim a local flock provides distributed coordination.
    with Path(path).open('a') as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('Another local publisher is active') from None
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--namespace', required=True)
    parser.add_argument('--source', help='Combined root (default .preview-data); excludes split inputs')
    parser.add_argument('--forecast-dir', help='Existing read-only forecast cache root')
    parser.add_argument('--history-dir', help='Existing read-only history cache root')
    parser.add_argument('--cities-file', help='Existing trusted GeoNames records JSON list')
    parser.add_argument('--city-id')
    parser.add_argument('--month')
    parser.add_argument('--rollback', metavar='VERSION')
    parser.add_argument('--execute', action='store_true', help='requires separate external-write authorization')
    parser.add_argument('--lock-file', default='.preview-publisher.lock')
    args = parser.parse_args(argv)
    try:
        namespace(args.namespace)
        split = (args.forecast_dir, args.history_dir, args.cities_file)
        if any(split) and (not all(split) or args.source):
            raise ValueError('Provide all three split inputs, without --source')
        if args.rollback and (args.city_id or args.month or args.source or any(split)):
            raise ValueError('Rollback cannot include sample inputs')
        if not args.rollback:
            if not args.city_id or not args.month:
                raise ValueError('Expected --city-id and --month')
            if all(split):
                source = ReadOnlyDirectoryStore(args.forecast_dir)
                archive = ReadOnlyDirectoryStore(args.history_dir)
                # Read only the explicitly selected metadata file, bounded by the
                # same object limit. Never scan or assemble a worker/cache tree.
                with Path(args.cities_file).open('rb') as stream:
                    records = document(stream.read(LIMIT+1))
            else:
                source = ReadOnlyDirectoryStore(args.source or '.preview-data')
                archive = source
                records = document(source.get('cities.json'))
            manifest, objects = prepare(source, records, args.city_id, args.month, args.namespace,
                                        history_source=archive)
            report = dict(mode='dry_run', version=sha(encode(manifest)),
                          objects=len(objects), source_bytes=sum(len(b) for b in objects.values()))
        else:
            from web.publication import VERSION
            if not VERSION.fullmatch(args.rollback):
                raise ValueError('Invalid rollback version')
            report = dict(mode='dry_run', version=args.rollback)
        if args.execute:
            import os
            if os.environ.get('VERCEL_ENV') == 'production':
                raise ValueError('Production publication is out of scope')
            from web.blob_store import blob_session
            with publisher_lock(args.lock_file), blob_session(args.namespace, publisher=True) as remote:
                if args.rollback:
                    announce(remote, args.namespace, args.rollback)
                else:
                    publish(remote, manifest, objects)
                report.update(mode='pointer_write_acknowledged', **remote.stats)
                # Acknowledgement is not proof of hosted visibility or cache bounds.
        print(json.dumps(report, sort_keys=True))
        return 0
    except (OSError, ValueError, TypeError, LookupError, OverflowError):
        # Do not print exception chains or source content/credential details.
        print(json.dumps(dict(status='unavailable', error='Sample validation/publication failed; inspect configuration and state safely.')))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
