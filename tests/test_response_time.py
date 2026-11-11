"""Feature 3 tests: first-response time by creation year. No course dataset needed."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from model import Issue
from response_time_analysis import analyze

ROOT = Path(__file__).resolve().parents[1]


def comment(date, author='helper', kind='commented'):
    return dict(event_type=kind, event_date=date, author=author)


def issue(created='2024-01-01T00:00:00Z', creator='creator', events=None):
    return Issue(dict(state='open', created_date=created, creator=creator,
                      events=events if events is not None else []))


class FirstResponseTests(unittest.TestCase):
    def test_median_hours_and_unanswered_percent(self):
        rows = analyze([
            issue(events=[comment('2024-01-01T02:00:00Z')]),
            issue(events=[comment('2024-01-01T06:00:00Z')]),
            issue(events=[]),
        ])['years']
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['median_hours'], 4)
        self.assertEqual((rows[0]['answered'], rows[0]['unanswered']), (2, 1))
        self.assertAlmostEqual(rows[0]['unanswered_percent'], 100 / 3)

    def test_bot_and_creator_comments_do_not_count(self):
        result = analyze([issue(events=[comment('2024-01-01T01:00:00Z', 'creator'),
                                        comment('2024-01-01T02:00:00Z', 'CI[bot]')])])
        self.assertEqual(result['summary']['unanswered'], 1)
        self.assertIsNone(result['years'][0]['median_hours'])

    def test_earliest_reply_wins_regardless_of_order(self):
        rows = analyze([issue(events=[comment('2024-01-02T00:00:00Z', 'late'),
                                      comment('2024-01-01T03:00:00Z', 'early')])])['years']
        self.assertEqual(rows[0]['median_hours'], 3)
        self.assertEqual(rows[0]['top_responder'], 'early')

    def test_grouped_by_creation_year_not_reply_year(self):
        rows = analyze([issue(created='2022-12-31T23:00:00Z',
                              events=[comment('2023-01-01T01:00:00Z')])])['years']
        self.assertEqual([r['year'] for r in rows], [2022])
        self.assertEqual(rows[0]['median_hours'], 2)

    def test_missing_metadata_excluded_not_unanswered(self):
        s = analyze([issue(created=None), issue(creator=None), issue(creator='  ')])['summary']
        self.assertEqual((s['missing_created'], s['missing_creator']), (1, 2))
        self.assertEqual((s['eligible'], s['unanswered']), (0, 0))

    def test_undated_and_early_comments_ignored(self):
        result = analyze([issue(events=[comment(None), comment('2023-12-31T00:00:00Z')])])
        self.assertEqual(result['summary']['unanswered'], 1)

    def test_timezone_offsets_normalized(self):
        rows = analyze([issue(created='2024-01-01T01:00:00+01:00',
                              events=[comment('2024-01-01T01:00:00Z')])])['years']
        self.assertEqual(rows[0]['median_hours'], 1)

    def test_empty_dataset(self):
        result = analyze([])
        self.assertEqual(result['years'], [])
        self.assertEqual(result['summary']['unanswered_percent'], 0)
        self.assertEqual(result['top_responders'], [])

    def test_sensitivity_without_top_responder(self):
        issues = [issue(events=[comment('2024-01-01T01:00:00Z', 'fast'),
                                comment('2024-01-01T10:00:00Z', 'slow')]),
                  issue(events=[comment('2024-01-01T02:00:00Z', 'fast')])]
        row = analyze(issues)['years'][0]
        self.assertEqual(row['top_responder'], 'fast')
        self.assertEqual(row['top_responder_share_percent'], 100)
        self.assertEqual(row['median_hours'], 1.5)
        self.assertEqual(row['median_hours_without_top'], 10)

    def test_sensitivity_does_not_change_shared_issues(self):
        obj = issue(events=[comment('2024-01-01T01:00:00Z', 'fast')])
        analyze([obj])
        self.assertEqual(len(obj.events), 1)

    def test_username_capitalization_counts_as_one_person(self):
        # "Helper" and "helper" are the same GitHub account.
        result = analyze([issue(events=[comment('2024-01-01T01:00:00Z', 'Helper')]),
                          issue(events=[comment('2024-01-01T02:00:00Z', 'helper')])])
        row = result['years'][0]
        self.assertEqual(row['top_responder'], 'Helper')
        self.assertEqual(row['top_responder_share_percent'], 100)
        self.assertEqual(result['top_responders'], [('Helper', 2)])

    def test_without_top_removes_every_spelling(self):
        issues = [issue(events=[comment('2024-01-01T01:00:00Z', 'Helper'),
                                comment('2024-01-01T09:00:00Z', 'other')]),
                  issue(events=[comment('2024-01-01T02:00:00Z', 'HELPER'),
                                comment('2024-01-01T05:00:00Z', 'helper')])]
        row = analyze(issues)['years'][0]
        self.assertEqual(row['top_responder_share_percent'], 100)
        self.assertEqual(row['median_hours_without_top'], 9)


class CommandLineTests(unittest.TestCase):
    def run_module(self, records):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            (folder / 'fixture.json').write_text(json.dumps(records), encoding='utf-8')
            env = os.environ.copy()
            env.update(ENPM611_PROJECT_DATA_PATH=str(folder / 'fixture.json'),
                       output_dir=str(folder / 'out'), MPLBACKEND='Agg')
            env.pop('show', None)
            proc = subprocess.run([sys.executable, 'response_time_analysis.py'], cwd=ROOT,
                                  env=env, capture_output=True, text=True, timeout=90)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            data = json.loads((folder / 'out' / 'summary.json').read_text())
            for chart in ('first_response_by_year', 'first_response_without_top_responder'):
                self.assertTrue((folder / 'out' / f'{chart}.png')
                                .read_bytes().startswith(b'\x89PNG\r\n\x1a\n'))
                self.assertIn('<svg', (folder / 'out' / f'{chart}.svg').read_text())
            return data, proc.stdout

    def test_zero_hour_response_does_not_crash_charts(self):
        # A reply at the exact moment the issue was opened gives a 0-hour wait,
        # which a log-scale chart cannot show. The run must still finish.
        records = [dict(state='open', creator='a', created_date='2024-01-01T00:00:00Z',
                        events=[comment('2024-01-01T00:00:00Z', 'b')])]
        data, _ = self.run_module(records)
        self.assertEqual(data['years'][0]['median_hours'], 0)
        self.assertIsNone(data['years'][0]['median_hours_without_top'])

    def test_mixed_zero_and_positive_waits(self):
        records = [dict(state='open', creator='a', created_date=f'{year}-01-01T00:00:00Z',
                        events=[comment(f'{year}-01-01T0{hour}:00:00Z', 'b'),
                                comment(f'{year}-01-01T05:00:00Z', 'c')])
                   for year, hour in ((2023, 0), (2024, 2))]
        data, _ = self.run_module(records)
        self.assertEqual([r['median_hours'] for r in data['years']], [0, 2])

    def test_fixture_outputs(self):
        records = [dict(state='open', creator='a', created_date='2024-01-01T00:00:00Z',
                        events=[comment('2024-01-01T05:00:00Z', 'b')]),
                   dict(state='open', creator='a', created_date='2024-01-01T00:00:00Z', events=[])]
        data, stdout = self.run_module(records)
        self.assertEqual(data['years'][0]['median_hours'], 5)
        self.assertEqual(data['summary']['unanswered'], 1)
        self.assertIn('Question:', stdout)

    def test_empty_dataset_does_not_crash(self):
        data, _ = self.run_module([])
        self.assertEqual(data['years'], [])


class RunInProcessTests(unittest.TestCase):
    """Run ResponseTimeAnalysis.run() in this process so coverage tools can
    measure the report and chart code. Loading is replaced with fixed issues."""

    CHARTS = ('first_response_by_year', 'first_response_without_top_responder')

    def run_analysis(self, issues):
        from contextlib import redirect_stdout
        from io import StringIO
        from unittest import mock
        import response_time_analysis
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary) / 'out'
            env = {'output_dir': str(out), 'MPLBACKEND': 'Agg', 'show': 'json:false'}
            stdout = StringIO()
            with mock.patch.dict(os.environ, env), \
                    mock.patch.object(response_time_analysis, 'DataLoader') as loader, \
                    redirect_stdout(stdout):
                loader.return_value.get_issues.return_value = issues
                result = response_time_analysis.ResponseTimeAnalysis().run()
            files = sorted(p.name for p in out.iterdir())
            for chart in self.CHARTS:
                self.assertTrue((out / f'{chart}.png').read_bytes().startswith(b'\x89PNG'))
            saved = json.loads((out / 'summary.json').read_text())
        return result, saved, stdout.getvalue(), files

    def test_multi_year_report_and_files(self):
        issues = [issue(created='2023-01-01T00:00:00Z',
                        events=[comment('2023-01-01T02:00:00Z', 'fast'),
                                comment('2023-01-01T08:00:00Z', 'slow')]),
                  issue(created='2024-01-01T00:00:00Z',
                        events=[comment('2024-01-01T01:00:00Z', 'fast')]),
                  issue(created='2024-06-01T00:00:00Z')]
        result, saved, stdout, files = self.run_analysis(issues)
        self.assertEqual(saved['years'], result['years'])
        self.assertEqual([r['median_hours'] for r in result['years']], [2, 1])
        self.assertIn('Finding: median first response went from 2.0 h in 2023 to 1.0 h in 2024', stdout)
        self.assertIn('fast: 2', stdout)
        self.assertEqual(files, sorted(['first_response_by_year.csv', 'summary.json'] +
                                       [f'{c}.{e}' for c in self.CHARTS for e in ('png', 'svg')]))

    def test_year_with_no_replies_at_all(self):
        result, _, stdout, _ = self.run_analysis([issue(), issue()])
        self.assertIsNone(result['years'][0]['median_hours'])
        self.assertIn('N/A', stdout)

    def test_zero_hour_wait_uses_normal_scale(self):
        result, _, _, _ = self.run_analysis([issue(events=[comment('2024-01-01T00:00:00Z')])])
        self.assertEqual(result['years'][0]['median_hours'], 0)

    def test_no_usable_issues(self):
        result, _, stdout, _ = self.run_analysis([issue(created=None)])
        self.assertEqual(result['years'], [])
        self.assertIn('excluded: 1 missing creation date', stdout)
        self.assertNotIn('Finding:', stdout)


if __name__ == '__main__':
    unittest.main()
