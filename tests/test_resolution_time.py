import unittest
from model import Issue
from resolution_time_analysis import analyze
from issue_utils import get_close_date, is_bot, inspect_closure


def issue(state='closed', created='2024-01-01T00:00:00Z', events=None, labels=None):
    return Issue(dict(state=state, created_date=created, labels=['area/solver'] if labels is None else labels,
                      events=events if events is not None else [event('2024-01-03T00:00:00Z')]))


def event(date, author='human', kind='closed'):
    return dict(event_type=kind, event_date=date, author=author)


class ClosureTests(unittest.TestCase):
    def test_median_and_open_denominator(self):
        result = analyze([issue(), issue(events=[event('2024-01-05T00:00:00Z')]), issue(state='open')])
        self.assertEqual(result['groups'][0]['median_days'], 3)
        self.assertAlmostEqual(result['groups'][0]['open_percent'], 100 / 3)

    def test_final_closure_unsorted_and_reopen(self):
        obj = issue(events=[event('2024-01-10T00:00:00Z'), event('2024-01-02T00:00:00Z'),
                            event('2024-01-03T00:00:00Z', kind='reopened')])
        self.assertEqual(get_close_date(obj).day, 10)
        self.assertEqual(analyze([obj])['groups'][0]['median_days'], 9)

    def test_latest_bot_closure_not_earlier_human(self):
        obj = issue(events=[event('2024-01-03T00:00:00Z'), event('2024-01-05T00:00:00Z', 'app[bot]')])
        self.assertEqual(analyze([obj])['summary']['bot_closure'], 1)
        self.assertTrue(is_bot('APP[BOT]'))
        self.assertFalse(is_bot('robotics-user'))

    def test_exclusions(self):
        cases = [issue(created=None), issue(events=[]), issue(events=[event(None)]),
                 issue(events=[event('2023-12-31T00:00:00Z')]),
                 issue(events=[event('2024-01-02T00:00:00Z', None)])]
        s = analyze(cases)['summary']
        self.assertEqual((s['missing_created'], s['unusable_closure'], s['negative_duration'], s['missing_closer']), (1, 2, 1, 1))
        self.assertEqual(s['eligible'], 0)

    def test_multilabel_deduplication(self):
        r = analyze([issue(labels=['area/solver', 'area/solver', 'kind/bug'])])
        self.assertEqual(len(r['groups']), 2)
        self.assertTrue(all(g['eligible_closed'] == 1 for g in r['groups']))

    def test_offsets_and_zero_duration(self):
        r = analyze([issue(created='2024-01-01T01:00:00+01:00', events=[event('2024-01-01T00:00:00Z')])])
        self.assertEqual(r['groups'][0]['median_days'], 0)

    def test_inconsistent_reopen_excluded(self):
        obj = issue(events=[event('2024-01-02T00:00:00Z'), event('2024-01-03T00:00:00Z', kind='reopened')])
        self.assertIsNone(get_close_date(obj))

    def test_empty_and_unlabelled(self):
        self.assertEqual(analyze([])['groups'], [])
        obj = issue(); obj.labels = []
        self.assertEqual(analyze([obj])['summary']['eligible_without_target_labels'], 1)

    def test_one_second_boundaries(self):
        for timestamp, eligible, negative, days in [
            ('2023-12-31T23:59:59Z', 0, 1, None),
            ('2024-01-01T00:00:00Z', 1, 0, 0),
            ('2024-01-01T00:00:01Z', 1, 0, 1/86400),
        ]:
            with self.subTest(timestamp=timestamp):
                result = analyze([issue(events=[event(timestamp)])])
                self.assertEqual(result['summary']['eligible'], eligible)
                self.assertEqual(result['summary']['negative_duration'], negative)
                actual = result['groups'][0]['median_days']
                if days is None:
                    self.assertIsNone(actual)
                else:
                    self.assertAlmostEqual(actual, days)

    def test_open_issue_with_old_closure(self):
        result = analyze([issue(state='open')])
        self.assertEqual(result['summary']['open'], 1)
        self.assertEqual(result['summary']['eligible'], 0)
        self.assertIsNone(result['groups'][0]['median_days'])
        self.assertEqual(result['groups'][0]['open_percent'], 100)

    def test_odd_median_resists_outlier(self):
        from datetime import datetime, timedelta, timezone
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        rows = [issue(events=[event((start+timedelta(days=n)).isoformat())]) for n in (2, 4, 90)]
        self.assertEqual(analyze(rows)['groups'][0]['median_days'], 4)

    def test_closure_reason_partition(self):
        cases = [([], 'missing_closure_event'),
                 ([event(None)], 'undated_closure'),
                 ([event('2024-01-03T00:00:00Z'), event(None, kind='reopened')], 'undated_reopen'),
                 ([event('2024-01-03T00:00:00Z'), event('2024-01-03T00:00:00Z', kind='reopened')], 'reopen_at_or_after_closure')]
        for events, reason in cases:
            with self.subTest(reason=reason):
                obj = issue(events=events)
                self.assertEqual(inspect_closure(obj), (None, reason))
                result = analyze([obj])
                self.assertEqual(result['closure_exclusions'][reason], 1)
                self.assertEqual(sum(result['closure_exclusions'].values()), result['summary']['unusable_closure'])

    def test_naive_dates_assumed_utc(self):
        obj = issue(created='2024-01-01T00:00:00', events=[event('2024-01-02T00:00:00Z')])
        self.assertEqual(analyze([obj])['groups'][0]['median_days'], 1)

    def test_unknown_state_and_invalid_labels(self):
        obj = issue(labels=['kind/bug', None, 3, 'unrelated'])
        obj.state = 'unexpected'
        result = analyze([obj])
        self.assertEqual(result['summary']['unknown_state'], 1)
        self.assertEqual([r['label'] for r in result['groups']], ['kind/bug'])


if __name__ == '__main__':
    unittest.main()
