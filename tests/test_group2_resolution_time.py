"""Independent Team 2 tests for Group 6's time-to-closure analysis."""

import contextlib
import csv
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from model import Issue
from resolution_time_analysis import ResolutionTimeAnalysis, save_charts


def make_issue(state, labels, closure_date=None):
    """Construct a controlled issue with a known creation and closure date."""
    events = []
    if closure_date is not None:
        events.append({
            'event_type': 'closed',
            'author': 'human-maintainer',
            'event_date': closure_date,
        })
    return Issue({
        'state': state,
        'created_date': '2024-01-01T00:00:00Z',
        'labels': labels,
        'events': events,
    })


class Group2ResolutionTimeTests(unittest.TestCase):
    def test_run_keeps_json_csv_console_and_charts_consistent(self):
        """End-to-end analysis methods must agree on known, mixed issue data."""
        issues = [
            make_issue('closed', ['kind/bug', 'area/solver'], '2024-01-03T00:00:00Z'),
            make_issue('closed', ['kind/bug'], '2024-01-07T00:00:00Z'),
            make_issue('open', ['kind/bug']),
            make_issue('closed', ['kind/feature'], closure_date=None),
        ]
        with tempfile.TemporaryDirectory() as tempdir:
            output = Path(tempdir) / 'nested' / 'results'
            settings = {
                'output_dir': str(output),
                'ENPM611_PROJECT_DATA_PATH': 'synthetic-fixture.json',
                'show': False,
            }
            console = io.StringIO()
            with patch('resolution_time_analysis.DataLoader') as loader, \
                 patch('resolution_time_analysis.config.get_parameter', side_effect=settings.get), \
                 contextlib.redirect_stdout(console):
                loader.return_value.get_issues.return_value = issues
                result = ResolutionTimeAnalysis().run()

            self.assertEqual(result['summary']['total'], 4)
            self.assertEqual(result['summary']['open'], 1)
            self.assertEqual(result['summary']['eligible'], 2)
            self.assertEqual(result['summary']['unusable_closure'], 1)
            self.assertEqual(result['closure_exclusions']['missing_closure_event'], 1)
            self.assertEqual(result['dataset'], 'synthetic-fixture.json')

            groups = {row['label']: row for row in result['groups']}
            self.assertEqual(groups['area/solver']['median_days'], 2)
            self.assertEqual(groups['kind/bug']['median_days'], 4)
            self.assertEqual(groups['kind/bug']['eligible_closed'], 2)
            self.assertEqual(groups['kind/bug']['open_issues'], 1)
            self.assertEqual(groups['kind/bug']['total_issues'], 3)
            self.assertAlmostEqual(groups['kind/bug']['open_percent'], 100 / 3)
            self.assertIsNone(groups['kind/feature']['median_days'])

            exported = json.loads((output / 'summary.json').read_text(encoding='utf-8'))
            self.assertEqual(exported, result)
            with (output / 'closure_by_label.csv').open(newline='', encoding='utf-8') as stream:
                csv_rows = {row['label']: row for row in csv.DictReader(stream)}
            self.assertEqual(set(csv_rows), set(groups))
            self.assertEqual(float(csv_rows['kind/bug']['median_days']), 4)
            self.assertEqual(int(csv_rows['kind/bug']['eligible_closed']), 2)
            self.assertAlmostEqual(float(csv_rows['kind/bug']['open_percent']), 100 / 3)
            self.assertEqual(csv_rows['kind/feature']['median_days'], '')

            self.assertIn('kind/bug | 4.00 | 2 | 1 / 3', console.getvalue())
            self.assertIn('kind/feature | N/A | 0 | 0 / 1', console.getvalue())
            for family in ('area', 'kind'):
                png = (output / f'closure_by_{family}.png').read_bytes()
                svg = (output / f'closure_by_{family}.svg').read_text(encoding='utf-8')
                self.assertTrue(png.startswith(b'\x89PNG\r\n\x1a\n'))
                self.assertGreater(len(png), 1000)
                self.assertIn('<svg', svg)
                self.assertIn(f'Time to closure by {family} label', svg)

    def test_save_charts_explains_empty_label_family(self):
        """A missing label family should produce an explicit empty-state chart."""
        kind_only = [{
            'label': 'kind/bug',
            'median_days': 3.5,
            'eligible_closed': 2,
        }]
        with tempfile.TemporaryDirectory() as tempdir:
            output = Path(tempdir)
            save_charts(kind_only, output, show=False)
            area_svg = (output / 'closure_by_area.svg').read_text(encoding='utf-8')
            kind_svg = (output / 'closure_by_kind.svg').read_text(encoding='utf-8')
            self.assertIn('No eligible closed issues in this label family', area_svg)
            self.assertIn('kind/bug', kind_svg)
            self.assertIn('3.5 d (n=2)', kind_svg)

    def test_show_option_requests_display_for_both_charts(self):
        """The interactive option should display each label-family chart once."""
        with tempfile.TemporaryDirectory() as tempdir:
            with patch('matplotlib.pyplot.show') as show:
                save_charts([], Path(tempdir), show=True)
            self.assertEqual(show.call_count, 2)
            for family in ('area', 'kind'):
                self.assertTrue((Path(tempdir) / f'closure_by_{family}.png').is_file())


if __name__ == '__main__':
    unittest.main()
