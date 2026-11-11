"""Feature 2 tests on synthetic issues; no course dataset or network needed."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace as Obj
import unittest

from contributor_profile_analysis import (analyze, band_authors, normalize_user,
                                          save_chart, CATEGORIES)

ROOT = Path(__file__).resolve().parents[1]


def ev(author, kind='commented', year=2022, date='default'):
    return Obj(event_type=kind, author=author, event_date=(
        datetime(year, 6, 1, tzinfo=timezone.utc) if date == 'default' else date))


def issue(events, labels=()):
    return Obj(events=list(events), labels=list(labels))


class NormalizeUserTests(unittest.TestCase):
    def test_recovers_values_config_decoded(self):
        cases = [('abn', 'abn'), ('  abn ', 'abn'), (12345, '12345'), (True, 'true'),
                 (1.5, '1.5'), (None, None), ('', None), ('   ', None)]
        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(normalize_user(value), expected)


class AnalyzeTests(unittest.TestCase):
    def test_unknown_user_gets_non_bot_suggestions(self):
        data = [issue([ev('a'), ev('a'), ev('b'), ev('app[bot]'), ev('app[bot]'), ev('app[bot]')])]
        result = analyze(data, 'nobody')
        self.assertFalse(result['found'])
        self.assertEqual(result['suggestions'], ['a', 'b'])

    def test_empty_dataset(self):
        result = analyze([], 'abn')
        self.assertFalse(result['found'])
        self.assertEqual(result['suggestions'], [])
        self.assertEqual(result['triage_years'], [])

    def test_passive_missing_author_and_undated_events_excluded(self):
        data = [issue([ev('u'), ev('u', 'mentioned'), ev('u', 'subscribed'),
                       ev('u', 'unsubscribed'), ev(None), ev(' '), ev('u', date=None)])]
        result = analyze(data, 'u')
        self.assertEqual(result['total_events'], 1)
        self.assertEqual(result['excluded'], dict(passive=3, missing_author=2, undated=1))

    def test_case_insensitive_match_uses_most_common_spelling(self):
        data = [issue([ev('Abn'), ev('abn'), ev('abn')])]
        result = analyze(data, 'ABN')
        self.assertTrue(result['found'])
        self.assertEqual(result['user'], 'abn')
        self.assertEqual(result['total_events'], 3)

    def test_pooled_mix_percentages(self):
        data = [issue([ev('u'), ev('u'), ev('u', 'labeled'), ev('u', 'locked')])]
        result = analyze(data, 'u')
        self.assertEqual(result['pooled_counts'],
                         dict(commented=2, labeled=1, unlabeled=0, closed=0, other=1))
        self.assertEqual(result['pooled_percent']['commented'], 50.0)
        self.assertAlmostEqual(sum(result['pooled_percent'].values()), 100.0)

    def test_baseline_excludes_bots_and_requested_user_ties_by_name(self):
        events = [ev('u')] * 5 + [ev('zed'), ev('amy'), ev('ci[bot]'), ev('ci[bot]')]
        result = analyze([issue(events)], 'u')
        self.assertEqual(result['baseline_users'], ['amy', 'zed'])
        self.assertEqual(result['baseline_total'], 2)

    def test_baseline_capped_at_ten(self):
        events = [ev(f'p{i:02}') for i in range(15)] + [ev('u')]
        result = analyze([issue(events)], 'u')
        self.assertEqual(len(result['baseline_users']), 10)

    def test_triage_shares_per_year(self):
        data = [issue([ev('a', 'closed', 2020), ev('a', 'labeled', 2020), ev('a', 'unlabeled', 2020),
                       ev('b', 'closed', 2020), ev('a', 'commented', 2020),
                       ev('ci[bot]', 'closed', 2020), ev('b', 'closed', 2021)])]
        result = analyze(data, 'a')
        y2020, y2021 = result['triage_years']
        self.assertEqual((y2020['year'], y2020['total']), (2020, 4))   # comment and bot ignored
        self.assertEqual(y2020['shares'], {'a': 75.0, 'b': 25.0})
        self.assertEqual((y2020['top_author'], y2020['top_share']), ('a', 75.0))
        self.assertEqual(y2021['shares'], {'b': 100.0})

    def test_user_years_include_zero_activity_years(self):
        data = [issue([ev('u', 'closed', 2020), ev('x', 'closed', 2021), ev('u', 'commented', 2022)])]
        result = analyze(data, 'u')
        by_year = {e['year']: e for e in result['user_years']}
        self.assertEqual(sorted(by_year), [2020, 2021, 2022])
        self.assertEqual(by_year[2021]['total'], 0)
        self.assertEqual(by_year[2021]['percent'], {c: 0.0 for c in CATEGORIES})
        self.assertEqual(by_year[2020]['triage_share'], 100.0)
        self.assertEqual(by_year[2021]['triage_share'], 0.0)

    def test_year_uses_utc(self):
        late = datetime.fromisoformat('2021-01-01T02:00:00+05:00')   # 2020-12-31 in UTC
        result = analyze([issue([ev('u', date=late)])], 'u')
        self.assertEqual([e['year'] for e in result['user_years']], [2020])

    def test_bot_user_profiled_but_not_in_shares_or_baseline(self):
        data = [issue([ev('ci[bot]', 'closed'), ev('ci[bot]'), ev('a', 'closed')])]
        result = analyze(data, 'ci[bot]')
        self.assertTrue(result['found'])
        self.assertTrue(result['user_is_bot'])
        self.assertEqual(result['triage_years'][0]['shares'], {'a': 100.0})
        self.assertEqual(result['baseline_users'], ['a'])

    def test_top_areas_count_issues_once(self):
        data = [issue([ev('u'), ev('u')], ['area/cli', 'area/cli', 'kind/bug']),
                issue([ev('u')], ['area/cli', 'area/docs']),
                issue([ev('other')], ['area/solver'])]
        result = analyze(data, 'u')
        self.assertEqual(result['top_areas'], [('area/cli', 2), ('area/docs', 1)])

    def test_band_authors(self):
        years = [dict(shares={'a': 70.0, 'b': 20.0, 'c': 9.0, 'd': 1.0}),
                 dict(shares={'b': 50.0, 'e': 50.0})]
        self.assertEqual(band_authors(years, 'd'), ['a', 'b', 'e', 'd'])
        self.assertEqual(band_authors(years, 'x[bot]'), ['a', 'b', 'e'])


class ChartTests(unittest.TestCase):
    def test_chart_written_including_zero_year_and_bot(self):
        data = [issue([ev('u', 'closed', 2020), ev('x', 'closed', 2021), ev('u', 'labeled', 2022),
                       ev('ci[bot]', 'commented', 2022)])]
        with tempfile.TemporaryDirectory() as folder:
            for user in ('u', 'ci[bot]'):
                with self.subTest(user=user):
                    path = save_chart(analyze(data, user), Path(folder))
                    self.assertTrue(path.exists() and path.stat().st_size > 0)
                    self.assertTrue(path.name.startswith('contributor_profile_'))


class RunTests(unittest.TestCase):
    """Runs the class end to end in a subprocess with a temporary JSON dataset."""

    def run_feature(self, user, output_dir=True):
        records = [dict(state='closed', created_date='2022-01-01T00:00:00Z', labels=['area/cli'],
                        events=[dict(event_type='closed', author='abn', event_date='2022-02-01T00:00:00Z'),
                                dict(event_type='commented', author='dev', event_date='2022-01-02T00:00:00Z')])]
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'fixture.json'
            source.write_text(json.dumps(records), encoding='utf-8')
            env = os.environ.copy()
            env.update(ENPM611_PROJECT_DATA_PATH=str(source), MPLBACKEND='Agg', PYTHONPATH=str(ROOT))
            for name in ('show', 'user', 'output_dir'):
                env.pop(name, None)
            if output_dir:
                env['output_dir'] = str(Path(folder) / 'out')
            if user is not None:
                env['user'] = user
            proc = subprocess.run(
                [sys.executable, '-c',
                 'from contributor_profile_analysis import ContributorProfileAnalysis as C; C().run()'],
                # Without --output-dir, run in the temp folder so the default
                # outputs/contributor_profile/ folder is not created in the repo.
                cwd=ROOT if output_dir else folder, env=env, capture_output=True,
                text=True, timeout=90)
            charts = list((Path(folder) / 'out').glob('*.png')) + list(
                (Path(folder) / 'outputs' / 'contributor_profile').glob('*.png'))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return proc.stdout, charts

    def test_known_user_prints_report_and_saves_chart(self):
        out, charts = self.run_feature('ABN')
        self.assertIn('Contributor profile: abn', out)
        self.assertIn('area/cli: 1', out)
        self.assertEqual(len(charts), 1)

    def test_default_output_folder_without_output_dir(self):
        out, charts = self.run_feature('abn', output_dir=False)
        self.assertIn('outputs/contributor_profile/contributor_profile_abn.png', out.replace('\\', '/'))
        self.assertEqual(len(charts), 1)

    def test_missing_user_prints_usage(self):
        out, charts = self.run_feature(None)
        self.assertIn('Usage: python run.py --feature 2 --user', out)
        self.assertEqual(charts, [])

    def test_unknown_user_suggests_contributors(self):
        out, charts = self.run_feature('nobody')
        self.assertIn("No activity found for 'nobody'", out)
        self.assertIn('abn', out)
        self.assertEqual(charts, [])


if __name__ == '__main__':
    unittest.main()
