"""Offline fixed-year inventory and bounded operator workflow."""
from datetime import datetime, timedelta
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from test_forecasts import RECORDS
from test_history import month_data
from web.data_commands import records_at, tree
from web.fixtures import BERLIN
from web.history import DirectoryStore, Library, LEDGER, key
from web.history_commands import MONTHS, inventory, backfill, main


class HistoryCommandTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.bundle = self.root / 'bundle'
        self.bundle.mkdir()
        (self.bundle / 'cities.json').write_text(json.dumps(RECORDS))
        _, self.cities = records_at(self.bundle)
        self.local = self.root / 'local'
        self.clock = lambda: datetime(2026, 10, 24, tzinfo=BERLIN)
        self.args = (self.cities, self.local, self.bundle, self.clock)

    def publish(self, root, city, month, value=14):
        Library(DirectoryStore(root), self.clock).publish(city, month, month_data(month, value))

    def provider(self, url, params, timeout):
        self.assertLessEqual(timeout, 4)
        month = (datetime.fromisoformat(params['start_date']) + timedelta(days=1)).strftime('%Y-%m')
        return month_data(month)

    def test_readonly_600_and_invalid_unreadable(self):
        before = tree(self.root)
        stamps = {p: p.stat().st_mtime_ns for p in self.root.rglob('*')}
        with patch('urllib.request.urlopen', side_effect=AssertionError('network')):
            result = inventory(*self.args)
            backfill(*self.args)
        self.assertEqual(result['missing'], 600)
        self.assertEqual(result['equivalent_calls'], 3600)
        self.assertEqual(before, tree(self.root))
        self.assertEqual(stamps, {p: p.stat().st_mtime_ns for p in self.root.rglob('*')})
        self.assertFalse(self.local.exists())
        store = DirectoryStore(self.local)
        store.put(key(self.cities[0], MONTHS[0]), b'broken')
        self.assertEqual(inventory(*self.args)['invalid'], 1)
        with patch('web.history_commands.ReadOnlyDirectoryStore.get', side_effect=PermissionError()):
            report = inventory(*self.args)
        self.assertEqual(report['unreadable'], 600)
        self.assertEqual(report['status'], 'unreadable')

    def test_seed_preserves_valid_bytes_and_ledger(self):
        city = self.cities[0]
        for root, value in ((self.local, 12), (self.bundle, 13)):
            self.publish(root, city, '2024-02', value)
        self.publish(self.bundle, city, '2024-03')
        DirectoryStore(self.local).put(key(city, '2024-03'), b'corrupt local month')
        store = DirectoryStore(self.local)
        store.put(LEDGER, b'unchanged ledger')
        before = tree(self.local)
        result = backfill(*self.args, seed=True)
        self.assertEqual(result['imported'], 1)
        self.assertEqual(store.get(LEDGER), before[LEDGER])
        self.assertEqual(store.get(key(city, '2024-02')), before[key(city, '2024-02')])
        self.assertEqual(backfill(*self.args, seed=True)['imported'], 0)
        self.assertEqual((self.local / key(city, '2024-03')).read_bytes(),
                         (self.bundle / key(city, '2024-03')).read_bytes())

    def test_bounded_resume_and_429_cooldown(self):
        first = backfill(*self.args, download=True, provider=self.provider, max_blocks=1)
        self.assertEqual(first['run']['published'], 1)
        self.assertEqual(first['stop_reason'], 'max_blocks')
        second = backfill(*self.args, download=True, provider=self.provider, daily=6)
        self.assertEqual(second['http_requests'], 0)
        def fail(*args):
            raise HTTPError('url', 429, 'rate', {'Retry-After': '900'}, None)
        result = backfill(*self.args, download=True, provider=fail)
        self.assertEqual(result['run']['failed'], 1)
        ledger = json.loads((self.local / LEDGER).read_bytes())
        self.assertEqual(ledger['days']['2026-10-24'], 12)
        self.assertGreaterEqual(ledger['cooldown_until'], self.clock().timestamp()+900)
        self.assertEqual(backfill(*self.args, download=True, provider=self.provider)['stop_reason'], 'cooldown')
        self.assertEqual(inventory(*self.args)['valid'], 1)

    def test_invalid_ledger_and_lock_fail_closed(self):
        store = DirectoryStore(self.local)
        store.put(LEDGER, b'bad')
        provider = lambda *a: self.fail('network')
        self.assertEqual(backfill(*self.args, download=True, provider=provider)['stop_reason'], 'invalid_ledger')
        with store.exclusive():
            self.assertEqual(backfill(*self.args, download=True, provider=provider)['stop_reason'], 'locked')

    def test_full_600_and_repeat_no_network(self):
        for city in self.cities:
            for month in MONTHS:
                self.publish(self.bundle, city, month)
        result = inventory(*self.args)
        self.assertEqual((result['valid'], result['status']), (600, 'complete'))
        result = backfill(*self.args, download=True, provider=lambda *a: self.fail('network'))
        self.assertEqual(result['imported'], 600)
        self.assertEqual(result['http_requests'], 0)
        self.assertEqual(backfill(*self.args, download=True, provider=lambda *a: self.fail('network'))['imported'], 0)

    def test_cli_and_manifest_rejection(self):
        with patch('builtins.print') as output:
            self.assertEqual(main(['status', '--bundle-dir', str(self.bundle), '--history-dir', str(self.local)]), 0)
        self.assertEqual(json.loads(output.call_args_list[0].args[0])['total'], 600)
        (self.bundle / 'cities.json').write_text(json.dumps(RECORDS[:-1]))
        with patch('builtins.print'):
            self.assertEqual(main(['status', '--bundle-dir', str(self.bundle)]), 1)
        with self.assertRaises(ValueError):
            backfill(self.cities, self.bundle, self.bundle, self.clock, seed=True)
        for timeout in (float('nan'), float('inf'), 0):
            with self.assertRaises(ValueError):
                backfill(*self.args, download=True, timeout=timeout)
