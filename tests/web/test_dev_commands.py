"""Local launch checks use synthetic stores and never acquire live weather."""
from contextlib import redirect_stdout
from datetime import timedelta
import io
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from test_forecasts import RECORDS
from test_live import NOW, forecast, geo
from test_history import month_data
from web.check_dev import check, main
from web.forecasts import Cache, MemoryStore
from web.history import DirectoryStore, Library
from web.live import GEO, IDS, Service, location
from web.prefetch_history import main as history_main
from web.server import Handler

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
                for p in self.root.rglob('*') if p.is_file() and 'guard' not in p.relative_to(self.root).parts}

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
    def test_make_expansion_without_preflight_dependency(self):
        result = subprocess.run(['make', '-n', 'dev', 'test', 'demo'], cwd=ROOT,
                                capture_output=True, text=True, check=True)
        self.assertIn('-m web.server --history-dir ".history-local" --forecast-dir ".forecast-local" --port "8000"', result.stdout)
        self.assertIn('-m unittest discover -s tests/web -v', result.stdout)
        self.assertIn('-m web.server --fixtures --port "8000"', result.stdout)
        self.assertNotIn('-m web.check_dev', result.stdout)

    @unittest.skipUnless(shutil.which('make'), 'make required')
    def test_make_dev_prepares_featured_when_configured_and_starts_after_failure(self):
        # A command stub exercises the actual Makefile without network or a server.
        fake_python = self.root / 'fake-python'
        calls = self.root / 'python-calls'
        fake_python.write_text(
            '#!/bin/sh\n'
            'printf "%s\\n" "$*" >> "$FAKE_PYTHON_CALLS"\n'
            'if [ "$2" = web.prefetch_forecasts ] && [ "$FAIL_PREFETCH" = 1 ]; then exit 1; fi\n'
            'exit 0\n')
        fake_python.chmod(0o700)
        for state, configured, fail in (('no-city-list', False, False),
                                         ('prepared-or-missing', True, False),
                                         ('worker-failed', True, True)):
            with self.subTest(state=state):
                manifest = self.forecasts / 'cities.json'
                if configured:
                    manifest.write_text('stub-only; never parsed')
                else:
                    manifest.unlink(missing_ok=True)
                calls.unlink(missing_ok=True)
                env = dict(os.environ, FAKE_PYTHON_CALLS=str(calls),
                           FAIL_PREFETCH='1' if fail else '0')
                result = subprocess.run(
                    ['make', 'dev', f'PYTHON={fake_python}',
                     f'HISTORY_DIR={self.history}', f'FORECAST_DIR={self.forecasts}'],
                    cwd=ROOT, env=env, capture_output=True, text=True, timeout=5)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                commands = calls.read_text().splitlines()
                self.assertEqual(len(commands), 2 if configured else 1)
                if configured:
                    self.assertIn('-m web.prefetch_forecasts --cities-file', commands[0])
                    self.assertIn(str(manifest), commands[0])
                    self.assertIn('--store-dir', commands[0])
                self.assertIn('-m web.server --history-dir', commands[-1])
                if fail or not configured:
                    self.assertIn('WARNING:', result.stdout)
                else:
                    self.assertNotIn('WARNING:', result.stdout)

    def launch(self, *, direct=False):
        # Installed only in the child interpreter. Freeze the German day to
        # match synthetic publications and fail/record every provider attempt.
        guard = self.root / 'guard'
        guard.mkdir(exist_ok=True)
        marker = self.root / 'provider-attempt'
        (guard / 'sitecustomize.py').write_text(
            'import datetime, sys\n'
            'from pathlib import Path\n'
            'class Frozen(datetime.datetime):\n'
            '    @classmethod\n'
            '    def now(cls, tz=None):\n'
            f'        return cls.fromisoformat({NOW.isoformat()!r}).astimezone(tz)\n'
            'datetime.datetime = Frozen\n'
            'def deny(event, args):\n'
            '    if event == "urllib.Request":\n'
            f'        Path({str(marker)!r}).write_text("attempted")\n'
            '        raise AssertionError("Provider forbidden")\n'
            'sys.addaudithook(deny)\n')
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0))
            port = probe.getsockname()[1]
        args = ([sys.executable, '-m', 'web.server', '--history-dir', str(self.history),
                 '--forecast-dir', str(self.forecasts), '--port', str(port)] if direct else
                ['make', 'dev', f'PYTHON={sys.executable}', f'HISTORY_DIR={self.history}',
                 f'FORECAST_DIR={self.forecasts}', f'PORT={port}'])
        env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(guard), str(ROOT)]))
        child = subprocess.Popen(args, cwd=ROOT, env=env, stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, text=True, start_new_session=True)

        def stop():
            try:
                os.killpg(child.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                output, _ = child.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                output, _ = child.communicate(timeout=5)
            self.assertFalse(marker.exists(), output)
        self.addCleanup(stop)
        self.stop_child = stop
        base = f'http://127.0.0.1:{port}'
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if child.poll() is not None:
                self.fail(child.communicate()[0])
            try:
                with urlopen(base + '/api/context', timeout=.2) as response:
                    self.assertFalse(json.load(response)['fixture_mode'])
                return base
            except (URLError, TimeoutError):
                time.sleep(.02)
        self.fail('Local server did not start within five seconds')

    @unittest.skipUnless(shutil.which('make'), 'make required')
    def test_actual_startup_missing_empty_stale_and_prepared_stores(self):
        for state in ('missing', 'empty', 'yesterday', 'prepared'):
            with self.subTest(state=state):
                self.history = self.root / (state + ' history')
                self.forecasts = self.root / (state + ' forecast')
                if state != 'missing':
                    self.history.mkdir()
                    self.forecasts.mkdir()
                if state in ('yesterday', 'prepared'):
                    self.prepared()
                    if state == 'yesterday':
                        manifest = next(self.forecasts.glob('forecast/featured-v1/*.json'))
                        manifest.rename(manifest.with_name((NOW.date() - timedelta(days=1)).isoformat() + '.json'))
                before = self.snapshot()
                base = self.launch()
                with urlopen(base + '/', timeout=2) as response:
                    self.assertEqual(response.status, 200)
                    self.assertIn(b'html', response.read())
                # Startup and context/page reads leave all file bytes intact.
                after = self.snapshot()
                self.assertEqual(before, {k: v for k, v in after.items() if not k.startswith('guard/')})
                with urlopen(base + '/api/featured', timeout=2) as response:
                    self.assertEqual(response.status, 200)
                    body = json.load(response)
                    self.assertFalse(body['fixture'])
                    self.assertEqual(len(body['cities']), 10)
                    self.assertEqual(body['cities'][0]['mode'],
                                     'forecast' if state == 'prepared' else 'unavailable')
                # Reads may create the existing worker lock, never ledger/data.
                self.assertEqual({k: v for k, v in before.items() if not k.endswith('.worker.lock')},
                                 {k: v for k, v in self.snapshot().items() if not k.endswith('.worker.lock')})
                self.stop_child()

    def test_direct_server_cli_starts_with_missing_stores(self):
        self.history.rmdir()
        self.forecasts.rmdir()
        self.launch(direct=True)
        self.assertTrue(self.history.is_dir())
        self.assertTrue(self.forecasts.is_dir())

    def command_until_exit(self, args, *, env=None, timeout=5):
        child = subprocess.Popen(args, cwd=ROOT, env=env, stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, text=True, start_new_session=True)
        try:
            output, _ = child.communicate(timeout=timeout)
            return child.returncode, output
        finally:
            # Kill the entire group even if make already exited. On timeout,
            # this also reaps a server that unexpectedly started successfully.
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            child.communicate(timeout=5)

    @unittest.skipUnless(shutil.which('make'), 'make required')
    def test_actual_invalid_path_fails(self):
        invalid = self.root / 'file'
        invalid.write_text('not a directory')
        code, output = self.command_until_exit(
            ['make', 'dev', f'HISTORY_DIR={invalid}', f'FORECAST_DIR={self.forecasts}'])
        self.assertNotEqual(code, 0)
        self.assertIn('FileExistsError', output)

    @unittest.skipUnless(shutil.which('make'), 'make required')
    def test_existing_inaccessible_directories_fail_before_listening(self):
        # Simulate OS denial in the child; chmod is ineffective under root.
        # Exercise both configured stores and both directory access operations.
        guard = self.root / 'guard'
        guard.mkdir()
        for directory in (self.history, self.forecasts):
            for operation in ('scandir', 'stat'):
                with self.subTest(directory=directory, operation=operation):
                    (guard / 'sitecustomize.py').write_text(
                        'import os\n'
                        f'original = os.{operation}\n'
                        # Keep the injected hook non-descriptor so Python 3.9
                        # pathlib does not bind its accessor as an extra argument.
                        'class DeniedAccess:\n'
                        '    def __call__(self, path, *args, **kwargs):\n'
                        f'        if str(path) == {str(directory) + ("/." if operation == "stat" else "")!r}:\n'
                        '            raise PermissionError("Injected inaccessible directory")\n'
                        '        return original(path, *args, **kwargs)\n'
                        f'os.{operation} = DeniedAccess()\n')
                    # Avoid stale bytecode when switching guards quickly.
                    shutil.rmtree(guard / '__pycache__', ignore_errors=True)
                    env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(guard), str(ROOT)]))
                    code, output = self.command_until_exit(
                        ['make', 'dev', f'PYTHON={sys.executable}',
                         f'HISTORY_DIR={self.history}', f'FORECAST_DIR={self.forecasts}'], env=env)
                    self.assertNotEqual(code, 0)
                    self.assertIn('PermissionError: Injected inaccessible directory', output)
                    self.assertNotIn('Local travel UI:', output)
        self.assertEqual(self.snapshot(), {})

    def test_timeout_reaps_unexpected_running_process(self):
        # A real timeout must kill/reap a child rather than leaving a listener.
        child_pid = self.root / 'child.pid'
        with self.assertRaises(subprocess.TimeoutExpired):
            self.command_until_exit(
                [sys.executable, '-c',
                 'import os, time; from pathlib import Path; '
                 f'Path({str(child_pid)!r}).write_text(str(os.getpid())); time.sleep(60)'],
                timeout=1)
        pid = int(child_pid.read_text())
        with self.assertRaises(ProcessLookupError):
            os.kill(pid, 0)


class FixtureRouteContractTests(unittest.TestCase):
    def setUp(self):
        self.provider = Mock(side_effect=OSError('Provider forbidden in offline test'))
        # Exercise the real router without opening sockets or mutating Handler.
        self.handler = Handler.__new__(Handler)
        self.handler.fixtures_only = True
        self.handler.service = Service(self.provider, lambda: NOW)
        self.handler.send_json = Mock()

    def request(self, path):
        self.handler.path = path
        self.handler.send_json.reset_mock()
        with patch('web.live.urlopen', side_effect=AssertionError('Network forbidden')):
            self.handler.do_GET()
        self.handler.send_json.assert_called_once()
        return self.handler.send_json.call_args.args

    def test_fixture_advice_search_featured_and_context_need_no_provider(self):
        routes = ['/api/cities?q=Berlin', '/api/cities?q=Unknown',
                  '/api/featured',
                  '/api/advice?view=trip&city_id=berlin&start=2026-10-17&end=2026-10-18&preference=normal',
                  '/api/advice?view=city&city_id=berlin']
        for route in routes:
            with self.subTest(route=route):
                status, body = self.request(route)
                self.assertEqual(status, 200)
                self.assertTrue(body['fixture'])
        status, body = self.request('/api/context')
        self.assertEqual(status, 200)
        self.assertTrue(body['fixture_mode'])
        self.provider.assert_not_called()

    def test_fixture_city_resolution_remains_a_provider_dependent_exception(self):
        # A valid non-featured shared-link ID still reaches GeoNames. The test
        # denies the call and verifies failure; it never acquires real metadata.
        status, body = self.request('/api/city?city_id=1234567')
        self.provider.assert_called_once_with(GEO + 'get', {'id': '1234567'})
        self.assertEqual(status, 503)
        self.assertNotIn('city', body)


class HistoryCheckSelectionTests(unittest.TestCase):
    def test_selected_city_complete_while_manifest_wide_check_is_incomplete(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as root:
            root = Path(root)
            records = [geo(), geo(IDS['hamburg'], name='Hamburg', admin1='Hamburg')]
            manifest = root / 'cities.json'
            manifest.write_text(json.dumps(records))
            store = root / 'store'
            library = Library(DirectoryStore(store), lambda: NOW)
            for year in range(2021, 2026):
                month = f'{year}-11'
                library.publish(location(records[0]), month, month_data(month))
            before = {p.relative_to(root): p.read_bytes()
                      for p in root.rglob('*') if p.is_file()}
            args = ['--check', '--store', str(store), '--cities-file', str(manifest),
                    '--start', '2026-11-02', '--end', '2026-11-05']
            for selection, expected_status, expected_code, expected_cities in (
                    (['--city-id', 'berlin'], 'complete', 0, ['berlin']),
                    ([], 'incomplete', 1, ['berlin', 'hamburg'])):
                with self.subTest(selection=selection), redirect_stdout(io.StringIO()) as out, \
                        patch('web.live.urlopen', side_effect=AssertionError('Network forbidden')), \
                        patch('web.history.urlopen', side_effect=AssertionError('Network forbidden')):
                    self.assertEqual(history_main(args + selection), expected_code)
                    report = json.loads(out.getvalue())
                    self.assertEqual(report['status'], expected_status)
                    self.assertEqual([c['city_id'] for c in report['cities']], expected_cities)
                    self.assertEqual(report['http_requests'], 0)
            after = {p.relative_to(root): p.read_bytes()
                     for p in root.rglob('*') if p.is_file()}
            self.assertEqual(before, after)
