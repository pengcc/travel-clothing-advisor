"""Local launch checks use synthetic stores and never acquire live weather."""
from contextlib import redirect_stdout
from datetime import timedelta
import io
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from test_forecasts import RECORDS
from test_live import NOW, forecast
from web.check_dev import check, main
from web.forecasts import Cache, MemoryStore

ROOT = Path(__file__).resolve().parents[2]


class DevCommandTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.history = self.root / 'history'
        self.forecasts = self.root / 'forecasts'
        self.history.mkdir()
        self.forecasts.mkdir()
        self.messages = []

    def prepared(self):
        # Only presence is checked for history; exact-trip validity is separate.
        block = self.history / 'history/era5/temp-v1/1/hash/2025-10.json.gz'
        block.parent.mkdir(parents=True)
        block.write_bytes(b'synthetic presence marker')
        store = MemoryStore()
        cache = Cache(store, lambda: NOW)
        cache.prefetch(RECORDS, lambda u, p, t: forecast(NOW))
        for name, data in store.objects.items():
            path = self.forecasts / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)

    def snapshot(self):
        return {str(p.relative_to(self.root)): p.read_bytes()
                for p in self.root.rglob('*') if p.is_file()}

    def run_check(self):
        with patch('web.check_dev.Cache', side_effect=lambda store: Cache(store, lambda: NOW)), \
                patch('urllib.request.urlopen', side_effect=AssertionError('Network forbidden')):
            return check(self.history, self.forecasts, self.messages.append)

    def test_missing_both_directories_no_creation(self):
        self.history.rmdir()
        self.forecasts.rmdir()
        self.assertFalse(self.run_check())
        self.assertEqual(len(self.messages), 3)
        self.assertIn('History directory missing', self.messages[0])
        self.assertIn('Forecast directory missing', self.messages[1])
        self.assertFalse(self.history.exists())
        self.assertFalse(self.forecasts.exists())

    def test_unreadable_directory_fails_without_writes(self):
        with patch('web.check_dev.os.scandir', side_effect=PermissionError()):
            self.assertFalse(self.run_check())
        self.assertEqual(self.snapshot(), {})
        self.assertTrue(any('unreadable' in m for m in self.messages))

    def test_empty_stores_fail_without_writes(self):
        self.assertFalse(self.run_check())
        self.assertTrue(any('unprepared' in m for m in self.messages))
        self.assertEqual(self.snapshot(), {})

    def test_prepared_read_only_and_coverage_caveat(self):
        self.prepared()
        before = self.snapshot()
        self.assertTrue(self.run_check())
        self.assertEqual(before, self.snapshot())
        self.assertFalse((self.forecasts / '.worker.lock').exists())
        self.assertTrue(any('NOT validated' in m for m in self.messages))

    def test_yesterday_and_corrupt_publications_fail(self):
        self.prepared()
        with patch('web.check_dev.Cache', side_effect=lambda store: Cache(store, lambda: NOW + timedelta(days=1))):
            self.assertFalse(check(self.history, self.forecasts, self.messages.append))
        manifest = next(self.forecasts.glob('forecast/featured-v1/*.json'))
        manifest.write_bytes(b'broken')
        self.assertFalse(self.run_check())

    def test_missing_source_fails(self):
        self.prepared()
        next(self.forecasts.glob('forecast/hourly-14d-v1/*/*/*.json')).unlink()
        self.assertFalse(self.run_check())

    def test_cli_exit_status(self):
        with redirect_stdout(io.StringIO()):
            self.assertEqual(main(['--history-dir', str(self.history),
                                   '--forecast-dir', str(self.forecasts)]), 1)

    @unittest.skipUnless(shutil.which('make'), 'make required')
    def test_make_expansion_and_failed_preflight_blocks_server(self):
        result = subprocess.run(['make', '-n', 'dev', 'test', 'demo'], cwd=ROOT,
                                capture_output=True, text=True, check=True)
        self.assertIn('-m web.server --history-dir ".history-local" --forecast-dir ".forecast-local" --port "8000"', result.stdout)
        self.assertIn('-m unittest discover -s tests/web -v', result.stdout)
        self.assertIn('-m web.server --fixtures --port "8000"', result.stdout)
        result = subprocess.run(['make', 'dev', f'HISTORY_DIR={self.root / "absent history"}',
                                 f'FORECAST_DIR={self.root / "absent forecast"}'],
                                cwd=ROOT, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('-m web.server', result.stdout)
        self.assertIn('History directory missing', result.stdout)
        self.assertIn('Forecast directory missing', result.stdout)
