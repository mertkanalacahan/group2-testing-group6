"""Team 2 white-box tests for Team 6's Feature 2, contributor_profile_analysis.py.

Self-contained: builds small synthetic datasets, so no course data file is needed.
Run from the project root with:  python -m unittest discover
"""
import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import matplotlib
matplotlib.use('Agg')  # never open chart windows during tests

import config
import contributor_profile_analysis as profile
from model import Issue


def make_issue(number=1, creator='alice', state='closed',
               created='2024-01-01T00:00:00Z', labels=None, events=None):
    """Build a real Issue; events are (event_type, event_date, author[, label]) tuples."""
    rows = []
    for event in events or []:
        row = dict(event_type=event[0], event_date=event[1], author=event[2])
        if len(event) > 3:
            row['label'] = event[3]
        rows.append(row)
    return Issue(dict(number=number, creator=creator, state=state,
                      title=f'Issue {number}', labels=list(labels or []),
                      url=f'https://github.com/python-poetry/poetry/issues/{number}',
                      created_date=created, events=rows))


def capture_stdout(function, *args, **kwargs):
    """Run function and return (its return value, everything it printed)."""
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        value = function(*args, **kwargs)
    return value, buffer.getvalue()


class IsolatedTestCase:
    """Mixin: config.set_parameter writes os.environ, so restore it after each test."""

    def isolate(self):
        env = patch.dict(os.environ)
        env.start()
        self.addCleanup(env.stop)
        for name in ('user', 'label', 'show', 'output_dir'):
            os.environ.pop(name, None)
        saved_config = config._config
        self.addCleanup(setattr, config, '_config', saved_config)

    def temp_dir(self):
        folder = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(folder.cleanup)
        return folder.name


def dataset():
    """alice triages, bob comments, a bot labels; plus excluded events."""
    return [
        make_issue(number=1, creator='zoe', labels=['area/cli', 'kind/bug'], events=[
            ('labeled', '2023-03-01T00:00:00Z', 'alice', 'kind/bug'),
            ('labeled', '2023-03-02T00:00:00Z', 'alice', 'area/cli'),
            ('commented', '2023-03-03T00:00:00Z', 'Alice'),          # other spelling
            ('commented', '2023-03-04T00:00:00Z', 'bob'),
            ('labeled', '2023-03-05T00:00:00Z', 'bob', 'kind/bug'),
            ('labeled', '2023-03-06T00:00:00Z', 'github-actions[bot]', 'stale'),
            ('mentioned', '2023-03-07T00:00:00Z', 'carol'),          # passive
            ('commented', None, 'dave'),                              # undated
            ('commented', '2023-03-08T00:00:00Z', None),             # no author
        ]),
        make_issue(number=2, creator='zoe', labels=['area/docs'], events=[
            ('closed', '2024-05-01T00:00:00Z', 'alice'),
            ('assigned', '2024-05-02T00:00:00Z', 'alice'),
            ('commented', '2024-05-03T00:00:00Z', 'bob'),
        ]),
    ]


class HelperTests(IsolatedTestCase, unittest.TestCase):
    def setUp(self):
        self.isolate()
        config._config = {}

    def test_normalize_user(self):
        self.assertIsNone(profile.normalize_user(None))
        self.assertIsNone(profile.normalize_user('   '))
        self.assertEqual(profile.normalize_user('  bob '), 'bob')
        self.assertEqual(profile.normalize_user(12345), '12345')
        self.assertEqual(profile.normalize_user(True), 'true')

    def test_numeric_username_from_command_line_is_recovered(self):
        config.set_parameter('user', '12345')
        self.assertEqual(profile.ContributorProfileAnalysis().user, '12345')

    def test_exponent_like_username_from_command_line_is_recovered(self):
        # "1e3" is a valid GitHub username; it must reach the analysis unchanged.
        config.set_parameter('user', '1e3')
        self.assertEqual(profile.ContributorProfileAnalysis().user, '1e3')

    def test_category_and_percentages(self):
        self.assertEqual(profile.category('assigned'), 'other')
        self.assertEqual(profile.category('closed'), 'closed')
        self.assertEqual(profile.percentages({'commented': 1, 'closed': 3})['closed'], 75.0)
        self.assertEqual(set(profile.percentages({}).values()), {0.0})

    def test_safe_name(self):
        self.assertEqual(profile.safe_name('github-actions[bot]'), 'github-actions_bot_')
        self.assertEqual(profile.safe_name(''), 'user')

    def test_band_authors(self):
        years = [dict(shares={'a': 60.0, 'b': 30.0, 'c': 6.0, 'd': 4.0})]
        self.assertEqual(profile.band_authors(years, 'd'), ['a', 'b', 'd'])
        self.assertEqual(profile.band_authors(years, 'x[bot]'), ['a', 'b'])
        self.assertEqual(profile.band_authors(years, None), ['a', 'b'])


class AnalyzeTests(unittest.TestCase):
    def setUp(self):
        self.result = profile.analyze(dataset(), 'ALICE')

    def test_user_is_matched_case_insensitively_to_most_common_spelling(self):
        self.assertTrue(self.result['found'])
        self.assertEqual(self.result['user'], 'alice')
        self.assertFalse(self.result['user_is_bot'])

    def test_excluded_events_are_counted(self):
        self.assertEqual(self.result['excluded'], dict(passive=1, missing_author=1, undated=1))

    def test_pooled_mix_for_the_user(self):
        self.assertEqual(self.result['total_events'], 5)
        self.assertEqual(self.result['pooled_counts'],
                         dict(commented=1, labeled=2, unlabeled=0, closed=1, other=1))
        self.assertEqual(self.result['pooled_percent']['labeled'], 40.0)

    def test_triage_shares_exclude_bots(self):
        first = self.result['triage_years'][0]
        self.assertEqual(first['year'], 2023)
        self.assertEqual(first['total'], 3)
        self.assertEqual(first['top_author'], 'alice')
        self.assertNotIn('github-actions[bot]', first['shares'])
        self.assertAlmostEqual(first['top_share'], 200 / 3)

    def test_yearly_rows_and_triage_share(self):
        years = {row['year']: row for row in self.result['user_years']}
        self.assertEqual(years[2023]['total'], 3)
        self.assertAlmostEqual(years[2023]['triage_share'], 200 / 3)
        self.assertEqual(years[2024]['triage_share'], 100.0)

    def test_baseline_and_suggestions_exclude_the_user_and_bots(self):
        self.assertEqual(self.result['baseline_users'], ['bob'])
        self.assertEqual(self.result['baseline_total'], 3)
        self.assertNotIn('github-actions[bot]', self.result['suggestions'])
        self.assertEqual(self.result['suggestions'][0], 'alice')

    def test_top_areas_count_distinct_issues(self):
        self.assertEqual(self.result['top_areas'], [('area/cli', 1), ('area/docs', 1)])

    def test_unknown_user_returns_only_project_data(self):
        result = profile.analyze(dataset(), 'nobody')
        self.assertFalse(result['found'])
        self.assertNotIn('total_events', result)
        self.assertEqual(len(result['triage_years']), 2)

    def test_bot_user_is_profiled_but_flagged(self):
        result = profile.analyze(dataset(), 'github-actions[bot]')
        self.assertTrue(result['found'])
        self.assertTrue(result['user_is_bot'])


class OutputTests(IsolatedTestCase, unittest.TestCase):
    def setUp(self):
        self.isolate()
        config._config = {}

    def test_report_prints_question_and_tables(self):
        _, printed = capture_stdout(profile.print_report, profile.analyze(dataset(), 'alice'))
        self.assertIn('Question: what does this contributor do', printed)
        self.assertIn('Baseline: bob', printed)
        self.assertIn('area/cli: 1', printed)
        self.assertIn('top triager held 67% of triage actions in 2023', printed)

    def test_chart_is_saved_with_a_safe_file_name(self):
        result = profile.analyze(dataset(), 'github-actions[bot]')
        path = profile.save_chart(result, Path(self.temp_dir()))
        self.assertEqual(path.name, 'contributor_profile_github-actions_bot_.png')
        self.assertGreater(path.stat().st_size, 0)

    def test_run_without_user_prints_usage(self):
        analysis = profile.ContributorProfileAnalysis()
        result, printed = capture_stdout(analysis.run)
        self.assertIsNone(result)
        self.assertIn('Feature 2 needs a contributor', printed)

    def test_run_with_unknown_user_suggests_contributors(self):
        config.set_parameter('user', 'nobody')
        with patch('contributor_profile_analysis.DataLoader') as loader:
            loader.return_value.get_issues.return_value = dataset()
            result, printed = capture_stdout(profile.ContributorProfileAnalysis().run)
        self.assertFalse(result['found'])
        self.assertIn("No activity found for 'nobody'", printed)
        self.assertIn('Try one of the most active contributors: alice, bob', printed)

    def test_run_with_known_user_saves_chart(self):
        output = self.temp_dir()
        config.set_parameter('user', 'bob')
        config.set_parameter('output_dir', output)
        with patch('contributor_profile_analysis.DataLoader') as loader:
            loader.return_value.get_issues.return_value = dataset()
            result, printed = capture_stdout(profile.ContributorProfileAnalysis().run)
        self.assertTrue(result['found'])
        self.assertTrue(os.path.isfile(os.path.join(output, 'contributor_profile_bob.png')))
        self.assertIn('Saved chart to', printed)


if __name__ == '__main__':
    unittest.main()