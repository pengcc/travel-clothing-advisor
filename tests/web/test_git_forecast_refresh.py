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

    def prs(self):
        return self.pr_list

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
        self.pending = self.root / 'pending'
        if self.pending.exists():
            shutil.rmtree(self.pending)
        shutil.copytree(assembled, self.pending)
        self.writes.append('commit')
        return 'new-head'

    def push(self, head, expected):
        if self.head != expected:
            raise ValueError('lease')
        self.head, self.meta = head, self.pending_meta
        self.branch = self.pending
        self.writes.append('push')

    def publish_pr(self, head, meta, prs):
        if self.fail_api:
            raise ValueError('API failure')
        self.writes.append('pr')
        self.pr_list = [dict(state='open', head=dict(sha=head), merged_at=None)]


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


class GitProtocolTests(unittest.TestCase):
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
        self.assertIn('timeout-minutes: 5', raw)
        for absent in ('TRAVEL_P1_', 'WORKER_DSN', 'BLOB_WRITE', 'pull_request_target', 'enable-auto-merge', 'web.refresh_weather'):
            self.assertNotIn(absent, raw)
        import re
        self.assertEqual(len(re.findall(r'uses: actions/[\w-]+@[0-9a-f]{40}', raw)), 2)
