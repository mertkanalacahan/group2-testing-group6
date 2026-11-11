"""Shared helper contracts, independent of any analysis module or dataset."""
from datetime import datetime, timezone
from types import SimpleNamespace as Obj
import unittest
from issue_utils import (is_bot, utc_date, inspect_closure, get_close_event,
                         get_close_date, get_first_response)


def event(day=2, author='helper', kind='commented', date='default'):
    return Obj(event_type=kind, author=author, event_date=(
        datetime(2024, 1, day, tzinfo=timezone.utc) if date == 'default' else date))


def issue(events=(), creator='creator', created='default'):
    return Obj(events=list(events), creator=creator, created_date=(
        datetime(2024, 1, 1, tzinfo=timezone.utc) if created == 'default' else created))


class SharedHelperTests(unittest.TestCase):
    def test_bot_heuristic(self):
        for name, expected in [('APP[BOT]', True), ('robotics', False), (None, False), ('', False)]:
            with self.subTest(name=name): self.assertEqual(is_bot(name), expected)

    def test_utc_normalization(self):
        self.assertIsNone(utc_date('not parsed'))
        self.assertEqual(utc_date(datetime(2024, 1, 1)).tzinfo, timezone.utc)
        self.assertEqual(utc_date(datetime.fromisoformat('2024-01-01T01:00:00+01:00')).hour, 0)

    def test_final_closure_unsorted(self):
        last = event(5, kind='closed')
        obj = issue([last, event(2, kind='closed'), event(3, kind='reopened')])
        self.assertEqual(inspect_closure(obj), (last, None))
        self.assertIs(get_close_event(obj), last)
        self.assertEqual(get_close_date(obj), last.event_date)

    def test_closure_exclusion_reasons(self):
        cases = [([], 'missing_closure_event'),
                 ([event(kind='closed', date=None)], 'undated_closure'),
                 ([event(kind='closed'), event(kind='reopened', date=None)], 'undated_reopen'),
                 ([event(kind='closed'), event(kind='reopened')], 'reopen_at_or_after_closure')]
        for events, reason in cases:
            with self.subTest(reason=reason):
                obj = issue(events)
                self.assertEqual(inspect_closure(obj), (None, reason))
                self.assertIsNone(get_close_date(obj))

    def test_response_earliest_not_input_order(self):
        first = event(2)
        self.assertIs(get_first_response(issue([event(4), first, event(3)])), first)

    def test_response_filters_author_type_and_date(self):
        valid = event(4)
        events = [event(author='Creator'), event(author='app[bot]'),
                  event(kind='closed'), event(author=None), event(author=' '),
                  event(date=None), event(date=datetime(2023, 12, 31, tzinfo=timezone.utc)), valid]
        self.assertIs(get_first_response(issue(events)), valid)

    def test_response_at_creation_is_valid(self):
        obj = event(date=datetime(2024, 1, 1))
        self.assertIs(get_first_response(issue([obj])), obj)
        self.assertIsNone(obj.event_date.tzinfo)  # original object is unchanged

    def test_no_eligible_response(self):
        self.assertIsNone(get_first_response(issue()))
        self.assertIsNone(get_first_response(issue([event(author='creator')])))

    def test_missing_issue_metadata(self):
        for creator, created in [(None, 'default'), (' ', 'default'), ('creator', None)]:
            with self.subTest(creator=creator, created=created):
                self.assertIsNone(get_first_response(issue([event()], creator, created)))

    def test_equal_dates_keep_first_event(self):
        first, second = event(author='one'), event(author='two')
        self.assertIs(get_first_response(issue([first, second])), first)


if __name__ == '__main__':
    unittest.main()
