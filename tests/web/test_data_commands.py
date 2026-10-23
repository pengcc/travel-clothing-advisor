"""Offline daily maintenance regressions; all data is synthetic."""
from datetime import timedelta
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from test_forecasts import RECORDS
from test_live import NOW, forecast
from test_history import month_data
from web.data_commands import records_at, status, update, export, tree
from web.forecasts import Cache
from web.history import Library, DirectoryStore, key, plan


class DataCommandTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.bundle = self.root / 'bundle'
        self.bundle.mkdir()
        (self.bundle / 'cities.json').write_text(json.dumps(RECORDS))
        self.records, self.cities = records_at(self.bundle)
        self.f = self.root / 'forecasts'
        self.h = self.root / 'history'
        self.clock = lambda: NOW
        self.params = (self.cities, self.f, self.h, self.bundle, self.clock)

    def prepare(self):
        Cache(DirectoryStore(self.f), self.clock).prefetch(RECORDS, lambda *a: forecast(NOW))

    def test_status_readonly_and_git_reuse_without_provider(self):
        city, month = plan(self.cities, NOW.date())[0]
        Library(DirectoryStore(self.bundle), self.clock).publish(city, month, month_data(month))
        before = tree(self.root)
        report = status(*self.params)
        self.assertEqual(tree(self.root), before)
        self.assertEqual(report['valid_forecasts'], 0)
        self.assertIn(month, report['cities'][0]['valid_months'])
        self.prepare()
        # All missing historical blocks use the mocked provider, at most five.
        def provider(url, params, timeout):
            m = (NOW.date().fromisoformat(params['start_date']) + timedelta(days=1)).strftime('%Y-%m')
            return month_data(m)
        from web.history import Downloader
        original = Downloader.__init__
        def init(worker, *args, **kwargs):
            original(worker, *args, provider=provider, **kwargs)
        with patch.object(Downloader, '__init__', init), patch('web.forecasts.transport', side_effect=AssertionError()):
            result, ok = update(self.records, *self.params)
        self.assertTrue(ok)
        self.assertEqual(result['history_status'], 'paused_limit')
        self.assertEqual(result['history']['published'], 5)
        self.assertGreaterEqual(result['history']['hits'], 1)
        self.assertEqual((self.h / key(city, month)).read_bytes(), (self.bundle / key(city, month)).read_bytes())

    def test_export_gate_union_and_exclusion(self):
        before = tree(self.bundle)
        with self.assertRaises(ValueError):
            export(self.records, *self.params)
        self.assertEqual(before, tree(self.bundle))
        self.prepare()
        (self.bundle / 'README.md').write_text('Keep attribution')
        for root, month in ((self.bundle, '2020-01'), (self.h, '2022-05')):
            Library(DirectoryStore(root), self.clock).publish(self.cities[0], month, month_data(month))
        (self.h / 'usage.json').write_text('private metadata')
        result = export(self.records, *self.params)
        self.assertEqual(result['validated_objects'], 14)
        self.assertEqual((self.bundle / 'README.md').read_text(), 'Keep attribution')
        for month in ('2020-01', '2022-05'):
            self.assertTrue((self.bundle / key(self.cities[0], month)).exists())
        self.assertFalse((self.bundle / 'usage.json').exists())
        self.assertEqual(export(self.records, *self.params)['changed'], 0)

    def test_midnight_rolls_back(self):
        self.prepare()
        before = tree(self.bundle)
        from web import data_commands
        rename = Path.rename
        crossed = False
        def move(path, target):
            nonlocal crossed
            result = rename(path, target)
            if path.name == 'next':
                crossed = True
            return result
        clock = lambda: NOW + timedelta(days=int(crossed))
        with patch.object(Path, 'rename', move), self.assertRaises(ValueError):
            export(self.records, self.cities, self.f, self.h, self.bundle, clock)
        self.assertEqual(before, tree(self.bundle))

    def test_actual_make_status_no_writes_and_export_refuses_missing(self):
        before = tree(self.root)
        for command, success in (('data-status', True), ('data-export', False)):
            child = subprocess.run(['make', command, f'PYTHON={sys.executable}',
                f'DATA_DIR={self.bundle}', f'FORECAST_DIR={self.f}', f'HISTORY_DIR={self.h}'],
                capture_output=True, text=True)
            self.assertEqual(child.returncode == 0, success, child.stdout + child.stderr)
            self.assertEqual(tree(self.root), before)

    def test_command_update_and_export_all_cached_no_network(self):
        self.prepare()
        for city, month in plan(self.cities, NOW.date()):
            Library(DirectoryStore(self.bundle), self.clock).publish(city, month, month_data(month))
        guard = self.root / 'guard'
        guard.mkdir()
        (guard / 'sitecustomize.py').write_text(
            'import datetime, sys\n'
            'class Frozen(datetime.datetime):\n'
            '    @classmethod\n'
            '    def now(cls, tz=None):\n'
            f'        return cls.fromisoformat({NOW.isoformat()!r}).astimezone(tz)\n'
            'datetime.datetime = Frozen\n'
            'def deny(event, args):\n'
            '    if event in ("urllib.Request", "socket.connect"):\n'
            '        raise AssertionError("Network forbidden")\n'
            'sys.addaudithook(deny)\n')
        env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(guard), str(Path.cwd())]))
        for command in ('data-update', 'data-status', 'data-export'):
            child = subprocess.run(['make', command, f'PYTHON={sys.executable}',
                f'DATA_DIR={self.bundle}', f'FORECAST_DIR={self.f}', f'HISTORY_DIR={self.h}'],
                env=env, capture_output=True, text=True)
            self.assertEqual(child.returncode, 0, child.stdout + child.stderr)
            if command == 'data-update':
                self.assertIn('"http_requests": 0', child.stdout)
        self.assertEqual(status(*self.params)['pending_blocks'], 0)

    def test_invalid_local_history_cannot_mask_git_and_paths_cannot_overlap(self):
        self.prepare()
        month = '2020-01'
        name = key(self.cities[0], month)
        Library(DirectoryStore(self.bundle), self.clock).publish(self.cities[0], month, month_data(month))
        DirectoryStore(self.h).put(name, b'corrupt')
        DirectoryStore(self.h).put(name.replace(month, 'invalid'), b'corrupt')
        original = (self.bundle / name).read_bytes()
        export(self.records, *self.params)
        self.assertEqual((self.bundle / name).read_bytes(), original)
        before = tree(self.bundle)
        with self.assertRaises(ValueError):
            export(self.records, self.cities, self.bundle, self.h, self.bundle, self.clock)
        self.assertEqual(before, tree(self.bundle))

    def test_failed_swap_and_concurrent_destination_change_preserve_original(self):
        self.prepare()
        before = tree(self.bundle)
        rename = Path.rename
        def move(path, target):
            if path.name == 'next':
                raise OSError('Injected failed swap')
            return rename(path, target)
        with patch.object(Path, 'rename', move), self.assertRaises(OSError):
            export(self.records, *self.params)
        self.assertEqual(before, tree(self.bundle))
        from web import data_commands
        original = data_commands.valid_objects
        def read(*args, **kwargs):
            result = original(*args, **kwargs)
            if str(args[0][0]).endswith('/next'):
                (self.bundle / 'README.md').write_text('Concurrent edit')
            return result
        with patch.object(data_commands, 'valid_objects', read), self.assertRaises(ValueError):
            export(self.records, *self.params)
        self.assertEqual((self.bundle / 'README.md').read_text(), 'Concurrent edit')
