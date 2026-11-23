"""Independent Team 2 tests for Group 6's Feature 2"""

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import config
import contributor_profile_analysis as profile
import data_loader
import run
from model import Issue

def event(event_type, author, event_date, label=None):
    """Construct one timeline event in the dataset's JSON format."""
    return {'event_type': event_type, 'author': author,
            'event_date': event_date, 'label': label}

def make_issue(number, labels, events, creator='zoe'):
    """Construct a controlled issue with known labels and timeline events."""
    return Issue({
        'number': number,
        'creator': creator,
        'state': 'closed',
        'created_date': '2023-01-01T00:00:00Z',
        'labels': labels,
        'events': events,
    })

def known_issues():
    """alice triages and comments, bob comments, a bot labels; plus excluded events."""
    return [
        make_issue(1, ['area/cli', 'kind/bug'], [
            event('labeled', 'alice', '2023-03-01T00:00:00Z', 'kind/bug'),
            event('labeled', 'alice', '2023-03-02T00:00:00Z', 'area/cli'),
            event('commented', 'Alice', '2023-03-03T00:00:00Z'),
            event('commented', 'bob', '2023-03-04T00:00:00Z'),
            event('labeled', 'bob', '2023-03-05T00:00:00Z', 'kind/bug'),
            event('labeled', 'github-actions[bot]', '2023-03-06T00:00:00Z', 'stale'),
            event('mentioned', 'carol', '2023-03-07T00:00:00Z'),
            event('commented', 'dave', None),
            event('commented', None, '2023-03-08T00:00:00Z'),
        ]),
        make_issue(2, ['area/docs'], [
            event('closed', 'alice', '2024-05-01T00:00:00Z'),
            event('assigned', 'alice', '2024-05-02T00:00:00Z'),
            event('commented', 'bob', '2024-05-03T00:00:00Z'),
        ]),
    ]

class Group2ContributorProfileTests(unittest.TestCase):
    def setUp(self):
        self.result = profile.analyze(known_issues(), 'ALICE')

    def test_user_is_matched_case_insensitively_and_activity_mix_is_counted(self):
        """Any capitalisation finds the user under their most common spelling."""
        self.assertTrue(self.result['found'])
        self.assertEqual(self.result['user'], 'alice')
        self.assertFalse(self.result['user_is_bot'])
        self.assertEqual(self.result['total_events'], 5)
        self.assertEqual(self.result['pooled_counts'],
                         {'commented': 1, 'labeled': 2, 'unlabeled': 0,
                          'closed': 1, 'other': 1})
        self.assertEqual(self.result['pooled_percent']['labeled'], 40.0)

    def test_passive_undated_and_anonymous_events_are_excluded(self):
        """Events that say nothing about a person's work are counted, not profiled."""
        self.assertEqual(self.result['excluded'],
                         {'passive': 1, 'missing_author': 1, 'undated': 1})

    def test_triage_shares_ignore_bots_and_track_each_year(self):
        """Yearly triage shares exclude bots and include the user's own share."""
        first = self.result['triage_years'][0]
        self.assertEqual(first['year'], 2023)
        self.assertEqual(first['total'], 3)
        self.assertEqual(first['top_author'], 'alice')
        self.assertAlmostEqual(first['top_share'], 200 / 3)
        self.assertNotIn('github-actions[bot]', first['shares'])
        years = {row['year']: row for row in self.result['user_years']}
        self.assertEqual(years[2023]['total'], 3)
        self.assertAlmostEqual(years[2023]['triage_share'], 200 / 3)
        self.assertEqual(years[2024]['triage_share'], 100.0)

    def test_baseline_and_suggestions_exclude_the_user_and_bots(self):
        """The comparison group is every other human; bots are never suggested."""
        self.assertEqual(self.result['baseline_users'], ['bob'])
        self.assertEqual(self.result['baseline_total'], 3)
        self.assertEqual(self.result['suggestions'][0], 'alice')
        self.assertNotIn('github-actions[bot]', self.result['suggestions'])

    def test_top_areas_count_each_issue_once(self):
        """Area labels are counted per issue touched, not per event."""
        self.assertEqual(self.result['top_areas'], [('area/cli', 1), ('area/docs', 1)])

    def test_unknown_user_returns_only_project_data(self):
        """An unknown user gets project-wide data but no personal profile."""
        result = profile.analyze(known_issues(), 'nobody')
        self.assertFalse(result['found'])
        self.assertNotIn('total_events', result)
        self.assertEqual(len(result['triage_years']), 2)

    def test_bot_user_is_profiled_but_flagged(self):
        """A bot account can be inspected, but is marked as a bot."""
        result = profile.analyze(known_issues(), 'github-actions[bot]')
        self.assertTrue(result['found'])
        self.assertTrue(result['user_is_bot'])

    def test_normalize_user_recovers_typed_strings(self):
        """Blank input means no user; numbers and booleans become their typed text."""
        self.assertIsNone(profile.normalize_user(None))
        self.assertIsNone(profile.normalize_user('   '))
        self.assertEqual(profile.normalize_user('  bob '), 'bob')
        self.assertEqual(profile.normalize_user(12345), '12345')
        self.assertEqual(profile.normalize_user(True), 'true')

    def test_helpers_categorise_events_and_build_safe_names(self):
        """Event categories, percentage maths, and chart file names are predictable."""
        self.assertEqual(profile.category('assigned'), 'other')
        self.assertEqual(profile.category('closed'), 'closed')
        self.assertEqual(profile.percentages({'commented': 1, 'closed': 3})['closed'], 75.0)
        self.assertEqual(set(profile.percentages({}).values()), {0.0})
        self.assertEqual(profile.safe_name('github-actions[bot]'), 'github-actions_bot_')
        self.assertEqual(profile.safe_name(''), 'user')

    def test_band_authors_keeps_leaders_and_the_profiled_human(self):
        """Triagers above 5% always appear; the user is added only if human."""
        years = [{'shares': {'a': 60.0, 'b': 30.0, 'c': 6.0, 'd': 4.0}}]
        self.assertEqual(profile.band_authors(years, 'd'), ['a', 'b', 'd'])
        self.assertEqual(profile.band_authors(years, 'x[bot]'), ['a', 'b'])
        self.assertEqual(profile.band_authors(years, None), ['a', 'b'])

    def test_report_prints_question_baseline_and_areas(self):
        """The console report states its question and the computed comparisons."""
        console = io.StringIO()
        with contextlib.redirect_stdout(console):
            profile.print_report(self.result)
        self.assertIn('Question: what does this contributor do', console.getvalue())
        self.assertIn('Baseline: bob', console.getvalue())
        self.assertIn('area/cli: 1', console.getvalue())
        self.assertIn('top triager held 67% of triage actions in 2023', console.getvalue())

    def test_chart_is_saved_with_a_safe_file_name(self):
        """Usernames with symbols still produce a valid PNG file name."""
        result = profile.analyze(known_issues(), 'github-actions[bot]')
        with tempfile.TemporaryDirectory() as tempdir:
            path = profile.save_chart(result, Path(tempdir))
            self.assertEqual(path.name, 'contributor_profile_github-actions_bot_.png')
            self.assertTrue(path.read_bytes().startswith(b'\x89PNG\r\n\x1a\n'))

    def test_show_option_requests_display_of_the_chart(self):
        """The interactive option should display the chart once and still save it."""
        with (
            tempfile.TemporaryDirectory() as tempdir,
            patch('matplotlib.pyplot.show') as show,
        ):
            path = profile.save_chart(self.result, Path(tempdir), show=True)
            self.assertEqual(show.call_count, 1)
            self.assertTrue(path.is_file())

class Group2ContributorProfileCLIIntegrationTests(unittest.TestCase):
    def run_command(self, records, *options):
        """Use the real argument parser, config, JSON loader, analysis, and chart export."""
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / 'issues.json'
            output = Path(temporary) / 'results'
            source.write_text(json.dumps(records), encoding='utf-8')
            buffer = io.StringIO()
            arguments = ['run.py', '--feature', '2', '--output-dir', str(output), *options]
            with (
                patch.dict(os.environ, {'ENPM611_PROJECT_DATA_PATH': str(source),
                                        'MPLBACKEND': 'Agg'}),
                patch.object(config, '_config', None),
                patch.object(data_loader, '_ISSUES', None),
                patch('sys.argv', arguments),
                contextlib.redirect_stdout(buffer),
            ):
                os.environ.pop('user', None)
                run.main()
            charts = sorted(path.name for path in output.glob('*.png'))
        return buffer.getvalue(), charts

    def records_with(self, username):
        """A JSON dataset in which `username` commented on and labeled one issue."""
        return [{'number': 1, 'creator': 'zoe', 'state': 'open',
                 'created_date': '2023-01-01T00:00:00Z', 'labels': ['area/cli'],
                 'events': [event('commented', username, '2023-01-02T00:00:00Z'),
                            event('labeled', username, '2023-01-03T00:00:00Z', 'area/cli')]}]

    def test_command_profiles_a_known_user_and_saves_the_chart(self):
        """A real command loads JSON, prints the profile, and exports the chart."""
        console, charts = self.run_command(self.records_with('bob'), '--user', 'bob')
        self.assertIn('Loaded 1 issues from', console)
        self.assertIn('Saved chart to', console)
        self.assertEqual(charts, ['contributor_profile_bob.png'])

    def test_command_suggests_contributors_for_an_unknown_user(self):
        """An unknown user gets the most active contributors as suggestions."""
        console, charts = self.run_command(self.records_with('bob'), '--user', 'nobody')
        self.assertIn("No activity found for 'nobody'", console)
        self.assertIn('Try one of the most active contributors: bob', console)
        self.assertEqual(charts, [])

    def test_command_without_a_user_explains_the_required_option(self):
        """Feature 2 without --user prints usage instead of failing."""
        console, charts = self.run_command(self.records_with('bob'))
        self.assertIn('Feature 2 needs a contributor', console)
        self.assertEqual(charts, [])

    def test_numeric_username_is_looked_up_as_typed(self):
        """A digits-only GitHub username must reach the analysis unchanged."""
        console, charts = self.run_command(self.records_with('12345'), '--user', '12345')
        self.assertNotIn('No activity found', console)
        self.assertEqual(charts, ['contributor_profile_12345.png'])

    def test_exponent_like_username_is_looked_up_as_typed(self):
        """A valid GitHub username such as 1e3 must not be turned into a number."""
        console, charts = self.run_command(self.records_with('1e3'), '--user', '1e3')
        self.assertNotIn("No activity found for '1000.0'", console)
        self.assertEqual(charts, ['contributor_profile_1e3.png'])

if __name__ == "__main__":
    unittest.main()