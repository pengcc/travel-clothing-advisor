"""Offline history export and one-command history PR flow against a real temporary git remote."""
from argparse import Namespace
from datetime import datetime
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from test_forecasts import RECORDS
from test_history import month_data
from web import history_pr
from web.data_commands import records_at, tree
from web.fixtures import BERLIN
from web.history import DirectoryStore, Library, key
from web.history_commands import MONTHS, export, inventory

real_sh = history_pr.sh


def git(*cmd, cwd):
    subprocess.run(('git',) + cmd, cwd=cwd, check=True, capture_output=True)


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.bundle, self.local = self.root / 'bundle', self.root / 'local'
        self.bundle.mkdir()
        (self.bundle / 'cities.json').write_text(json.dumps(RECORDS))
        (self.bundle / 'forecast').mkdir()
        (self.bundle / 'forecast' / 'keep.json').write_text('forecast')
        _, self.cities = records_at(self.bundle)
        self.clock = lambda: datetime(2026, 10, 24, tzinfo=BERLIN)

    def publish(self, root, city, month, value=14):
        Library(DirectoryStore(root), self.clock).publish(city, month, month_data(month, value))

    def test_adds_missing_and_repairs_invalid_without_touching_valid_git_or_other_paths(self):
        a, b, c = self.cities[0], self.cities[1], self.cities[2]
        self.publish(self.local, a, '2024-02')
        self.publish(self.local, a, '2024-03', value=11)
        self.publish(self.bundle, a, '2024-03', value=15)       # valid in Git: must win
        self.publish(self.local, b, '2024-02')
        DirectoryStore(self.bundle).put(key(b, '2024-02'), b'broken')  # invalid in Git: repaired
        self.publish(self.local, c, '2024-02')
        c_local_only_invalid = DirectoryStore(self.local)
        c_local_only_invalid.put(key(c, '2024-03'), b'broken')   # invalid locally: ignored
        git_valid_bytes = (self.bundle / key(a, '2024-03')).read_bytes()
        before = tree(self.bundle)
        with patch('urllib.request.urlopen', side_effect=AssertionError('network')):
            result = export(self.cities, self.local, self.bundle, self.clock)
        self.assertEqual((result['added'], result['repaired'], result['git_valid']), (2, 1, 4))
        self.assertEqual((self.bundle / key(a, '2024-03')).read_bytes(), git_valid_bytes)
        after = tree(self.bundle)
        self.assertEqual({n for n in after if after[n] != before.get(n)} ,
                         {key(a, '2024-02'), key(b, '2024-02'), key(c, '2024-02')})
        self.assertEqual(after['forecast/keep.json'], b'forecast')
        self.assertEqual(export(self.cities, self.local, self.bundle, self.clock)['added'], 0)
        self.assertEqual(inventory(self.cities, self.local, self.bundle, self.clock)['valid'], 4)

    def test_rejects_nested_roots_and_unreadable_sources(self):
        with self.assertRaises(ValueError):
            export(self.cities, self.bundle, self.bundle, self.clock)
        self.publish(self.local, self.cities[0], '2024-02')
        with patch('web.history_commands.ReadOnlyDirectoryStore.get', side_effect=PermissionError()):
            with self.assertRaises(OSError):
                export(self.cities, self.local, self.bundle, self.clock)
        self.assertFalse((self.bundle / 'history').exists())


class HistoryPrTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.origin, self.repo, self.local = root / 'origin.git', root / 'repo', root / 'local'
        self.repo.mkdir()
        git('init', '--bare', '-b', 'main', str(self.origin), cwd=root)
        git('init', '-b', 'main', cwd=self.repo)
        for k, v in (('user.name', 't'), ('user.email', 't@example.com')):
            git('config', k, v, cwd=self.repo)
        (self.repo / 'weather-data').mkdir()
        (self.repo / 'weather-data' / 'cities.json').write_text(json.dumps(RECORDS))
        git('add', '.', cwd=self.repo)
        git('commit', '-m', 'init', cwd=self.repo)
        git('remote', 'add', 'origin', str(self.origin), cwd=self.repo)
        git('push', '-u', 'origin', 'main', cwd=self.repo)
        previous = os.getcwd()
        os.chdir(self.repo)
        self.addCleanup(os.chdir, previous)
        self.clock = lambda: datetime(2026, 10, 24, tzinfo=BERLIN)
        self.gh = []
        patcher = patch.object(history_pr, 'sh', self.sh)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.args = Namespace(history_dir=str(self.local), bundle_dir=str(self.repo / 'weather-data'),
                              base='main', no_download=False, max_blocks=5, batch_calls=30,
                              daily_calls=60, monthly_calls=600, timeout=30)
        _, self.cities = records_at(self.args.bundle_dir)

    def sh(self, *cmd, check=True, strip=True):
        if cmd[0] == 'gh':
            self.gh.append(cmd)
            return 'https://github.example/pr/1' if cmd[1:3] == ('pr', 'create') else ''
        return real_sh(*cmd, check=check, strip=strip)

    def fake_backfill(self, months, stop='max_blocks'):
        def run(cities, local, bundle, clock, **kw):
            self.assertTrue(kw['seed'] and kw['download'])
            for month in months:
                Library(DirectoryStore(local), clock).publish(cities[0], month, month_data(month))
            return dict(stop_reason=stop, imported=0, new_valid=len(months),
                        run=dict(published=len(months), failed=0, http_requests=len(months), equivalent_calls=6 * len(months)))
        return run

    def branches(self):
        return real_sh('git', 'branch', '--format=%(refname:short)').split()

    def test_new_months_become_one_history_only_pr_and_operator_returns_to_start(self):
        rc = history_pr.run(self.args, self.clock, backfill=self.fake_backfill(['2024-02', '2024-03']))
        self.assertEqual(rc, 0)
        remote = real_sh('git', 'ls-remote', '--heads', 'origin', 'data/history-20261024')
        self.assertIn('data/history-20261024', remote)
        files = real_sh('git', 'diff', '--name-only', 'main', 'data/history-20261024').split()
        self.assertEqual(len(files), 2)
        self.assertTrue(all(f.startswith('weather-data/history/') for f in files))
        create = [c for c in self.gh if c[1:3] == ('pr', 'create')][0]
        self.assertIn('0/600 -> 2/600', ' '.join(create))
        self.assertEqual(real_sh('git', 'rev-parse', '--abbrev-ref', 'HEAD'), 'main')
        self.assertEqual(real_sh('git', 'status', '--porcelain'), '')
        # A second run the same day must not reuse the existing remote branch name.
        history_pr.run(self.args, self.clock, backfill=self.fake_backfill(['2024-04']))
        self.assertIn('data/history-20261024-2', self.branches())

    def test_pr_body_reports_last_error_without_provider_message(self):
        text = history_pr.body(220, dict(added=1, repaired=0, git_valid=221), dict(
            stop_reason='provider_or_storage_failure',
            run=dict(published=1, failed=1, http_requests=2, equivalent_calls=12,
                     last_error=dict(stage='request', type='HTTPError', job='berlin/2022-09',
                                     http_status=429, cooldown_seconds=300))))
        self.assertIn('Last error: HTTPError during request for berlin/2022-09, HTTP status 429, cooldown 300s', text)

    def test_nothing_new_leaves_no_branch_or_pr(self):
        rc = history_pr.run(self.args, self.clock, backfill=self.fake_backfill([], stop='complete'))
        self.assertEqual(rc, 0)
        self.assertEqual(self.branches(), ['main'])
        self.assertEqual([c for c in self.gh if c[1:3] == ('pr', 'create')], [])

    def test_no_download_exports_existing_local_months_without_backfill(self):
        Library(DirectoryStore(self.local), self.clock).publish(self.cities[0], '2024-02', month_data('2024-02'))
        self.args.no_download = True
        rc = history_pr.run(self.args, self.clock, backfill=lambda *a, **k: self.fail('download'))
        self.assertEqual(rc, 0)
        self.assertIn('--no-download', [c for c in self.gh if c[1:3] == ('pr', 'create')][0][-1])

    def test_repairing_a_tracked_invalid_month_is_in_scope(self):
        # A modified tracked file is the first porcelain entry (` M path`); it must not be misparsed.
        name = key(self.cities[0], '2024-02')
        DirectoryStore(self.args.bundle_dir).put(name, b'broken')
        git('add', '.', cwd=self.repo)
        git('commit', '-m', 'broken month', cwd=self.repo)
        git('push', 'origin', 'main', cwd=self.repo)
        Library(DirectoryStore(self.local), self.clock).publish(self.cities[0], '2024-02', month_data('2024-02'))
        self.args.no_download = True
        self.assertEqual(history_pr.run(self.args, self.clock), 0)
        files = real_sh('git', 'diff', '--name-only', 'main', 'data/history-20261024').split()
        self.assertEqual(files, ['weather-data/' + name])
        self.assertIn('repaired 1', [c for c in self.gh if c[1:3] == ('pr', 'create')][0][-1])

    def test_dirty_tree_and_abort_reasons_stop_cleanly(self):
        (self.repo / 'stray.txt').write_text('x')
        with self.assertRaises(history_pr.Stop):
            history_pr.run(self.args, self.clock, backfill=self.fake_backfill([]))
        self.assertEqual(self.branches(), ['main'])
        (self.repo / 'stray.txt').unlink()
        for reason in history_pr.ABORT:
            with self.assertRaises(history_pr.Stop):
                history_pr.run(self.args, self.clock, backfill=self.fake_backfill(['2024-02'], stop=reason))
            self.assertEqual(self.branches(), ['main'])
            self.assertEqual(real_sh('git', 'status', '--porcelain'), '')
        self.assertEqual([c for c in self.gh if c[1:3] == ('pr', 'create')], [])
        self.assertEqual(real_sh('git', 'ls-remote', '--heads', 'origin').count('data/history'), 0)

    def test_changes_outside_history_scope_abort_before_commit(self):
        def sneaky(cities, local, bundle, clock, **kw):
            (Path(bundle) / 'forecast').mkdir()
            (Path(bundle) / 'forecast' / 'x.json').write_text('x')
            return dict(stop_reason='max_blocks', run={})
        with self.assertRaises(history_pr.Stop):
            history_pr.run(self.args, self.clock, backfill=sneaky, export=lambda *a: dict(added=0, repaired=0, git_valid=0))
        # Nothing was committed or published; the unexpected file is left for the operator, not deleted.
        self.assertEqual(self.branches(), ['main'])
        self.assertEqual(real_sh('git', 'ls-remote', '--heads', 'origin').count('data/history'), 0)
        self.assertEqual(real_sh('git', 'status', '--porcelain', '--untracked-files=all'),
                         '?? weather-data/forecast/x.json')


if __name__ == '__main__':
    unittest.main()
