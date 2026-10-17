"""Issue #36 operations: synthetic metadata and months, no external requests."""
from contextlib import redirect_stdout, redirect_stderr
from datetime import date
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from web.history import DirectoryStore, Library, key
from web.live import IDS, Unavailable, location
from web.prefetch_history import coverage, main, resolve_manifest
from test_history import month_data
from test_live import geo, NOW


class OperationsTests(unittest.TestCase):
    def test_metadata_validates_featured_ids_before_writing(self):
        with tempfile.TemporaryDirectory() as root:
            target = Path(root)/'cities.json'
            def fetch(url, params):
                self.assertTrue(url.endswith('/get'))
                return dict(geo(), id=params['id'])
            resolve_manifest(['munich', 'berlin'], target, fetch)
            self.assertEqual([r['id'] for r in json.loads(target.read_text())],
                             [IDS['munich'], IDS['berlin']])
            self.assertEqual(location(json.loads(target.read_text())[0])['id'], 'munich')
            with self.assertRaises(FileExistsError):
                resolve_manifest(['munich'], target, fetch)
            other = Path(root)/'bad.json'
            for raw in (geo(), dict(geo(), id=IDS['munich'], country_code='FR'),
                        dict(geo(), id=IDS['munich'], latitude=None)):
                with self.assertRaises((Unavailable, ValueError)):
                    resolve_manifest(['munich'], other, lambda *a:raw)
                self.assertFalse(other.exists())

    def test_cli_all_featured_metadata_and_partial_failure(self):
        with tempfile.TemporaryDirectory() as root:
            target = Path(root)/'cities.json'
            calls = []
            def fetch(url, params):
                calls.append(params['id'])
                return dict(geo(), id=params['id'])
            def resolve(ids, destination):
                return resolve_manifest(ids, destination, fetch)
            with patch('web.prefetch_history.resolve_manifest', side_effect=resolve), redirect_stdout(StringIO()):
                self.assertEqual(main(['--resolve-cities','--cities-file',str(target)]),0)
            self.assertEqual(len(calls),10)
            self.assertIn(IDS['munich'],calls)
            other = Path(root)/'partial.json'
            calls.clear()
            def fail_second(url, params):
                calls.append(params['id'])
                if len(calls) == 2:
                    raise Unavailable('Synthetic failure')
                return dict(geo(), id=params['id'])
            with self.assertRaises(Unavailable):
                resolve_manifest(['munich','berlin'],other,fail_second)
            self.assertFalse(other.exists())

    def test_cli_metadata_explicit_only_and_no_overwrite_requests(self):
        with tempfile.TemporaryDirectory() as root:
            manifest = Path(root)/'cities.json'
            manifest.write_text(json.dumps([geo()]))
            with patch('web.live.urlopen', side_effect=AssertionError('Network forbidden')):
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(['--cities-file',str(manifest),'--check',
                        '--start','2026-11-02','--end','2026-11-05']),1)
                with self.assertRaises(SystemExit), redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                    main(['--cities-file',str(manifest),'--resolve-cities'])

    def test_exact_coverage_readonly_valid_corrupt_missing_and_outage(self):
        city = location(geo())
        start, end = date(2026,11,2), date(2026,11,5)
        with tempfile.TemporaryDirectory() as root:
            lib = Library(DirectoryStore(root), lambda:NOW)
            lib.publish(city,'2021-11',month_data('2021-11'))
            lib.store.put(key(city,'2022-11'),b'corrupt')
            before = {str(p.relative_to(root)):p.read_bytes() for p in Path(root).rglob('*') if p.is_file()}
            with patch('web.history.urlopen',side_effect=AssertionError('Network forbidden')):
                report = coverage([city],start,end,root)
            states = report['cities'][0]['months']
            self.assertEqual(states['2021-11'],'valid')
            self.assertEqual(states['2022-11'],'missing_or_invalid')
            self.assertEqual(states['2025-11'],'missing_or_invalid')
            self.assertEqual(report['status'],'incomplete')
            self.assertEqual(report['cities'][0]['missing_equivalent_calls'],24)
            after = {str(p.relative_to(root)):p.read_bytes() for p in Path(root).rglob('*') if p.is_file()}
            self.assertEqual(before,after)
            with patch('web.prefetch_history.ReadOnlyDirectoryStore.get',side_effect=PermissionError()):
                self.assertEqual(coverage([city],start,end,root)['status'],'unreadable')
            missing = Path(root)/'absent'
            self.assertEqual(coverage([city],start,end,missing)['status'],'unreadable')
            self.assertFalse(missing.exists())
            self.assertEqual(coverage([city],start,end,None)['status'],'unconfigured')
            for year in range(2021,2026):
                lib.publish(city,f'{year}-11',month_data(f'{year}-11'))
            self.assertEqual(coverage([city],start,end,root)['status'],'complete')

    def test_rollover_leap_and_exact_download_jobs(self):
        city = location(geo())
        report = coverage([city],date(2026,12,20),date(2027,1,10),None)
        self.assertEqual(len(report['required_months']),10)
        self.assertIn('2026-01',report['required_months'])
        self.assertEqual(len(coverage([city],date(2028,2,29),date(2028,3,1),None)['required_months']),10)
        with tempfile.TemporaryDirectory() as root:
            manifest = Path(root)/'cities.json'
            manifest.write_text(json.dumps([geo()]))
            with patch('web.prefetch_history.Downloader.fill') as fill, redirect_stdout(StringIO()):
                self.assertEqual(main(['--cities-file',str(manifest),'--store',root,
                    '--start','2026-11-02','--end','2026-11-05','--download']),0)
            self.assertEqual([m for c,m in fill.call_args.args[0]],
                             [f'{y}-11' for y in range(2021,2026)])
            for extra in (['--city-id','munich'], ['--start','2026-11-01'],
                          ['--check'], ['--start','2026-11-01','--end','2026-12-15']):
                with self.assertRaises(SystemExit), redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                    main(['--cities-file',str(manifest),*extra])
