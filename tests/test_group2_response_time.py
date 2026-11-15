"""Independent Team 2 tests for Group 6's Feature 3 (time to first response)."""

import contextlib
import csv
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import config
import data_loader
import run
from model import Issue
from response_time_analysis import ResponseTimeAnalysis, analyze, save_chart, save_dependency_chart

def make_issue(created, creator='zoe', comments=()):
    """Construct a controlled issue with a known creation date and comment history."""
    return Issue({
        'state': 'open',
        'creator': creator,
        'created_date': created,
        'labels': [],
        'events': [{'event_type': 'commented', 'author': author, 'event_date': date}
                   for author, date in comments],
    })

def mixed_dataset():
    """Two creation years with an answered and an unanswered issue, plus unusable records."""
    return [
        # 2019: the creator's own comment and a later reply lose to the earliest reply.
        make_issue('2019-01-01T00:00:00Z', comments=[
            ('zoe', '2019-01-01T01:00:00Z'),
            ('helper', '2019-01-01T05:00:00Z'),
            ('Helper', '2019-01-01T02:00:00Z'),
        ]),
        make_issue('2019-06-01T00:00:00Z', comments=[('ci[bot]', '2019-06-01T01:00:00Z')]),
        make_issue('2020-01-01T00:00:00Z', comments=[('helper', '2020-01-01T10:00:00Z')]),
        make_issue('2020-02-01T00:00:00Z', comments=[('other', '2020-02-01T20:00:00Z')]),
        make_issue('2020-03-01T00:00:00Z', comments=[('helper', '2020-03-02T06:00:00Z')]),
        make_issue(None, comments=[('helper', '2020-04-01T01:00:00Z')]),
        make_issue('2020-05-01T00:00:00Z', creator='   ',
                   comments=[('helper', '2020-05-01T01:00:00Z')]),
    ]

class Group2ResponseTimeTests(unittest.TestCase):
    def test_run_keeps_json_csv_console_and_charts_consistent(self):
        """End-to-end analysis methods must agree on known, mixed issue data."""
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tempdir:
            output = Path(tempdir) / 'nested' / 'results'
            settings = {
                'output_dir': str(output),
                'ENPM611_PROJECT_DATA_PATH': 'synthetic-fixture.json',
                'show': False,
            }
            console = io.StringIO()
            with patch('response_time_analysis.DataLoader') as loader, \
                 patch('response_time_analysis.config.get_parameter', side_effect=settings.get), \
                 contextlib.redirect_stdout(console):
                loader.return_value.get_issues.return_value = mixed_dataset()
                result = ResponseTimeAnalysis().run()

            self.assertEqual(result['summary']['total'], 7)
            self.assertEqual(result['summary']['eligible'], 5)
            self.assertEqual(result['summary']['answered'], 4)
            self.assertEqual(result['summary']['unanswered'], 1)
            self.assertEqual(result['summary']['missing_created'], 1)
            self.assertEqual(result['summary']['missing_creator'], 1)
            self.assertAlmostEqual(result['summary']['unanswered_percent'], 20)
            self.assertEqual(result['dataset'], 'synthetic-fixture.json')

            years = {row['year']: row for row in result['years']}
            self.assertEqual(sorted(years), [2019, 2020])
            self.assertAlmostEqual(years[2019]['median_hours'], 2)
            self.assertAlmostEqual(years[2019]['unanswered_percent'], 50)
            self.assertEqual(years[2019]['top_responder'], 'Helper')
            self.assertIsNone(years[2019]['median_hours_without_top'])
            self.assertAlmostEqual(years[2020]['median_hours'], 20)
            self.assertEqual(years[2020]['answered'], 3)
            self.assertAlmostEqual(years[2020]['top_responder_share_percent'], 200 / 3)
            self.assertEqual(result['top_responders'], [('Helper', 3), ('other', 1)])

            exported = json.loads((output / 'summary.json').read_text(encoding='utf-8'))
            self.assertEqual(exported['summary'], result['summary'])
            self.assertEqual(exported['years'], result['years'])
            with (output / 'first_response_by_year.csv').open(newline='', encoding='utf-8') as stream:
                csv_rows = {int(row['year']): row for row in csv.DictReader(stream)}
            self.assertEqual(set(csv_rows), set(years))
            self.assertEqual(float(csv_rows[2020]['median_hours']), 20)
            self.assertEqual(int(csv_rows[2020]['answered']), 3)
            self.assertEqual(csv_rows[2019]['median_hours_without_top'], '')

            self.assertIn('Issues analysed: 5 of 7', console.getvalue())
            self.assertIn('Answered: 4   No eligible response: 1 (20.0%)', console.getvalue())
            self.assertIn('2019 | 2 | 2.0 | 50.0% | Helper (100.0%) | N/A', console.getvalue())
            self.assertIn('2020 | 3 | 20.0 | 0.0% | Helper (66.7%) | 20.0', console.getvalue())
            self.assertIn('Helper: 3', console.getvalue())
            for name in ('first_response_by_year', 'first_response_without_top_responder'):
                png = (output / f'{name}.png').read_bytes()
                svg = (output / f'{name}.svg').read_text(encoding='utf-8')
                self.assertTrue(png.startswith(b'\x89PNG\r\n\x1a\n'))
                self.assertGreater(len(png), 1000)
                self.assertIn('<svg', svg)
            self.assertIn('Time to first response by issue creation year',
                          (output / 'first_response_by_year.svg').read_text(encoding='utf-8'))
            self.assertIn('2.0 h', (output / 'first_response_by_year.svg').read_text(encoding='utf-8'))

    def test_first_response_ignores_creator_bot_and_unusable_comments(self):
        """Only a dated comment by a known non-bot third party may start the clock."""
        issue = Issue({
            'state': 'open',
            'creator': 'Zoe',
            'created_date': '2020-01-01T00:00:00Z',
            'labels': [],
            'events': [
                {'event_type': 'labeled', 'author': 'triager',
                 'event_date': '2020-01-01T01:00:00Z'},
                {'event_type': 'commented', 'author': 'zoe',
                 'event_date': '2020-01-01T02:00:00Z'},
                {'event_type': 'commented', 'author': 'stale[bot]',
                 'event_date': '2020-01-01T03:00:00Z'},
                {'event_type': 'commented', 'author': None,
                 'event_date': '2020-01-01T04:00:00Z'},
                {'event_type': 'commented', 'author': 'undated', 'event_date': None},
                {'event_type': 'commented', 'author': 'early', 'event_date': '2019-12-31T00:00:00Z'},
                {'event_type': 'commented', 'author': 'human',
                 'event_date': '2020-01-01T09:00:00Z'},
            ],
        })
        row = analyze([issue])['years'][0]
        self.assertEqual(row['answered'], 1)
        self.assertEqual(row['top_responder'], 'human')
        self.assertAlmostEqual(row['median_hours'], 9)

        unanswered = analyze([make_issue('2021-01-01T00:00:00Z')])['years'][0]
        self.assertEqual(unanswered['answered'], 0)
        self.assertAlmostEqual(unanswered['unanswered_percent'], 100)
        self.assertIsNone(unanswered['median_hours'])
        self.assertIsNone(unanswered['top_responder'])

    def test_charts_explain_a_dataset_with_nothing_to_plot(self):
        """A dataset with no usable issue should produce explicit empty-state charts."""
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tempdir:
            output = Path(tempdir)
            save_chart([], output, show=False)
            save_dependency_chart([], output, show=False)
            self.assertIn('No issues with a usable creation date and creator',
                          (output / 'first_response_by_year.svg').read_text(encoding='utf-8'))
            self.assertIn('No answered issues to compare',
                          (output / 'first_response_without_top_responder.svg').read_text(encoding='utf-8'))

    def test_show_option_requests_display_for_both_charts(self):
        """The interactive option should display each of the two charts once."""
        rows = analyze(mixed_dataset())['years']
        with (
            tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tempdir,
            patch('matplotlib.pyplot.show') as show,
        ):
            save_chart(rows, Path(tempdir), show=True)
            save_dependency_chart(rows, Path(tempdir), show=True)
            self.assertEqual(show.call_count, 2)
            self.assertTrue((Path(tempdir) / 'first_response_by_year.png').is_file())
            self.assertTrue((Path(tempdir) / 'first_response_without_top_responder.png').is_file())

    def test_median_without_top_responder_cannot_be_faster_than_with_them(self):
        """Dropping the leading responder must not make the reported median improve."""
        issues = [
            make_issue('2020-01-01T00:00:00Z', comments=[('bob', '2020-01-05T04:00:00Z')]),
            make_issue('2020-01-01T00:00:00Z', comments=[('bob', '2020-01-05T04:00:00Z')]),
            make_issue('2020-01-01T00:00:00Z', comments=[('alice', '2020-01-01T01:00:00Z'),
                                                         ('bob', '2020-01-01T02:00:00Z')]),
        ]
        row = analyze(issues)['years'][0]
        self.assertEqual(row['top_responder'], 'bob')
        self.assertAlmostEqual(row['median_hours'], 100)
        self.assertGreaterEqual(
            row['median_hours_without_top'], row['median_hours'],
            'the two issues that lose their only reply were dropped from the '
            'sensitivity median instead of being counted as unanswered')

class Group2ResponseTimeCLIIntegrationTests(unittest.TestCase):
    def run_command(self, source, output):
        """Use the real argument parser, config, JSON loader, analysis, and exports."""
        buffer = io.StringIO()
        arguments = ['run.py', '--feature', '3', '--output-dir', str(output)]
        with patch.dict(os.environ, {'ENPM611_PROJECT_DATA_PATH': str(source),
                                     'MPLBACKEND': 'Agg'}), \
             patch.object(config, '_config', None), \
             patch.object(data_loader, '_ISSUES', None), \
             patch('sys.argv', arguments), \
             contextlib.redirect_stdout(buffer):
            run.main()
        return buffer.getvalue()

    def test_command_respects_real_json_loader_and_responder_capitalization(self):
        """A real command must import JSON and treat one responder's spellings as one person."""
        records = [
            {'state': 'closed', 'creator': 'zoe', 'created_date': '2020-01-01T00:00:00Z',
             'labels': ['kind/bug'],
             'events': [{'event_type': 'commented', 'author': 'zoe',
                         'event_date': '2020-01-01T00:00:00Z'},
                        {'event_type': 'commented', 'author': 'Maintainer',
                         'event_date': '2020-01-02T00:00:00Z'}]},
            {'state': 'open', 'creator': 'amir', 'created_date': '2020-06-01T00:00:00Z',
             'labels': [],
             'events': [{'event_type': 'commented', 'author': 'maintainer',
                         'event_date': '2020-06-03T00:00:00Z'}]},
            {'state': 'open', 'creator': 'nina', 'created_date': '2020-07-01T00:00:00Z',
             'labels': [],
             'events': [{'event_type': 'commented', 'author': 'stale[bot]',
                         'event_date': '2020-07-02T00:00:00Z'}]},
        ]
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temporary:
            source = Path(temporary) / 'issues.json'
            output = Path(temporary) / 'custom-output'
            source.write_text(json.dumps(records), encoding='utf-8')
            console = self.run_command(source, output)
            report = json.loads((output / 'summary.json').read_text(encoding='utf-8'))
            row = report['years'][0]
            self.assertIn(f'Loaded 3 issues from {source}', console)
            self.assertEqual(report['dataset'], str(source))
            self.assertEqual(report['summary']['eligible'], 3)
            self.assertEqual(report['summary']['answered'], 2)
            self.assertEqual(report['summary']['unanswered'], 1)
            self.assertEqual(row['year'], 2020)
            self.assertAlmostEqual(row['median_hours'], 36)
            self.assertEqual(row['top_responder'], 'Maintainer')
            self.assertAlmostEqual(row['top_responder_share_percent'], 100)
            self.assertEqual(report['top_responders'], [['Maintainer', 2]])
            self.assertTrue((output / 'first_response_by_year.png').is_file())
            self.assertTrue((output / 'first_response_without_top_responder.svg').is_file())

    def test_unusable_issue_state_does_not_abort_the_whole_report(self):
        """One issue with an unrecognised state must not stop a report that ignores state."""
        records = [
            {'state': 'open', 'creator': 'zoe', 'created_date': '2020-01-01T00:00:00Z',
             'labels': [],
             'events': [{'event_type': 'commented', 'author': 'bob',
                         'event_date': '2020-01-02T00:00:00Z'}]},
            {'state': 'merged', 'creator': 'amir', 'created_date': '2020-02-01T00:00:00Z',
             'labels': [], 'events': []},
        ]
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temporary:
            source = Path(temporary) / 'issues.json'
            output = Path(temporary) / 'results'
            source.write_text(json.dumps(records), encoding='utf-8')
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                try:
                    self.run_command(source, output)
                    code = 0
                except SystemExit as exit_request:
                    code = exit_request.code
            self.assertEqual(code, 0, f'the analysis exited with {stderr.getvalue().strip()!r}')
            self.assertTrue((output / 'summary.json').is_file())

    def test_bad_json_reports_an_error_without_a_traceback(self):
        """A malformed dataset must cause the CLI's documented friendly failure."""
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temporary:
            source = Path(temporary) / 'invalid.json'
            source.write_text('{not valid JSON', encoding='utf-8')
            output = Path(temporary) / 'results'
            stderr = io.StringIO()
            with (
                contextlib.redirect_stderr(stderr),
                self.assertRaises(SystemExit) as exit_context,
            ):
                self.run_command(source, output)
            self.assertEqual(exit_context.exception.code, 1)
            self.assertIn('Unable to run analysis', stderr.getvalue())
            self.assertIn('Check the dataset path and JSON format.', stderr.getvalue())
            self.assertNotIn('Traceback (most recent call last)', stderr.getvalue())
            self.assertFalse((output / 'summary.json').exists())

if __name__ == "__main__":
    unittest.main()
