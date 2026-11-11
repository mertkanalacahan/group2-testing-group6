"""Shared bot, UTC date, closure and first-response helpers for Group 6.

Closure helpers validate event history, not snapshot state or closing author.
Callers decide eligibility (including closed state and bot-closure exclusions).
"""
from datetime import datetime, timezone


def is_bot(author):
    """Conservative GitHub bot-name heuristic; not an account-type lookup."""
    return isinstance(author, str) and author.lower().endswith('[bot]')


def utc_date(value):
    """Normalize parsed dates; treat naive timestamps as UTC."""
    if not isinstance(value, datetime):
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def inspect_closure(issue):
    """Latest closure by timestamp, independent of timeline ordering.

    Return (event, reason), with reason None for a usable history.
    Reasons are mutually exclusive, in the order checked below.
    """
    closes = [e for e in issue.events if e.event_type == 'closed']
    if not closes:
        return None, 'missing_closure_event'
    if any(utc_date(e.event_date) is None for e in closes):
        return None, 'undated_closure'
    last = max(closes, key=lambda e: utc_date(e.event_date))
    reopens = [e for e in issue.events if e.event_type == 'reopened']
    if any(utc_date(e.event_date) is None for e in reopens):
        return None, 'undated_reopen'
    if any(utc_date(e.event_date) >= utc_date(last.event_date) for e in reopens):
        return None, 'reopen_at_or_after_closure'
    return last, None


def get_close_event(issue):
    """Preserve the shared interface: return a usable final closure or None."""
    return inspect_closure(issue)[0]


def get_close_date(issue):
    event = get_close_event(issue)
    return utc_date(event.event_date) if event else None


def get_first_response(issue):
    """Return the earliest eligible comment Event, or None.

    Require a known creator and valid creation date. Eligible comments have a
    known non-bot author different from the creator (case-insensitive), a valid
    timestamp, and occur at or after creation. Ignore non-comment events and
    invalid records. Ties retain input order. Returned events are not mutated;
    use utc_date(event.event_date) when calculating elapsed time.

    None means no eligible observed response, not proof nobody ever responded.
    The caller may separately report unusable issue metadata as excluded.
    """
    created = utc_date(issue.created_date)
    creator = issue.creator
    if created is None or not isinstance(creator, str) or not creator.strip():
        return None
    eligible = []
    for event in issue.events:
        if event.event_type != 'commented':
            continue
        author = event.author
        if not isinstance(author, str) or not author.strip():
            continue
        if is_bot(author) or author.casefold() == creator.casefold():
            continue
        date = utc_date(event.event_date)
        if date is not None and date >= created:
            eligible.append(event)
    return min(eligible, key=lambda event: utc_date(event.event_date), default=None)
