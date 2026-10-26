"""Trusted-main forecast data-PR publisher. No merge/deploy/settings operations.

Only this explicit operator entry point performs IO. All subprocess output is
captured; errors never echo provider responses, token-bearing stderr or payloads.
"""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import tempfile
from time import monotonic

from web.data_commands import (forecast_update, forecast_export, forecast_batch,
                               trusted_records, Superseded, tree)
from web.fixtures import BERLIN
from web.live import Unavailable

REPO = 'pengcc/travel-clothing-advisor'
BRANCH = 'codex/weather-forecast-data'
WORKFLOW = 'weather-refresh.yml'
BOT_EMAIL = '41898282+github-actions[bot]@users.noreply.github.com'
MARKER = 'Travel-Forecast-v2: '


def admit(runs, run_id, attempt, now):
    """All runs count, including failed, cancelled and skipped jobs."""
    if attempt != 1:
        raise ValueError('Rerun cannot collect')
    today = now.astimezone(timezone.utc).date()
    parsed = []
    for row in runs:
        created = datetime.fromisoformat(row['created_at'].replace('Z', '+00:00'))
        if created.tzinfo is None or row['event'] not in ('schedule', 'workflow_dispatch'):
            raise ValueError('Unverifiable run history')
        if created.astimezone(timezone.utc).date() == today:
            parsed.append((created, row['id'], row))
    parsed.sort(key=lambda x: (x[0], x[1]))
    rank = next((i for i, (_, ident, _) in enumerate(parsed) if ident == run_id), None)
    if rank is None or rank >= 2:
        raise ValueError('Daily run budget unavailable')
    # A prior failure might have received Retry-After exceeding this slot. Without
    # retained provider headers we cannot prove cooldown elapsed: stop for the day.
    current_position = parsed[rank][:2]
    if any(r['conclusion'] not in ('success', 'skipped') and
           (datetime.fromisoformat(r['created_at'].replace('Z', '+00:00')), r['id']) < current_position
           for r in runs):
        raise ValueError('Prior cooldown cannot be proven elapsed')
    return 'am' if now.astimezone(timezone.utc).hour < 12 else 'pm'


class GitHub:
    def __init__(self, root='.', *, timer=monotonic):
        self.root = Path(root).resolve()
        self.timer, self.deadline = timer, timer() + 270

    def command(self, args, *, data=None, env=None):
        remaining = self.deadline - self.timer()
        if remaining <= 0:
            raise ValueError('Publication deadline exceeded')
        result = subprocess.run(args, cwd=self.root, input=data, capture_output=True,
                                timeout=min(30, remaining), env=env)
        if result.returncode:
            raise ValueError('Git/GitHub operation failed; inspect permissions and state safely')
        return result.stdout

    def git(self, *args, **kwargs):
        if args[0] in ('fetch', 'ls-remote', 'push') and os.environ.get('GH_TOKEN'):
            kwargs['env'] = self.remote_environment()
        return self.command(['git', *args], **kwargs)

    def remote_environment(self):
        # Needed for reads too: checkout intentionally does not persist credentials.
        import base64
        header = 'AUTHORIZATION: basic ' + base64.b64encode(
            ('x-access-token:' + os.environ['GH_TOKEN']).encode()).decode()
        return dict(os.environ, GIT_CONFIG_COUNT='1',
                    GIT_CONFIG_KEY_0='http.https://github.com/.extraheader', GIT_CONFIG_VALUE_0=header)


    def api(self, path, method='GET', payload=None):
        args = ['gh', 'api', '-X', method, path]
        data = None
        if payload is not None:
            args += ['--input', '-']
            data = json.dumps(payload).encode()
        return json.loads(self.command(args, data=data))

    def pages(self, path, field=None):
        rows = []
        total = None
        for page in range(1, 11):
            response = self.api(f'{path}&per_page=100&page={page}')
            part = response[field] if field else response
            if field:
                if total is not None and total != response['total_count']:
                    raise ValueError('Run history changed during pagination')
                total = response['total_count']
            rows.extend(part)
            if len(part) < 100:
                if field and total != len(rows):
                    raise ValueError('Incomplete run history')
                return rows
        raise ValueError('Pagination bound exceeded')

    def runs(self, now):
        # Include earlier failures: Retry-After may extend beyond a UTC midnight.
        return self.pages(f'repos/{REPO}/actions/workflows/{WORKFLOW}/runs?exclude_pull_requests=true', 'workflow_runs')

    def prs(self):
        return self.pages(f'repos/{REPO}/pulls?state=all&head=pengcc:{BRANCH}&base=main')

    def refs(self):
        remote = self.git('ls-remote', 'origin', 'refs/heads/main', f'refs/heads/{BRANCH}').decode()
        refs = dict((ref, sha) for sha, ref in (line.split() for line in remote.splitlines()))
        base, head = refs['refs/heads/main'], refs.get(f'refs/heads/{BRANCH}')
        # A shallow boundary can hide a genuine previous-base ancestor even
        # after fetching the old bot head. Keep the gate, fetch the actual graph.
        if self.git('rev-parse', '--is-shallow-repository').strip() == b'true':
            self.git('fetch', '--unshallow', '--no-tags', 'origin', base)
        for sha in (base, head):
            if sha:
                self.git('fetch', '--no-tags', 'origin', sha)
        return base, head

    def snapshot(self, sha, destination):
        destination.mkdir()
        listing = self.git('ls-tree', '-rz', sha, '--', 'weather-data').split(b'\0')
        for row in filter(None, listing):
            meta, name = row.split(b'\t', 1)
            mode, kind, blob = meta.split()
            if mode != b'100644' or kind != b'blob':
                raise ValueError('Non-regular data object')
            path = destination / os.fsdecode(name).removeprefix('weather-data/')
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(self.git('cat-file', 'blob', blob.decode()))
        return destination

    def metadata(self, head):
        if not head:
            return None
        raw = self.git('show', '-s', '--format=%ae%n%B', head).decode()
        email, message = raw.split('\n', 1)
        if email != BOT_EMAIL or not message.strip().startswith(MARKER):
            raise ValueError('Data branch ownership drift')
        meta = json.loads(message.strip()[len(MARKER):])
        parent = self.git('rev-parse', head + '^').decode().strip()
        if parent != meta['base'] or meta['day'] != datetime.fromisoformat(meta['acquired']).astimezone(BERLIN).date().isoformat():
            raise ValueError('Invalid publication provenance')
        self.allowed(parent, head)
        return meta

    def ancestor(self, previous, base):
        self.git('merge-base', '--is-ancestor', previous, base)

    def allowed(self, base, head):
        names = self.git('diff', '--name-only', '-z', base, head).split(b'\0')
        if any(not n.startswith(b'weather-data/forecast/') for n in names if n):
            raise ValueError('Non-forecast diff')

    def commit(self, base, assembled, original, meta, temporary):
        env = dict(os.environ, GIT_INDEX_FILE=str(temporary / 'index'),
                   GIT_AUTHOR_NAME='github-actions[bot]', GIT_AUTHOR_EMAIL=BOT_EMAIL,
                   GIT_COMMITTER_NAME='github-actions[bot]', GIT_COMMITTER_EMAIL=BOT_EMAIL)
        self.git('read-tree', base, env=env)
        after = tree(assembled)
        for name in original.keys() - after.keys():
            self.git('update-index', '--force-remove', '--', 'weather-data/' + name, env=env)
        for name, raw in after.items():
            if original.get(name) == raw:
                continue
            blob = self.git('hash-object', '-w', '--stdin', data=raw).decode().strip()
            self.git('update-index', '--add', '--cacheinfo', f'100644,{blob},weather-data/{name}', env=env)
        tree_sha = self.git('write-tree', env=env).decode().strip()
        commit = self.git('commit-tree', tree_sha, '-p', base, env=env,
                          data=(MARKER + json.dumps(meta, sort_keys=True) + '\n').encode()).decode().strip()
        self.allowed(base, commit)
        return commit

    def push(self, head, expected):
        self.git('push', f'--force-with-lease=refs/heads/{BRANCH}:{expected or ""}',
                 'origin', f'{head}:refs/heads/{BRANCH}', env=self.remote_environment())

    def publish_pr(self, head, meta, prs):
        body = (f'Refs #79. Forecast-only batch {meta["day"]} / {meta["slot"]}; 10/10 cities.\n\n'
                f'Acquisition UTC: {meta["first"]} through {meta["acquired"]}.\n'
                f'Validated base: `{meta["base"]}`; head: `{head}`. History changes: 0.\n'
                f'Run: https://github.com/{REPO}/actions/runs/{meta["run"]}\n\n'
                'Offline source, city-anchor, freshness and history-byte gates passed at this base/head. '
                'Independent Review and explicit human merge authorization required. Revalidate against '
                'CURRENT exact base/head before merge; an updated base invalidates this evidence. '
                'Merge may automatically trigger Vercel Production; obtain authorization for that effect. '
                'No checks is not passing checks. No bot approval or automatic merge.')
        payload = dict(title=f'Weather forecast {meta["day"]} {meta["slot"]} (10 cities)', body=body)
        opened = [p for p in prs if p['state'] == 'open']
        if opened:
            self.api(f'repos/{REPO}/pulls/{opened[0]["number"]}', 'PATCH', payload)
        else:
            self.api(f'repos/{REPO}/pulls', 'POST', dict(payload, head=BRANCH, base='main'))


def publication_prs(github, expected, initial):
    """Last-observed lifecycle control; Git push and PR API are not atomic."""
    current = github.prs()
    opened = [p for p in current if p['state'] == 'open']
    if len(opened) > 1:
        raise ValueError('Duplicate data PRs')
    if any(p['state'] == 'closed' and not p['merged_at'] for p in current):
        raise ValueError('Data publication manually paused')
    if opened and opened[0]['head']['sha'] != expected:
        raise ValueError('PR head drift')
    def lifecycle(rows):
        # Open PR head changes from our push are expected; all other lifecycle
        # changes (including merge/new PR) require a fresh reconciliation.
        return sorted((p['number'], p['state'], p['merged_at'],
                       p['head']['sha'] if p['state'] != 'open' else '') for p in rows)
    if lifecycle(current) != lifecycle(initial):
        raise ValueError('PR lifecycle changed during publication')
    return current


def reconcile(github, clock, run_id, attempt, *, collect=forecast_update):
    """One collection, bounded offline reassembly; injectable GitHub/clock for regressions."""
    now = clock()
    day = now.astimezone(BERLIN).date()
    prs = github.prs()
    if len([p for p in prs if p['state'] == 'open']) > 1:
        raise ValueError('Duplicate data PRs')
    # Any manual close is a pause until separately reviewed operator recovery.
    if any(p['state'] == 'closed' and not p['merged_at'] for p in prs):
        raise ValueError('Data publication manually paused')
    base, expected = github.refs()
    meta = github.metadata(expected)
    if meta:
        github.ancestor(meta['base'], base)
    slot = 'am' if now.astimezone(timezone.utc).hour < 12 else 'pm'
    opened = [p for p in prs if p['state'] == 'open']
    if opened and opened[0]['head']['sha'] != expected:
        raise ValueError('PR head drift')
    # Recovery after successful push / failed PR API must precede network admission.
    if meta and meta['day'] == day.isoformat() and meta['slot'] == slot:
        with tempfile.TemporaryDirectory(prefix='.forecast-recovery-', dir=github.root) as temp:
            t = Path(temp)
            sources = github.snapshot(expected, t / 'sources')
            latest = github.snapshot(base, t / 'base')
            forecast_export(sources, latest, t / 'assembled', clock, day)
            if meta['base'] != base:
                raise ValueError('Recovery base changed; independent revalidation required')
            if github.refs() != (base, expected):
                raise ValueError('Recovery refs changed')
            latest_prs = publication_prs(github, expected, prs)
            github.publish_pr(expected, meta, latest_prs)
        return 'already-published'
    admit(github.runs(now), run_id, attempt, now)
    with tempfile.TemporaryDirectory(prefix='.forecast-run-', dir=github.root) as temp:
        t = Path(temp)
        initial = github.snapshot(base, t / 'initial')
        trusted_records(initial)
        sources = t / 'sources'
        if clock().astimezone(timezone.utc).date() != now.astimezone(timezone.utc).date():
            raise ValueError('UTC execution day changed before collection')
        collect(initial, sources, clock)
        candidate = forecast_batch(sources, clock, day)
        times = [instant for _, instant in candidate.values()]
        for iteration in range(3):
            latest_base, current_head = github.refs()
            if current_head != expected:
                raise ValueError('Data branch changed; refusing overwrite')
            latest = github.snapshot(latest_base, t / f'base-{iteration}')
            branch = github.snapshot(expected, t / f'branch-{iteration}') if expected else None
            assembled = t / f'assembled-{iteration}'
            forecast_export(sources, latest, assembled, clock, day, branch)
            # Repeat full gates on the last observed exact main, then recheck refs.
            forecast_export(sources, latest, t / f'gate-{iteration}', clock, day, branch)
            if github.refs() != (latest_base, expected):
                continue
            if tree(assembled) == tree(latest):
                return 'unchanged'
            meta = dict(base=latest_base, day=day.isoformat(), slot=slot, run=run_id,
                        first=min(times).isoformat(), acquired=max(times).isoformat())
            head = github.commit(latest_base, assembled, tree(latest), meta, t)
            if github.refs() != (latest_base, expected):
                continue
            # Date/anchor/source/history validation immediately before the push.
            forecast_export(sources, latest, t / f'final-{iteration}', clock, day, branch)
            publication_prs(github, expected, prs)
            github.push(head, expected)
            latest_prs = publication_prs(github, head, prs)
            github.publish_pr(head, meta, latest_prs)
            return 'published'
        raise ValueError('Main repeatedly changed; no publication')


def verify(github, clock, base, head):
    """Read-only pre-merge verification; refuses stale supplied revision evidence."""
    if github.refs() != (base, head):
        raise ValueError('Base/head evidence stale')
    meta = github.metadata(head)
    if not meta or meta['base'] != base:
        raise ValueError('Reassemble/review data PR against current main first')
    github.allowed(base, head)
    with tempfile.TemporaryDirectory(prefix='.forecast-verify-', dir=github.root) as temp:
        t = Path(temp)
        latest = github.snapshot(base, t / 'base')
        sources = github.snapshot(head, t / 'sources')
        forecast_export(sources, latest, t / 'assembled', clock, clock().astimezone(BERLIN).date())
        if tree(t / 'assembled') != tree(sources) or github.refs() != (base, head):
            raise ValueError('PR tree or revision evidence changed')
    return dict(base=base, head=head, cities=10, history_changes=0)


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify', nargs=2, metavar=('EXACT_BASE', 'EXACT_HEAD'),
                        help='Read-only current data-PR check, no collection or publication')
    args = parser.parse_args(argv)
    if args.verify:
        try:
            print(json.dumps(verify(GitHub(), lambda: datetime.now(BERLIN), *args.verify), sort_keys=True))
            return 0
        except (ValueError, OSError, KeyError, TypeError, Unavailable, subprocess.SubprocessError):
            print('Forecast verification stopped: stale revisions or invalid data')
            return 1
    # Defense in depth; the workflow also gates these before granting the job IO.
    env = os.environ
    if not (env.get('TRAVEL_GIT_FORECAST_ENABLED') == 'true' and
            env.get('GITHUB_REPOSITORY') == REPO and env.get('GITHUB_REF') == 'refs/heads/main' and
            env.get('GITHUB_EVENT_NAME') in ('schedule', 'workflow_dispatch')):
        print('Forecast publication disabled or untrusted context')
        return 1
    try:
        result = reconcile(GitHub(), lambda: datetime.now(BERLIN),
                           int(env['GITHUB_RUN_ID']), int(env['GITHUB_RUN_ATTEMPT']))
        print('Forecast publication: ' + result)
        return 0
    except Superseded:
        print('Forecast publication: superseded; no branch or PR writes')
        return 0
    except (ValueError, OSError, KeyError, TypeError, Unavailable, subprocess.SubprocessError):
        print('Forecast publication stopped: validation, budget, cooldown or GitHub state unavailable')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
