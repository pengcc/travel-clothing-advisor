"""Synthetic weather and fake GitHub; no provider/cloud calls or retained data writes."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from test_live import NOW, forecast
from test_history import month_data
from web import data_commands as data
from web import git_forecast_refresh as refresh
from web.forecasts import Cache, key, pack, unpack
from web.history import DirectoryStore, Library, key as hkey
from web.fixtures import BERLIN
from web.live import FORECAST, Unavailable

MANIFEST = (Path(__file__).resolve().parents[2] / 'weather-data/cities.json').read_bytes()


class FakeGitHub:
    def __init__(self, root, main, now):
        self.root, self.main, self.now = root, main, now
        self.head = None
        self.meta = None
        self.branch = None
        self.pr_list = []
        self.writes = []
        self.reads = 0
        self.hook = lambda n: None
        self.run_rows = [dict(id=1, created_at=now.astimezone(timezone.utc).isoformat(),
                              event='schedule', conclusion=None)]
        self.fail_api = False
        self.commits = 0

    def prs(self):
        return deepcopy(self.pr_list)

    def refs(self):
        self.reads += 1
        self.hook(self.reads)
        return self.main.name, self.head

    def allowed(self, base, head):
        pass

    def ancestor(self, previous, base):
        pass

    def metadata(self, head):
        return self.meta

    def snapshot(self, sha, destination):
        source = self.branch if sha == self.head else self.root / sha
        shutil.copytree(source, destination)
        return destination

    def runs(self, now):
        return self.run_rows

    def commit(self, base, assembled, original, meta, temporary):
        self.pending_meta = meta
        self.commits += 1
        self.pending = self.root / f'pending-{self.commits}'
        shutil.copytree(assembled, self.pending)
        self.writes.append('commit')
        return self.pending.name

    def push(self, head, expected):
        if self.head != expected:
            raise ValueError('lease')
        self.head, self.meta = head, self.pending_meta
        self.branch = self.pending
        self.writes.append('push')
        for pr in self.pr_list:
            if pr['state'] == 'open':
                pr['head']['sha'] = head

    def publish_pr(self, head, meta, prs):
        if self.fail_api:
            raise ValueError('API failure')
        self.writes.append('pr')
        self.pr_list = [dict(number=1, state='open', head=dict(sha=head), merged_at=None)]


class RefreshTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.base = self.root / 'main-1'
        self.base.mkdir()
        (self.base / 'cities.json').write_bytes(MANIFEST)
        (self.base / 'README.md').write_bytes(b'Attribution retained\n')
        self.records, self.cities = data.trusted_records(self.base)
        self.now = NOW
        self.clock = lambda: self.now
        self.calls = []
        self.gh = FakeGitHub(self.root, self.base, self.now)
        self.collects = 0

    def provider(self, url, params, timeout):
        self.assertEqual(url, FORECAST)
        self.assertEqual(params['forecast_days'], 14)
        self.assertEqual(params['hourly'], 'temperature_2m')
        self.assertLessEqual(timeout, 4)
        self.calls.append(params)
        return forecast(self.now)

    def collect(self, bundle, output, clock):
        self.collects += 1
        return data.forecast_update(bundle, output, clock, self.provider)

    def prepare(self, root, instant):
        Cache(DirectoryStore(root), lambda: instant).prefetch(self.records,
                                                          lambda *a: forecast(instant))
        # Automation trees contain no cache ledger / legacy manifest.
        (root / 'forecast/control/admission-v1.json').unlink()
        (root / 'forecast/featured-v1' / (instant.date().isoformat()+'.json')).unlink()
        (root / '.worker.lock').unlink()

    def history(self, root, month='2010-01'):
        Library(DirectoryStore(root), self.clock).publish(self.cities[0], month, month_data(month))
        return root / hkey(self.cities[0], month)

    def newer_main(self, *, newer=False, drift=False):
        latest = self.root / 'main-2'
        shutil.copytree(self.base, latest)
        extra = self.history(latest)
        if newer:
            self.prepare(latest, self.now)
        if drift:
            records = json.loads(MANIFEST)
            records[0]['latitude'] = records[1]['latitude']
            (latest / 'cities.json').write_text(json.dumps(records))
        self.gh.main = latest
        return extra

    def run_refresh(self, attempt=1, run_id=1):
        return refresh.reconcile(self.gh, self.clock, run_id, attempt, collect=self.collect)

    def test_same_day_two_slots_really_acquire_and_same_slot_is_zero_io(self):
        self.assertEqual(self.run_refresh(), 'published')
        first = data.forecast_batch(self.gh.branch, self.clock, self.now.date())
        self.assertEqual(len(self.calls), 10)
        self.assertEqual(self.run_refresh(), 'already-published')
        self.assertEqual(len(self.calls), 10)
        self.now += timedelta(hours=8)
        self.gh.run_rows[0]['conclusion'] = 'success'
        self.gh.run_rows.append(dict(id=2, created_at=self.now.astimezone(timezone.utc).isoformat(),
                                     event='workflow_dispatch', conclusion=None))
        self.assertEqual(self.run_refresh(run_id=2), 'published')
        second = data.forecast_batch(self.gh.branch, self.clock, self.now.date())
        self.assertTrue(all(second[n][1] > first[n][1] for n in first))
        self.assertEqual((len(self.calls), len(self.gh.pr_list)), (20, 1))

    def test_p1_newer_main_plus_new_history_and_final_gate_race(self):
        for change_at in (2, 3, 4):
            with self.subTest(change_at=change_at):
                if (self.root / 'main-2').exists():
                    shutil.rmtree(self.root / 'main-2')
                self.gh = FakeGitHub(self.root, self.base, NOW)
                self.now, self.calls = NOW, []
                original = data.tree(self.base)
                def change(n):
                    if n == change_at:
                        self.now += timedelta(minutes=1)
                        self.extra = self.newer_main(newer=True)
                        self.latest_bytes = data.tree(self.gh.main)
                self.gh.hook = change
                with self.assertRaises(data.Superseded):
                    self.run_refresh()
                self.assertEqual(len(self.calls), 10)
                self.assertNotIn('push', self.gh.writes)
                self.assertNotIn('pr', self.gh.writes)
                self.assertEqual(data.tree(self.base), original)
                self.assertEqual(data.tree(self.gh.main), self.latest_bytes)
                self.assertEqual(hashlib.sha256(self.extra.read_bytes()).hexdigest(),
                                 data.history_hashes(self.gh.main, self.clock)[str(self.extra.relative_to(self.gh.main))])

    def test_p1_only_history_main_change_reassembles_without_second_io(self):
        def change(n):
            if n == 2:
                self.extra = self.newer_main()
        self.gh.hook = change
        self.assertEqual(self.run_refresh(), 'published')
        self.assertEqual(len(self.calls), 10)
        self.assertEqual(data.history_hashes(self.gh.main, self.clock),
                         data.history_hashes(self.gh.branch, self.clock))
        self.assertEqual(self.gh.meta['base'], 'main-2')

    def test_p1_equal_instant_raw_conflict_and_branch_newer(self):
        sources = self.root / 'sources'
        self.collect(self.base, sources, self.clock)
        batch = data.forecast_batch(sources, self.clock, self.now.date())
        data.no_regression(batch, batch)  # exactly equal is safe
        candidate = {n: (raw, t.astimezone(timezone(timedelta(hours=-5)))) for n, (raw, t) in batch.items()}
        data.no_regression(candidate, batch)  # compare instants, not strings
        with self.assertRaises(ValueError):
            data.no_regression(batch, {n: (b'other', t) for n, (_, t) in batch.items()})
        self.now += timedelta(minutes=1)
        branch = self.root / 'branch'
        shutil.copytree(self.base, branch)
        self.prepare(branch, self.now)
        with self.assertRaises(data.Superseded):
            data.forecast_export(sources, self.base, self.root/'out', self.clock, self.now.date(), branch)
        self.assertEqual(len(self.calls), 10)

    def test_p2_complete_anchor_before_io_and_after_download(self):
        for field, value in dict(latitude=48.1374, longitude=11.5755, name='Munich', admin1='Bavaria',
                                 feature_code='PPL', country_code='AT', timezone='UTC', population=1).items():
            with self.subTest(field=field):
                rows = json.loads(MANIFEST)
                rows[0][field] = value
                (self.base / 'cities.json').write_text(json.dumps(rows))
                with self.assertRaises(ValueError):
                    self.run_refresh()
                self.assertEqual(self.calls, [])
        (self.base / 'cities.json').write_bytes(MANIFEST+b'\n')
        with self.assertRaises(ValueError):
            self.run_refresh()
        (self.base / 'cities.json').write_bytes(MANIFEST)
        self.gh = FakeGitHub(self.root, self.base, self.now)
        self.gh.hook = lambda n: self.newer_main(drift=True) if n == 2 else None
        with self.assertRaises(ValueError):
            self.run_refresh()
        self.assertEqual(len(self.calls), 10)
        self.assertEqual(self.gh.writes, [])

    def test_source_corruption_missing_city_identity_future_and_hours(self):
        sources = self.root / 'sources'
        self.collect(self.base, sources, self.clock)
        name = key(self.cities[0], self.now.date())
        path = sources / name
        original = path.read_bytes()
        for kind in ('missing', 'checksum', 'identity', 'future', 'yesterday', 'source', 'unit',
                     'timezone', 'null', 'nan', 'infinite', 'gap', 'duplicate', 'reverse', 'schema'):
            with self.subTest(kind=kind):
                body = unpack(original)
                if kind == 'identity': body['identity']['coordinates'][0] += 1
                if kind == 'future': body['weather_fetched_at'] = (self.now+timedelta(seconds=1)).isoformat()
                if kind == 'yesterday': body['weather_fetched_at'] = (self.now-timedelta(days=1)).isoformat()
                if kind == 'source': body['source'] = 'wrong'
                if kind == 'schema': body['identity']['schema'] = 2
                if kind == 'unit': body['response']['hourly_units']['temperature_2m'] = 'F'
                if kind == 'timezone': body['response']['timezone'] = 'UTC'
                hours = body['response']['hourly']
                if kind in ('null', 'nan', 'infinite'):
                    hours['temperature_2m'][0] = dict(null=None, nan=float('nan'), infinite=float('inf'))[kind]
                if kind in ('gap', 'duplicate', 'reverse'):
                    hours['time'][10] += dict(gap=3600, duplicate=-3600, reverse=-7200)[kind]
                if kind == 'checksum': raw = original.replace(b'"sha256":"', b'"sha256":"bad')
                elif kind in ('nan', 'infinite'):
                    from web.history import digest
                    # Invalid JSON number fails checksum/canonical encoding before acceptance.
                    raw = json.dumps(dict(body=body, sha256='invalid')).encode()
                else: raw = pack(body)
                if kind == 'missing': path.unlink()
                else: path.write_bytes(raw)
                before = data.tree(self.base)
                with self.assertRaises((ValueError, Unavailable)):
                    data.forecast_export(sources, self.base, self.root / 'out', self.clock, self.now.date())
                self.assertEqual(data.tree(self.base), before)
                self.assertFalse((self.root/'out').exists())
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(original)

    def test_history_all_bytes_unknown_objects_corruption_and_no_partial_output(self):
        extra = self.history(self.base)
        unknown = self.base / 'history/future-v99/opaque.bin'
        unknown.parent.mkdir(parents=True)
        unknown.write_bytes(b'future bytes retained\x00')
        (self.base / 'other.txt').write_bytes(b'other tracked metadata')
        before = data.tree(self.base)
        self.assertEqual(self.run_refresh(), 'published')
        for name, raw in before.items():
            self.assertEqual((self.gh.branch / name).read_bytes(), raw)
        self.assertEqual(data.history_hashes(self.base, self.clock), data.history_hashes(self.gh.branch, self.clock))
        extra.write_bytes(b'bad gzip')
        self.gh.meta = None
        self.gh.writes.clear()
        calls = len(self.calls)
        with self.assertRaises((ValueError, OSError)):
            self.run_refresh()
        self.assertEqual(len(self.calls), calls)
        self.assertEqual(self.gh.writes, [])

    def test_dst_cross_midnight_and_failure_no_retry(self):
        for now in (datetime(2026,3,28,10,tzinfo=BERLIN), datetime(2026,10,24,10,tzinfo=BERLIN)):
            self.now = now
            output = self.root / now.date().isoformat()
            self.collect(self.base, output, self.clock)
            self.assertEqual(len(data.forecast_batch(output, self.clock, now.date())), 10)
        self.calls = []
        def midnight(url, params, timeout):
            result = self.provider(url, params, timeout)
            self.now += timedelta(days=1)
            return result
        with self.assertRaises(Unavailable):
            data.forecast_update(self.base, self.root/'midnight', self.clock, midnight)
        self.assertEqual(len(self.calls), 1)
        for code in (429, 500):
            calls = []
            def failed(*args):
                calls.append(1)
                from urllib.error import HTTPError
                raise HTTPError(FORECAST, code, 'sensitive response', {}, None)
            with self.assertRaises(Unavailable):
                data.forecast_update(self.base, self.root / str(code), self.clock, failed)
            self.assertEqual(calls, [1])
            self.assertFalse((self.root / str(code)).exists())

    def test_rerun_third_run_failed_slot_cross_day_and_unreadable_budget_zero_io(self):
        with self.assertRaises(ValueError): self.run_refresh(attempt=2)
        self.gh.run_rows = [dict(id=n, created_at=NOW.isoformat(), event='workflow_dispatch',
                                 conclusion='failure') for n in (1,2,3)]
        with self.assertRaises(ValueError): self.run_refresh(run_id=3)
        with self.assertRaises(ValueError): self.run_refresh(run_id=2)
        self.now += timedelta(days=1)
        with self.assertRaises(ValueError): self.run_refresh()
        self.gh.runs = lambda now: (_ for _ in ()).throw(ValueError('unreadable'))
        with self.assertRaises(ValueError): self.run_refresh()
        self.assertEqual(self.calls, [])
        self.assertEqual(self.gh.writes, [])

    def test_push_then_pr_failure_recovers_without_collection_and_manual_close_pauses(self):
        self.gh.fail_api = True
        with self.assertRaises(ValueError): self.run_refresh()
        self.assertEqual(self.gh.writes, ['commit', 'push'])
        self.gh.fail_api = False
        self.assertEqual(self.run_refresh(attempt=2), 'already-published')
        self.assertEqual(len(self.calls), 10)
        self.gh.pr_list[0].update(state='closed', merged_at=None)
        with self.assertRaises(ValueError): self.run_refresh()
        self.assertEqual(len(self.calls), 10)

    def second_slot(self):
        self.now += timedelta(hours=8)
        self.gh.run_rows[0]['conclusion'] = 'success'
        self.gh.run_rows.append(dict(id=2, created_at=self.now.astimezone(timezone.utc).isoformat(),
                                     event='schedule', conclusion=None))

    def test_manual_close_during_collection_stops_before_branch_push(self):
        self.assertEqual(self.run_refresh(), 'published')
        self.second_slot()
        old_head, old_tree = self.gh.head, data.tree(self.gh.branch)
        self.gh.writes.clear()
        self.gh.reads = 0
        def close(n):
            if n == 2:  # First refs read after acquisition; no ref change.
                self.gh.pr_list[0].update(state='closed', merged_at=None)
        self.gh.hook = close
        with self.assertRaisesRegex(ValueError, 'manually paused'):
            self.run_refresh(run_id=2)
        self.assertNotIn('push', self.gh.writes)
        self.assertNotIn('pr', self.gh.writes)
        self.assertEqual(self.gh.head, old_head)
        self.assertEqual(data.tree(self.gh.branch), old_tree)
        self.assertEqual(len(self.calls), 20)  # One acquisition, no retry.

    def test_close_after_push_blocks_pr_mutation_and_recovery_without_more_io(self):
        self.assertEqual(self.run_refresh(), 'published')
        self.second_slot()
        self.gh.writes.clear()
        push = self.gh.push
        def close_after_push(head, expected):
            push(head, expected)
            self.gh.pr_list[0].update(state='closed', merged_at=None)
        self.gh.push = close_after_push
        with self.assertRaisesRegex(ValueError, 'manually paused'):
            self.run_refresh(run_id=2)
        self.assertEqual(self.gh.writes, ['commit', 'push'])
        with self.assertRaisesRegex(ValueError, 'manually paused'):
            self.run_refresh(run_id=2, attempt=2)
        self.assertEqual(len(self.calls), 20)
        self.assertNotIn('pr', self.gh.writes)

    def test_api_failure_recovery_rechecks_close_before_pr_mutation(self):
        self.assertEqual(self.run_refresh(), 'published')
        self.second_slot()
        self.gh.fail_api = True
        with self.assertRaises(ValueError):
            self.run_refresh(run_id=2)
        self.gh.fail_api = False
        writes, calls = list(self.gh.writes), len(self.calls)
        prs = self.gh.prs
        reads = 0
        def close_on_recovery_gate():
            nonlocal reads
            reads += 1
            if reads == 2:  # Initial recovery check was open; close at final API gate.
                self.gh.pr_list[0].update(state='closed', merged_at=None)
            return prs()
        self.gh.prs = close_on_recovery_gate
        with self.assertRaisesRegex(ValueError, 'manually paused'):
            self.run_refresh(run_id=2, attempt=2)
        self.assertEqual((self.gh.writes, len(self.calls)), (writes, calls))

    def test_lifecycle_or_head_change_during_collection_stops_publication(self):
        self.assertEqual(self.run_refresh(), 'published')
        self.second_slot()
        original = deepcopy(self.gh.pr_list)
        for change in ('merge', 'head', 'replace'):
            with self.subTest(change=change):
                self.gh.pr_list = deepcopy(original)
                before = list(self.gh.writes)
                reads = 0
                def changed_prs():
                    nonlocal reads
                    reads += 1
                    rows = deepcopy(original)
                    if reads >= 2:
                        if change == 'merge': rows[0].update(state='closed', merged_at=NOW.isoformat())
                        if change == 'head': rows[0]['head']['sha'] = 'unexpected-head'
                        if change == 'replace': rows[0]['number'] = 999
                    return rows
                self.gh.prs = changed_prs
                with self.assertRaises(ValueError):
                    self.run_refresh(run_id=2)
                self.assertNotIn('push', self.gh.writes[len(before):])
                self.assertNotIn('pr', self.gh.writes[len(before):])

    def test_real_shallow_clone_next_slot_builds_on_advanced_or_merged_main(self):
        for merged in (False, True):
            with self.subTest(merged=merged), tempfile.TemporaryDirectory(dir=self.root) as temp:
                folder = Path(temp)
                source, runner = folder/'origin', folder/'runner'
                source.mkdir()
                shutil.copytree(self.base, source/'weather-data')
                def git(root, *args):
                    return subprocess.check_output(['git', '-C', str(root), *args],
                                                   stderr=subprocess.DEVNULL).decode().strip()
                git(source, 'init', '-b', 'main')
                git(source, 'config', 'user.name', 'Offline Test')
                git(source, 'config', 'user.email', 'test@example.invalid')
                git(source, 'add', '.')
                git(source, 'commit', '-m', 'base A')
                a = git(source, 'rev-parse', 'HEAD')
                sources = folder/'sources'
                self.now = NOW
                self.collect(source/'weather-data', sources, self.clock)
                assembled = folder/'assembled'
                data.forecast_export(sources, source/'weather-data', assembled, self.clock, NOW.date())
                prior = refresh.GitHub(source)
                meta = dict(base=a, day=NOW.date().isoformat(), slot='am', run=1,
                            first=NOW.isoformat(), acquired=NOW.isoformat())
                c = prior.commit(a, assembled, data.tree(source/'weather-data'), meta, folder)
                git(source, 'branch', refresh.BRANCH, c)
                added = self.history(source/'weather-data')
                retained = added.read_bytes()
                git(source, 'add', 'weather-data')
                git(source, 'commit', '-m', 'main B with additional history')
                if merged:
                    git(source, 'merge', '--no-ff', refresh.BRANCH, '-m', 'human merge')
                b = git(source, 'rev-parse', 'HEAD')
                subprocess.check_output(['git', 'clone', '--depth=1', '--branch=main',
                                         source.as_uri(), str(runner)], stderr=subprocess.DEVNULL)
                self.assertEqual(git(runner, 'rev-parse', '--is-shallow-repository'), 'true')
                gh = refresh.GitHub(runner)
                self.now = NOW + timedelta(hours=8)
                gh.runs = lambda now: [dict(id=2, created_at=self.now.isoformat(),
                                           event='schedule', conclusion=None)]
                rows = [dict(number=1, state='closed' if merged else 'open',
                             merged_at=NOW.isoformat() if merged else None, head=dict(sha=c))]
                gh.prs = lambda: deepcopy(rows)
                writes = []
                def api(path, method='GET', payload=None):
                    writes.append((method, payload))
                    return dict(number=2)
                gh.api = api
                push = gh.push
                def push_and_sync(head, expected):
                    push(head, expected)
                    if not merged: rows[0]['head']['sha'] = head
                gh.push = push_and_sync
                with patch.dict('os.environ', GH_TOKEN='synthetic-noncredential'):
                    self.assertEqual(refresh.reconcile(gh, self.clock, 2, 1, collect=self.collect), 'published')
                new_head = git(source, 'rev-parse', refresh.BRANCH)
                self.assertEqual(git(runner, 'rev-parse', '--is-shallow-repository'), 'false')
                gh.ancestor(a, b)  # Real check retained; no fake ancestry bypass.
                self.assertEqual(git(runner, 'rev-parse', new_head+'^'), b)
                self.assertEqual(gh.metadata(new_head)['base'], b)
                self.assertEqual(git(source, 'rev-parse', 'main'), b)
                output = gh.snapshot(new_head, folder/'published')
                self.assertEqual((output/added.relative_to(source/'weather-data')).read_bytes(), retained)
                self.assertEqual(len(data.forecast_batch(output, self.clock, self.now.date())), 10)
                self.assertEqual(writes[0][0], 'POST' if merged else 'PATCH')
                # Unrelated ancestry still fails closed.
                unrelated_tree = git(source, 'rev-parse', 'main^{tree}')
                orphan = subprocess.check_output(['git', '-C', str(source), 'commit-tree', unrelated_tree],
                                                 input=b'unrelated\n', stderr=subprocess.DEVNULL).decode().strip()
                git(runner, 'fetch', 'origin', orphan)
                with self.assertRaises(ValueError): gh.ancestor(orphan, b)

    def test_verify_exact_refs_readonly_and_stale_evidence_rejected(self):
        self.assertEqual(self.run_refresh(), 'published')
        before = list(self.gh.writes)
        result = refresh.verify(self.gh, self.clock, self.gh.main.name, self.gh.head)
        self.assertEqual(result['cities'], 10)
        self.assertEqual(self.gh.writes, before)
        with self.assertRaises(ValueError):
            refresh.verify(self.gh, self.clock, 'old-base', self.gh.head)
        self.assertEqual(len(self.calls), 10)

    def test_merged_pr_next_slot_starts_latest_main_and_still_one_pr(self):
        self.assertEqual(self.run_refresh(), 'published')
        merged = self.root / 'merged-main'
        shutil.copytree(self.gh.branch, merged)
        self.gh.main = merged
        self.gh.pr_list[0].update(state='closed', merged_at=NOW.isoformat())
        self.now += timedelta(hours=8)
        self.gh.run_rows[0]['conclusion'] = 'success'
        self.gh.run_rows.append(dict(id=2, created_at=self.now.astimezone(timezone.utc).isoformat(),
                                     event='schedule', conclusion=None))
        self.assertEqual(self.run_refresh(run_id=2), 'published')
        self.assertEqual(self.gh.meta['base'], 'merged-main')
        self.assertEqual((len(self.calls), len(self.gh.pr_list)), (20, 1))

    def test_branch_drift_stops_without_write_and_merge_gate_rejects_old_base(self):
        self.gh.hook = lambda n: setattr(self.gh, 'head', 'human-head') if n == 2 else None
        with self.assertRaises(ValueError): self.run_refresh()
        self.assertEqual((len(self.calls), self.gh.writes), (10, []))
        self.gh = FakeGitHub(self.root, self.base, self.now)
        self.assertEqual(self.run_refresh(), 'published')
        reviewed = self.gh.meta['base']
        self.now += timedelta(minutes=1)
        self.newer_main(newer=True)
        self.assertNotEqual(reviewed, self.gh.main.name)
        with self.assertRaises(data.Superseded):
            data.forecast_export(self.gh.branch, self.gh.main, self.root/'merge-check',
                                 self.clock, self.now.date())



class MergeGitHub(FakeGitHub):
    """Adds the #84 PR/check/merge surface; records every write."""
    def __init__(self, *args):
        super().__init__(*args)
        self.required, self.results = set(), {}
        self.merges, self.closed, self.comments = [], [], []
        self.pull_hook = lambda n: None
        self.pulls = 0
        self.overrides = {}

    def pull(self, number):
        self.pulls += 1
        self.pull_hook(self.pulls)
        pr = next(p for p in self.pr_list if p['number'] == int(number))
        row = dict(number=pr['number'], state=pr['state'], draft=False, merged=bool(pr['merged_at']),
                   merge_commit_sha='merge-sha' if pr['merged_at'] else None,
                   user=dict(login='github-actions[bot]'),
                   head=dict(ref=refresh.BRANCH, sha=pr['head']['sha'], repo=dict(full_name=refresh.REPO)),
                   base=dict(ref='main', repo=dict(full_name=refresh.REPO)))
        for key, value in self.overrides.items():
            row[key] = value(row) if callable(value) else value
        return row

    def required_checks(self):
        if self.required is None:
            raise ValueError('rules unreadable')
        return set(self.required)

    def check_results(self, head):
        return deepcopy(self.results)

    def merge(self, number, head):
        self.merges.append((int(number), head))
        if self.fail_api:
            raise ValueError('merge API failure')
        self.pr_list[0].update(state='closed', merged_at=NOW.isoformat())

    def confirm(self, number, base, head):
        self.writes.append('confirmed')

    def close(self, number):
        self.closed.append(int(number))
        self.pr_list[0]['state'] = 'closed'

    def comment(self, number, body):
        self.comments.append(body)


SCHEDULE = dict(GITHUB_EVENT_NAME='schedule', GITHUB_RUN_ATTEMPT='1',
                TRAVEL_FORECAST_AUTO_MERGE_ENABLED='true', GITHUB_REPOSITORY=refresh.REPO,
                GITHUB_REF='refs/heads/main')


class AutoMergeTests(unittest.TestCase):
    # Reuse the fixtures without re-running every inherited RefreshTests case.
    provider, collect, prepare, history, newer_main, run_refresh = (
        RefreshTests.provider, RefreshTests.collect, RefreshTests.prepare,
        RefreshTests.history, RefreshTests.newer_main, RefreshTests.run_refresh)

    def setUp(self):
        RefreshTests.setUp(self)
        self.gh = MergeGitHub(self.root, self.base, self.now)
        self.assertEqual(self.run_refresh(), 'published')
        self.found = refresh.candidate(self.gh, 1)
        self.args = (self.found['pr'], self.found['base'], self.found['head'])

    def merge(self, env=SCHEDULE):
        return refresh.auto_merge(self.gh, self.clock, env, *self.args)

    def refused(self, env=SCHEDULE):
        with self.assertRaises(ValueError):
            self.merge(env)
        self.assertEqual(self.gh.merges, [])

    def test_candidate_only_for_this_runs_first_attempt_publication(self):
        self.assertEqual(self.found, dict(pr=1, base=self.gh.main.name, head=self.gh.head))
        self.assertIsNone(refresh.candidate(self.gh, 2))
        self.assertEqual(self.run_refresh(), 'already-published')
        self.assertIsNone(refresh.candidate(self.gh, 1))
        # Unconfirmed identity emits no candidate instead of failing the run (F2).
        published = self.gh.published = (self.gh.main.name, self.gh.head)
        for name, apply in dict(head=lambda: setattr(self.gh, 'published', (published[0], 'other-head')),
                                main=lambda: setattr(self.gh, 'main', self.newer_main()),
                                duplicate=lambda: self.gh.pr_list.append(
                                    dict(number=2, state='open', head=dict(sha='x'), merged_at=None)),
                                unreadable=lambda: setattr(self.gh, 'prs', lambda: {}['missing'])).items():
            with self.subTest(name):
                self.setUp()
                self.gh.published = published
                apply()
                self.assertIsNone(refresh.candidate(self.gh, 1))

    def test_unconfirmed_candidate_keeps_published_run_successful(self):
        self.setUp()
        output = self.root / 'github-output'
        env = dict(SCHEDULE, TRAVEL_GIT_FORECAST_ENABLED='true', GITHUB_RUN_ID='1',
                   GITHUB_OUTPUT=str(output))
        def moved(gh, clock, run_id, attempt):
            gh.published = (self.gh.main.name, self.gh.head)
            self.gh.main = self.newer_main()
            return 'published'
        with patch.object(refresh, 'GitHub', lambda: self.gh), patch.object(refresh, 'reconcile', moved), \
                patch.dict('os.environ', env, clear=True):
            self.assertEqual(refresh.main([]), 0)
        self.assertFalse(output.exists())

    def test_schedule_merges_exact_head_once_then_confirms(self):
        self.assertTrue(self.merge()['merged'])
        self.assertEqual(self.gh.merges, [(1, self.gh.head)])
        self.assertEqual(self.gh.writes[-1], 'confirmed')
        self.assertEqual(len(self.calls), 10)

    def test_dispatch_switch_off_reruns_and_forged_arguments_never_merge(self):
        for change in (dict(GITHUB_EVENT_NAME='workflow_dispatch'),
                       dict(TRAVEL_FORECAST_AUTO_MERGE_ENABLED='false'),
                       dict(TRAVEL_FORECAST_AUTO_MERGE_ENABLED=''),
                       dict(GITHUB_RUN_ATTEMPT='2'),
                       dict(GITHUB_REF='refs/heads/other')):
            with self.subTest(change=change):
                self.refused(dict(SCHEDULE, **change))
        # Step A alone (dispatch, switch off) diagnoses but has no merge path.
        self.assertEqual(refresh.verify_candidate(self.gh, self.clock, *self.args)['pr'], 1)
        # CLI arguments cannot override the runner environment.
        env = dict(SCHEDULE, GITHUB_EVENT_NAME='workflow_dispatch')
        with patch.object(refresh, 'GitHub', lambda: self.gh), patch.dict('os.environ', env, clear=True):
            argv = ['--auto-merge', *map(str, self.args)]
            self.assertEqual(refresh.main(argv + ['--auto-merge-verify', *map(str, self.args)]), 1)
            self.assertEqual(refresh.main(argv), 1)
        self.assertEqual(self.gh.merges, [])

    def test_identity_path_data_and_check_gates_refuse(self):
        cases = dict(author=lambda: self.gh.overrides.update(user=dict(login='someone')),
                     branch=lambda: self.gh.overrides.update(head=lambda r: dict(r['head'], ref='other')),
                     base=lambda: self.gh.overrides.update(base=lambda r: dict(r['base'], ref='dev')),
                     fork=lambda: self.gh.overrides.update(head=lambda r: dict(r['head'], repo=None)),
                     draft=lambda: self.gh.overrides.update(draft=True),
                     duplicate=lambda: self.gh.pr_list.append(dict(number=2, state='open', head=dict(sha='x'), merged_at=None)),
                     paused=lambda: self.gh.pr_list.append(dict(number=0, state='closed', head=dict(sha='x'), merged_at=None)),
                     path=lambda: setattr(self.gh, 'allowed', lambda b, h: (_ for _ in ()).throw(ValueError('path'))),
                     stale_base=lambda: setattr(self.gh, 'main', self.newer_main()),
                     check_missing=lambda: setattr(self.gh, 'required', {'ci'}),
                     check_pending=lambda: (setattr(self.gh, 'required', {'ci'}), self.gh.results.update(ci=[False])),
                     check_mixed=lambda: (setattr(self.gh, 'required', {'ci'}), self.gh.results.update(ci=[True, False])),
                     rules_unreadable=lambda: setattr(self.gh, 'required', None))
        for name, apply in cases.items():
            with self.subTest(name):
                self.setUp()
                apply()
                self.refused()
        self.setUp()
        self.gh.required, self.gh.results = {'ci'}, dict(ci=[True])
        self.assertTrue(self.merge()['merged'])

    def test_close_or_head_change_after_verification_prevents_merge(self):
        def closed(n):
            if n == 2: self.gh.pr_list[0]['state'] = 'closed'
        def moved(n):
            if n == 2: self.gh.pr_list[0]['head']['sha'] = 'new-head'
        for hook in (closed, moved):
            with self.subTest(hook.__name__):
                self.setUp()
                self.gh.pull_hook = hook
                self.refused()

    def test_merge_api_failure_is_not_retried(self):
        self.gh.fail_api = True
        with self.assertRaises(ValueError):
            self.merge()
        self.assertEqual(len(self.gh.merges), 1)

    def test_failure_close_pauses_next_round_and_merged_pr_cannot_close(self):
        refresh.close_candidate(self.gh, 1, 'note')
        self.assertEqual((self.gh.closed, self.gh.comments), ([1], ['note']))
        self.now += timedelta(hours=8)
        with self.assertRaisesRegex(ValueError, 'paused'):
            self.run_refresh(run_id=2)
        self.setUp()
        self.merge()
        with self.assertRaises(ValueError):
            refresh.close_candidate(self.gh, 1, 'note')
        self.assertEqual(self.gh.closed, [])
        self.setUp()
        self.gh.overrides.update(head=lambda r: dict(r['head'], ref='feature'))
        with self.assertRaises(ValueError):
            refresh.close_candidate(self.gh, 1, 'note')
        self.assertEqual(self.gh.closed, [])


class GitProtocolTests(unittest.TestCase):
    def test_required_checks_from_token_readable_protection_and_rulesets(self):
        gh = refresh.GitHub()
        def responses(branch, rules):
            def api(path):
                if path == f'repos/{refresh.REPO}/branches/main':
                    return branch
                self.assertTrue(path.startswith(f'repos/{refresh.REPO}/rules/branches/main?'))
                return rules
            return api
        gh.api = responses(dict(protected=False, protection=dict(enabled=False)), [])
        self.assertEqual(gh.required_checks(), set())
        gh.api = responses(
            dict(protected=True, protection=dict(required_status_checks=dict(
                contexts=['legacy'], checks=[dict(context='app-check', app_id=1)]))),
            [dict(type='deletion'), dict(type='required_status_checks', parameters=dict(
                required_status_checks=[dict(context='ruleset-check')]))])
        self.assertEqual(gh.required_checks(), {'legacy', 'app-check', 'ruleset-check'})
        gh.api = responses(dict(protected=True, protection=dict()), [dict(type='required_status_checks')])
        with self.assertRaises(KeyError): gh.required_checks()

    def test_check_results_treat_non_success_and_incomplete_as_failing(self):
        gh = refresh.GitHub()
        runs = [dict(name='ok', status='completed', conclusion='success'),
                dict(name='skip', status='completed', conclusion='skipped'),
                dict(name='wait', status='in_progress', conclusion=None)]
        statuses = [dict(context='ci', state='success'), dict(context='ci', state='pending'),
                    dict(context='lint', state='failure')]
        def api(path, total=len(statuses)):
            if '/check-runs?' in path:
                return dict(total_count=len(runs), check_runs=runs)
            return dict(total_count=total, statuses=statuses)
        gh.api = api
        self.assertEqual(gh.check_results('h'), dict(ok=[True], skip=[False], wait=[False],
                                                     ci=[True, False], lint=[False]))
        gh.api = lambda path: api(path, total=101)
        with self.assertRaises(ValueError): gh.check_results('h')

    def test_confirm_requires_merged_squash_on_verified_base_with_identical_forecast(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            def git(*args, data=None):
                return subprocess.check_output(['git', '-C', str(root), *args], input=data,
                                               stderr=subprocess.DEVNULL).decode().strip()
            git('init', '-b', 'main')
            git('config', 'user.name', 'Offline Test')
            git('config', 'user.email', 'test@example.invalid')
            (root/'weather-data/forecast').mkdir(parents=True)
            (root/'weather-data/forecast/source.json').write_bytes(b'old')
            git('add', '.'); git('commit', '-qm', 'base')
            base = git('rev-parse', 'HEAD')
            (root/'weather-data/forecast/source.json').write_bytes(b'new')
            git('commit', '-qam', 'bot head')
            head = git('rev-parse', 'HEAD')
            tree = git('rev-parse', f'{head}^{{tree}}')
            squash = git('commit-tree', tree, '-p', base, data=b'squash')
            wrong_parent = git('commit-tree', tree, '-p', head, data=b'wrong parent')
            (root/'weather-data/forecast/source.json').write_bytes(b'other')
            git('commit', '-qam', 'other forecast')
            other = git('commit-tree', git('rev-parse', 'HEAD^{tree}'), '-p', base, data=b'other')
            gh = refresh.GitHub(root)
            real_git = gh.git
            gh.git = lambda *a, **k: b'' if a[0] == 'fetch' else real_git(*a, **k)
            def confirm(merged, sha, main=None):
                gh.pull = lambda n: dict(merged=merged, merge_commit_sha=sha)
                gh.refs = lambda: (main or sha, None)
                gh.confirm(1, base, head)
            confirm(True, squash)
            for case in ((False, squash), (True, None), (True, wrong_parent), (True, other),
                         (True, squash, base)):
                with self.subTest(case=case), self.assertRaises(ValueError):
                    confirm(*case)

    def test_complete_bounded_pagination_and_fail_closed(self):
        gh = refresh.GitHub()
        gh.api = lambda p: dict(total_count=101, workflow_runs=[{}]*100 if '&page=1' in p else [{}])
        self.assertEqual(len(gh.pages('runs?created=day', 'workflow_runs')), 101)
        gh.api = lambda p: dict(total_count=102, workflow_runs=[{}]*100 if '&page=1' in p else [{}])
        with self.assertRaises(ValueError): gh.pages('runs?created=day', 'workflow_runs')
        gh.api = lambda p: [{}]*100
        with self.assertRaises(ValueError): gh.pages('pulls?state=all')

    def test_real_git_commit_diff_provenance_and_expected_lease(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            def git(*args):
                return subprocess.check_output(['git', '-C', str(root), *args], stderr=subprocess.DEVNULL).decode().strip()
            git('init', '-b', 'main')
            git('config', 'user.name', 'Offline Test')
            git('config', 'user.email', 'test@example.invalid')
            (root/'weather-data').mkdir()
            (root/'weather-data/cities.json').write_bytes(MANIFEST)
            git('add', '.')
            git('commit', '-m', 'synthetic base')
            base = git('rev-parse', 'HEAD')
            assembled = root/'assembled'
            shutil.copytree(root/'weather-data', assembled)
            (assembled/'forecast').mkdir()
            (assembled/'forecast/source.json').write_bytes(b'synthetic')
            gh = refresh.GitHub(root)
            meta = dict(base=base, day=NOW.date().isoformat(), acquired=NOW.isoformat())
            head = gh.commit(base, assembled, data.tree(root/'weather-data'), meta, root)
            self.assertEqual(gh.metadata(head), meta)
            self.assertEqual(git('diff', '--name-only', base, head), 'weather-data/forecast/source.json')
            (assembled/'cities.json').write_bytes(b'changed')
            with self.assertRaises(ValueError): gh.commit(base, assembled, data.tree(root/'weather-data'), meta, root)
            git('checkout', '-q', '-b', 'shapes', head)
            git('mv', 'weather-data/forecast/source.json', 'weather-data/forecast/renamed.json')
            git('commit', '-qm', 'rename inside forecast')
            gh.allowed(head, git('rev-parse', 'HEAD'))  # rename-free view: delete + add
            git('mv', 'weather-data/forecast/renamed.json', 'weather-data/moved.json')
            git('commit', '-qm', 'rename out of forecast')
            with self.assertRaises(ValueError): gh.allowed(head, git('rev-parse', 'HEAD'))
            git('checkout', '-q', head)
            (root/'weather-data/forecast/source.json').chmod(0o755)
            git('commit', '-qam', 'executable')
            with self.assertRaises(ValueError): gh.allowed(head, git('rev-parse', 'HEAD'))
            git('checkout', '-q', head)
            (root/'weather-data/forecast/link').symlink_to('source.json')
            git('add', '.'); git('commit', '-qm', 'symlink')
            with self.assertRaises(ValueError): gh.allowed(head, git('rev-parse', 'HEAD'))
            git('checkout', '-q', 'main')
            commands = []
            gh.git = lambda *a, **k: commands.append((a,k))
            with patch.dict('os.environ', GH_TOKEN='synthetic-noncredential'):
                gh.push(head, 'expected-sha')
            self.assertIn('--force-with-lease=refs/heads/codex/weather-forecast-data:expected-sha', commands[0][0])
            self.assertNotIn('main', commands[0][0][-1])
            self.assertNotIn('synthetic-noncredential', str(commands[0][0]))

    def test_workflow_static_contract(self):
        raw = (Path(__file__).resolve().parents[2]/'.github/workflows/weather-refresh.yml').read_text()
        self.assertIn("17 3,15 * * *", raw)
        self.assertIn("vars.TRAVEL_GIT_FORECAST_ENABLED == 'true'", raw)
        self.assertIn("github.ref == 'refs/heads/main'", raw)
        self.assertIn('cancel-in-progress: false', raw)
        self.assertIn('persist-credentials: false', raw)
        self.assertIn('fetch-depth: 0', raw)
        self.assertIn('timeout-minutes: 5', raw)
        for absent in ('TRAVEL_P1_', 'WORKER_DSN', 'BLOB_WRITE', 'pull_request_target', 'enable-auto-merge', 'web.refresh_weather'):
            self.assertNotIn(absent, raw)
        import re
        self.assertEqual(len(re.findall(r'uses: actions/[\w-]+@[0-9a-f]{40}', raw)), 4)
        automerge = raw.split('\n  automerge:\n', 1)[1]
        self.assertIn('needs: refresh', automerge)
        self.assertIn("if: github.event_name == 'schedule' && github.run_attempt == 1 && "
                      "vars.TRAVEL_FORECAST_AUTO_MERGE_ENABLED == 'true'", automerge)
        self.assertIn('if: ${{ failure() || cancelled() }}', automerge)
        self.assertEqual(automerge.count('--auto-merge "$PR"'), 1)
        self.assertLess(automerge.index('--auto-merge-verify'), automerge.index('--auto-merge "$PR"'))
        self.assertLess(automerge.index('--auto-merge "$PR"'), automerge.index('--auto-merge-close'))
        for permission in ('contents: write', 'pull-requests: write', 'checks: read', 'statuses: read'):
            self.assertIn(permission, automerge)
        self.assertNotIn('actions: write', raw)
        self.assertNotIn('${{ needs.refresh.outputs', automerge.split('steps:', 1)[1])
