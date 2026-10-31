"""One-command manual history data PR: branch, bounded ERA5 backfill, export, push, open PR.

Never merges or deploys. Only `weather-data/history/` may enter the commit; forecasts
stay owned by the forecast data PR automation.
"""
import argparse
from datetime import datetime
import json
import subprocess
import sys

from web import history_commands as hc
from web.data_commands import records_at
from web.fixtures import BERLIN

SCOPE = 'weather-data/history/'
# Stops after which nothing was downloaded and storage/ledger state needs a human.
ABORT = ('storage_unreadable', 'invalid_ledger', 'locked')


class Stop(Exception):
    """Operator-facing precondition or safety failure."""


def sh(*cmd, check=True, strip=True):
    done = subprocess.run(cmd, capture_output=True, text=True)
    if check and done.returncode:
        raise Stop(f"{' '.join(cmd[:3])} failed: {(done.stderr or done.stdout).strip()[-400:]}")
    return done.stdout.strip() if strip else done.stdout


def branch_name(day, exists):
    base = f"data/history-{day.strftime('%Y%m%d')}"
    name, n = base, 1
    while exists(name):
        n += 1
        name = f'{base}-{n}'
    return name


def body(before, exported, backfill):
    lines = [
        'Manual ERA5 history data update (`make history-pr`). Data-only: changes are limited to `weather-data/history/`.',
        '',
        f"- Git coverage: {before}/600 -> {exported['git_valid']}/600 valid city-months",
        f"- Added {exported['added']}, repaired {exported['repaired']} month objects",
    ]
    if backfill:
        run = backfill.get('run', {})
        lines.append(f"- Download stop reason: `{backfill.get('stop_reason')}`; published {run.get('published', 0)}, "
                     f"failed {run.get('failed', 0)}, HTTP requests {run.get('http_requests', 0)}, "
                     f"weighted units {run.get('equivalent_calls', 0)}")
        if run.get('last_error'):
            err = run['last_error']
            lines.append(f"- Last error: {err['type']} during {err['stage']} for {err['job']}, "
                         f"HTTP status {err['http_status']}, cooldown {err['cooldown_seconds']:.0f}s")
    else:
        lines.append('- Download skipped (`--no-download`); only months already in the local store were exported.')
    lines += ['', 'Every object was revalidated (identity, checksum, full-month UTC coverage) before export; '
              'valid Git bytes and forecast files are untouched. Review, then merge manually; '
              'merging to `main` triggers a Production deployment.']
    return '\n'.join(lines)


def run(args, clock=lambda: datetime.now(BERLIN), backfill=hc.backfill, export=hc.export):
    # Preflight everything that can fail before any live download.
    if sh('git', 'status', '--porcelain'):
        raise Stop('Working tree has uncommitted changes; commit or stash them first.')
    sh('gh', 'auth', 'status')
    start = sh('git', 'rev-parse', '--abbrev-ref', 'HEAD')
    sh('git', 'fetch', 'origin', args.base)
    name = branch_name(clock(), lambda n: bool(
        sh('git', 'branch', '--list', n) or sh('git', 'ls-remote', '--heads', 'origin', n)))
    sh('git', 'switch', '-c', name, f'origin/{args.base}')
    pushed = False
    try:
        _, cities = records_at(args.bundle_dir)
        before = hc.inventory(cities, args.history_dir, args.bundle_dir, clock)
        git_before = sum(b['git'] == 'valid' for r in before['cities'] for b in r['months'].values())
        result = None
        if not args.no_download:
            result = backfill(cities, args.history_dir, args.bundle_dir, clock,
                              seed=True, download=True, max_blocks=args.max_blocks,
                              batch=args.batch_calls, daily=args.daily_calls,
                              monthly=args.monthly_calls, timeout=args.timeout)
            print(json.dumps({k: result.get(k) for k in ('stop_reason', 'imported', 'new_valid', 'run')},
                             sort_keys=True), file=sys.stderr)
            if result.get('stop_reason') in ABORT:
                raise Stop(f"Backfill stopped: {result['stop_reason']}; investigate before retrying.")
        exported = export(cities, args.history_dir, args.bundle_dir, clock)
        # -z keeps each entry's leading status columns and avoids path quoting.
        status = sh('git', 'status', '--porcelain', '-z', '--untracked-files=all', strip=False)
        paths = [entry[3:] for entry in status.split('\0') if entry]
        if not paths:
            print(f"Nothing new for Git ({git_before}/600 valid; stop reason: "
                  f"{result.get('stop_reason') if result else 'n/a'}). No branch or PR created.")
            return 0
        outside = [p for p in paths if not p.startswith(SCOPE)]
        if outside:
            raise Stop(f'Unexpected changes outside {SCOPE}: {outside[:5]}')
        day = clock().strftime('%Y-%m-%d')
        title = f"data: update history data {day} ({git_before} -> {exported['git_valid']}/600)"
        sh('git', 'add', '--', SCOPE)
        sh('git', 'commit', '-m', title)
        sh('git', 'push', '-u', 'origin', name)
        pushed = True
        print(sh('gh', 'pr', 'create', '--base', args.base, '--head', name, '--title', title,
                 '--body', body(git_before, exported, result)))
        return 0
    finally:
        # Return to where the operator started; keep the branch only once it is published.
        sh('git', 'checkout', '--', SCOPE, check=False)
        sh('git', 'clean', '-fdq', '--', SCOPE, check=False)
        sh('git', 'switch', start, check=False)
        if not pushed:
            sh('git', 'branch', '-D', name, check=False)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--history-dir', default='.history-local')
    parser.add_argument('--bundle-dir', default='weather-data')
    parser.add_argument('--base', default='main')
    parser.add_argument('--no-download', action='store_true', help='Export months already in the local store; no live IO')
    # Limits only guard against runaway loops: a full 600-block inventory is 3600 units (~1800 real calls,
    # under 20% of Open-Meteo's 10,000/day); monthly allows two. The 900 s timeout may end a run early;
    # each run publishes what it validated, so a full fill may take several runs.
    parser.add_argument('--max-blocks', type=int, default=600)
    parser.add_argument('--batch-calls', type=int, default=3600)
    parser.add_argument('--daily-calls', type=int, default=3600)
    parser.add_argument('--monthly-calls', type=int, default=7200)
    parser.add_argument('--timeout', type=float, default=900)
    try:
        return run(parser.parse_args(argv))
    except Stop as exc:
        print(f'history-pr stopped: {exc}', file=sys.stderr)
        return 1
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(f'history-pr failed: {type(exc).__name__}; local branch restored.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
