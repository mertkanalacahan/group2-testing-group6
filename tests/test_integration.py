"""Deterministic CLI tests; no network and no course dataset required."""
import csv
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class CommandLineTests(unittest.TestCase):
    def run_feature(self, folder, records):
        source = folder / 'fixture.json'
        source.write_text(json.dumps(records), encoding='utf-8')
        output = folder / 'results'
        env = os.environ.copy()
        env['ENPM611_PROJECT_DATA_PATH'] = str(source)
        env['MPLBACKEND'] = 'Agg'
        env.pop('show', None)
        # Under coverage, collect subprocess execution in separate data files.
        prefix = [sys.executable]
        if env.get('TEAM6_COVERAGE') == '1':
            prefix += ['-m', 'coverage', 'run', '--parallel-mode', '--branch',
                       '--source=resolution_time_analysis,issue_utils,run']
        proc = subprocess.run(prefix + ['run.py', '--feature', '1', '--output-dir', str(output)],
                              cwd=ROOT, env=env, capture_output=True, text=True, timeout=90)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return output

    def test_fixture_outputs_and_values(self):
        records = []
        for state, day in [('closed', 3), ('closed', 5), ('open', None)]:
            records.append(dict(state=state, created_date='2024-01-01T00:00:00Z',
                                labels=['kind/bug'], events=[] if day is None else [
                                    dict(event_type='closed', author='person', event_date=f'2024-01-{day:02}T00:00:00Z')]))
        with tempfile.TemporaryDirectory() as temporary:
            output = self.run_feature(Path(temporary), records)
            data = json.loads((output/'summary.json').read_text())
            self.assertEqual(data['summary']['eligible'], 2)
            self.assertEqual(data['summary']['open'], 1)
            self.assertEqual(data['groups'][0]['median_days'], 3)
            with (output/'closure_by_label.csv').open(newline='') as stream:
                row = next(csv.DictReader(stream))
            self.assertEqual(float(row['median_days']), 3)
            self.assertAlmostEqual(float(row['open_percent']), 100/3)
            for family in ('area', 'kind'):
                self.assertTrue((output/f'closure_by_{family}.png').read_bytes().startswith(b'\x89PNG\r\n\x1a\n'))
                self.assertIn('<svg', (output/f'closure_by_{family}.svg').read_text())

    def test_empty_dataset_outputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = self.run_feature(Path(temporary), [])
            data = json.loads((output/'summary.json').read_text())
            self.assertEqual(data['summary']['total'], 0)
            self.assertEqual(data['summary']['open_percent'], 0)
            self.assertEqual(data['groups'], [])
