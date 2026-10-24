"""Fixed 2021–2025 inventory and explicitly opted-in local ERA5 backfill."""
import argparse
from datetime import datetime
import json
import math
from pathlib import Path
import sys

from web.data_commands import records_at
from web.fixtures import BERLIN
from web.history import (Library, DirectoryStore, Downloader, BackfillPaused,
                         key, plan, transport, LEDGER)
from web.live import Unavailable
from web.readonly import ReadOnlyDirectoryStore

MONTHS = tuple(f'{year}-{month:02d}' for year in range(2021, 2026) for month in range(1, 13))


def inspect(root, city, month, clock):
    """Validate exactly the observed bytes, preserving missing/invalid/outage states."""
    store = ReadOnlyDirectoryStore(root)
    try:
        # A nonexistent store is known absent; a file in place of a root is an outage.
        if store.root.exists() and not store.root.is_dir():
            raise OSError()
        raw = store.get(key(city, month))
        if raw is None:
            return 'missing', None
        class Snapshot:
            def get(self, name):
                return raw
        valid = Library(Snapshot(), clock, read_only=True).read(city, month) is not None
        return ('valid', raw) if valid else ('invalid', None)
    except OSError:
        return 'unreadable', None


def inventory(cities, local, bundle, clock):
    rows = []
    for city in cities:
        blocks = {}
        for month in MONTHS:
            l, _ = inspect(local, city, month, clock)
            g, _ = inspect(bundle, city, month, clock)
            source = 'local' if l == 'valid' else 'git' if g == 'valid' else None
            state = ('valid' if source else 'unreadable' if 'unreadable' in (l, g)
                     else 'invalid' if 'invalid' in (l, g) else 'missing')
            blocks[month] = dict(state=state, source=source, local=l, git=g)
        counts = {s: sum(b['state'] == s for b in blocks.values())
                  for s in ('valid', 'missing', 'invalid', 'unreadable')}
        rows.append(dict(city_id=city['id'], months=blocks, **counts))
    counts = {s: sum(r[s] for r in rows) for s in ('valid', 'missing', 'invalid', 'unreadable')}
    unreadable = any(b[s] == 'unreadable' for r in rows for b in r['months'].values()
                     for s in ('local', 'git'))
    missing = [(c, m) for c, r in zip(cities, rows) for m, b in r['months'].items()
               if b['state'] in ('missing', 'invalid')]
    return dict(status='unreadable' if unreadable else 'complete' if counts['valid'] == 600 else 'partial',
                total=600, remaining=600-counts['valid'], equivalent_calls=sum(Downloader.cost(m) for _, m in missing),
                http_requests=0, cities=rows, **counts)


def backfill(cities, local, bundle, clock, *, download=False, seed=False,
             provider=transport, **limits):
    roots = [Path(p).resolve() for p in (local, bundle)]
    if any(a == b or a in b.parents or b in a.parents for a, b in (roots, roots[::-1])):
        raise ValueError('Use distinct, non-nested history and bundle directories')
    if any(not math.isfinite(v) or v <= 0 for v in limits.values()):
        raise ValueError('Limits must be finite and positive')
    before = inventory(cities, local, bundle, clock)
    if not (seed or download):
        return dict(before, mode='read_only', imported=0)
    if before['status'] == 'unreadable':
        return dict(before, stop_reason='storage_unreadable', imported=0)
    worker = Downloader(Library(ReadOnlyDirectoryStore(local), clock), provider, **limits)
    # Validate limits before creating any local files.
    store = DirectoryStore(local)
    worker.library = Library(store, clock)
    imported = 0
    reason = 'seed_only' if not download else 'complete'
    try:
        with store.exclusive():
            for city in cities:
                for month in MONTHS:
                    if worker.library.read(city, month) is not None:
                        continue
                    state, raw = inspect(bundle, city, month, clock)
                    if state == 'unreadable':
                        raise OSError()
                    if raw is not None:
                        store.put(key(city, month), raw)
                        if worker.library.read(city, month) is None:
                            raise OSError()
                        imported += 1
            if download:
                priority = [(c, m) for c, m in plan(cities, clock().date()) if m in MONTHS]
                seen = {(c['id'], m) for c, m in priority}
                jobs = priority + [(c, m) for m in reversed(MONTHS) for c in cities
                                   if (c['id'], m) not in seen]
                worker.fill_locked(jobs)
    except BackfillPaused:
        now = clock().astimezone(BERLIN)
        ledger = json.loads(store.get(LEDGER) or b'{}')
        cost = Downloader.cost(MONTHS[0])
        reason = ('max_blocks' if worker.stats['published'] >= worker.max_blocks
                  else 'batch_budget' if worker.stats['equivalent_calls'] + cost > worker.batch
                  else 'daily_budget' if ledger.get('days', {}).get(now.date().isoformat(), 0) + cost > worker.daily
                  else 'monthly_budget')
    except (Unavailable, OSError) as exc:
        # Only known internal messages; never serialize provider exception details.
        message = str(exc)
        reason = ('timeout' if '总时限' in message else 'cooldown' if '冷却中' in message
                  else 'invalid_ledger' if '用量记录' in message else 'locked' if '正在维护' in message
                  else 'provider_or_storage_failure')
    after = inventory(cities, local, bundle, clock)
    return dict(after, imported=imported, stop_reason=reason, mode='download' if download else 'seed',
                run=worker.stats, http_requests=worker.stats.get('http_requests', 0),
                new_valid=after['valid']-before['valid'])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('status', 'backfill'))
    parser.add_argument('--history-dir', default='.history-local')
    parser.add_argument('--bundle-dir', default='weather-data')
    parser.add_argument('--seed', action='store_true', help='Local writes only: import valid Git blocks')
    parser.add_argument('--download', action='store_true', help='LIVE ERA5 requests; separate data-operation approval required')
    parser.add_argument('--max-blocks', type=int, default=5)
    parser.add_argument('--batch-calls', type=int, default=30)
    parser.add_argument('--daily-calls', type=int, default=60)
    parser.add_argument('--monthly-calls', type=int, default=600)
    parser.add_argument('--timeout', type=float, default=30)
    args = parser.parse_args(argv)
    if args.command == 'status' and (args.seed or args.download):
        parser.error('status is strictly read-only')
    try:
        _, cities = records_at(args.bundle_dir)
        clock = lambda: datetime.now(BERLIN)
        if args.command == 'status':
            report = inventory(cities, args.history_dir, args.bundle_dir, clock)
        else:
            report = backfill(cities, args.history_dir, args.bundle_dir, clock,
                              seed=args.seed, download=args.download, max_blocks=args.max_blocks,
                              batch=args.batch_calls, daily=args.daily_calls,
                              monthly=args.monthly_calls, timeout=args.timeout)
        print(json.dumps(report, sort_keys=True))
        print(f"{report['valid']}/600 valid; {report['remaining']} remaining; "
              f"{report['equivalent_calls']} estimated weighted units; "
              f"{report.get('stop_reason', report['status'])}", file=sys.stderr)
        return 1 if report['status'] == 'unreadable' or report.get('stop_reason') in (
            'invalid_ledger', 'provider_or_storage_failure', 'cooldown', 'timeout', 'locked') else 0
    except (OSError, ValueError, TypeError, KeyError, Unavailable):
        print(json.dumps(dict(status='metadata_storage_or_limits_unavailable')))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
