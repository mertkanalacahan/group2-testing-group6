"""Feature 3: The elapsed hours before a new issue gets its first reply, grouped by issue creation year.

Question: How long does a new issue wait for its first reply from someone other
than its author, and has that changed over the years?
"""
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median
from types import SimpleNamespace
import csv
import json

import config
from data_loader import DataLoader
from issue_utils import get_first_response, utc_date


def _hours_between(start, end):
    return (end - start).total_seconds() / 3600


def _without_author(issue, author):
    """Read-only view of an issue with one author's events removed.

    The shared cached Issue objects are never modified.
    """
    target = author.casefold()
    events = [e for e in issue.events
              if not (isinstance(e.author, str) and e.author.casefold() == target)]
    return SimpleNamespace(creator=issue.creator, created_date=issue.created_date, events=events)


def analyze(issues):
    """Pure calculation separated from loading and plotting for testing.

    Returns a summary of counts, one row per creation year, and the overall
    top first responders. Issues missing a creation date or creator cannot be
    placed or judged, so they are excluded and counted rather than treated as
    unanswered.
    """
    counts = Counter(total=len(issues), eligible=0, answered=0, unanswered=0,
                     missing_created=0, missing_creator=0)
    by_year = defaultdict(list)          # year -> list of (issue, response or None)
    for issue in issues:
        created = utc_date(issue.created_date)
        if created is None:
            counts['missing_created'] += 1
            continue
        if not isinstance(issue.creator, str) or not issue.creator.strip():
            counts['missing_creator'] += 1
            continue
        counts['eligible'] += 1
        response = get_first_response(issue)
        counts['answered' if response else 'unanswered'] += 1
        by_year[created.year].append((issue, response))

    # GitHub usernames ignore capital letters, so "Helper" and "helper" are the
    # same person. Count by a lower-case key and show the first spelling seen.
    display_names = {}

    def person(author):
        key = author.casefold()
        display_names.setdefault(key, author)
        return key

    rows = []
    overall_responders = Counter()
    for year in sorted(by_year):
        pairs = by_year[year]
        hours = [_hours_between(utc_date(i.created_date), utc_date(r.event_date))
                 for i, r in pairs if r is not None]
        responders = Counter(person(r.author) for _, r in pairs if r is not None)
        overall_responders.update(responders)
        top_key, top_count = responders.most_common(1)[0] if responders else (None, 0)
        top = display_names.get(top_key)

        # Sensitivity check: what would the median be if the year's leading
        # first responder had not commented? Recomputed on a filtered view.
        without_top = []
        if top is not None:
            for issue, _ in pairs:
                alt = get_first_response(_without_author(issue, top))
                if alt is not None:
                    without_top.append(_hours_between(utc_date(issue.created_date),
                                                      utc_date(alt.event_date)))
        unanswered = len(pairs) - len(hours)
        rows.append(dict(
            year=year,
            issues=len(pairs),
            answered=len(hours),
            unanswered=unanswered,
            unanswered_percent=100 * unanswered / len(pairs),
            median_hours=median(hours) if hours else None,
            top_responder=top,
            top_responder_share_percent=100 * top_count / len(hours) if hours else None,
            median_hours_without_top=median(without_top) if without_top else None,
        ))

    counts['unanswered_percent'] = (100 * counts['unanswered'] / counts['eligible']
                                    if counts['eligible'] else 0)
    return dict(summary=dict(counts), years=rows,
                top_responders=[(display_names[key], count)
                                for key, count in overall_responders.most_common(5)])


def save_chart(rows, output, show=False):
    import matplotlib
    if not show:
        matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    fig, ax_hours = plt.subplots(figsize=(11, 6))
    if rows:
        years = [r['year'] for r in rows]
        medians = [r['median_hours'] for r in rows]
        unanswered = [r['unanswered_percent'] for r in rows]
        ax_pct = ax_hours.twinx()
        line_hours, = ax_hours.plot(years, medians, marker='o', color='#3478a6',
                                    label='Median hours to first response')
        line_pct, = ax_pct.plot(years, unanswered, marker='s', linestyle='--',
                                color='#d9822b', label='% of issues with no response')
        for year, value in zip(years, medians):
            if value is not None:
                ax_hours.annotate(f'{value:.1f} h', (year, value), textcoords='offset points',
                                  xytext=(14, 8), ha='left', fontsize=9, color='#3478a6',
                                  bbox=dict(boxstyle='round,pad=0.15', fc='white', ec='none', alpha=.85))
        ax_hours.set_xticks(years)
        ax_hours.set_ylim(bottom=0)
        ax_pct.set_ylim(0, max(25, max(unanswered) * 1.3))
        ax_pct.set_ylabel('Issues with no eligible response (%)', color='#d9822b')
        ax_hours.legend(handles=[line_hours, line_pct], loc='upper right')
    else:
        ax_hours.text(.5, .5, 'No issues with a usable creation date and creator',
                      ha='center', va='center', transform=ax_hours.transAxes)
    ax_hours.set_xlabel('Year the issue was created')
    ax_hours.set_ylabel('Median hours to first response', color='#3478a6')
    ax_hours.set_title('Time to first response by issue creation year')
    ax_hours.yaxis.grid(True, alpha=.2)
    ax_hours.set_axisbelow(True)
    fig.text(.01, .01, 'First response = earliest comment by someone other than the issue creator; '
                       'bot accounts ([bot]) excluded. Median among answered issues only. '
                       'The latest year may be partial.', fontsize=8)
    fig.tight_layout(rect=(0, .04, 1, 1))
    for extension in ('png', 'svg'):
        fig.savefig(output / f'first_response_by_year.{extension}', dpi=150)
    if show:
        plt.show()
    plt.close(fig)


def save_dependency_chart(rows, output, show=False):
    """Second chart: median wait with all replies vs without each year's top first responder."""
    import matplotlib
    if not show:
        matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    rows = [r for r in rows if r['median_hours'] is not None]
    fig, ax = plt.subplots(figsize=(11, 6))
    if rows:
        years = [r['year'] for r in rows]
        all_replies = [r['median_hours'] for r in rows]
        without_top = [r['median_hours_without_top'] for r in rows]
        ax.plot(years, all_replies, marker='o', color='#3478a6', label='All replies')
        ax.plot(years, without_top, marker='s', linestyle='--', color='#c0392b',
                label="Without that year's top first responder")
        for year, value in zip(years, all_replies):
            ax.annotate(f'{value:.1f} h', (year, value), textcoords='offset points',
                        xytext=(0, -16), ha='center', fontsize=9, color='#3478a6')
        for year, value in zip(years, without_top):
            if value is not None:
                ax.annotate(f'{value:.1f} h', (year, value), textcoords='offset points',
                            xytext=(0, 9), ha='center', fontsize=9, color='#c0392b',
                            bbox=dict(boxstyle='round,pad=0.15', fc='white', ec='none', alpha=.85))
        ax.set_xticks(years)
        ax.set_xticklabels([f"{r['year']}\n{r['top_responder']} "
                            f"({r['top_responder_share_percent']:.0f}%)" for r in rows], fontsize=9)
        plotted = [v for v in all_replies + without_top if v is not None]
        # A log scale cannot show zero (a reply at the exact moment the issue
        # was opened), so fall back to a normal scale whenever a zero is present.
        use_log = all(v > 0 for v in plotted)
        if use_log:
            ax.set_yscale('log')
            lowest, highest = min(plotted), max(plotted)
            ax.set_ylim(lowest / 2.5, highest * 2.5)
            ticks = [t for t in (0.5, 1, 2, 5, 10, 24, 48, 100, 200, 500, 1000, 2000)
                     if lowest / 2.5 <= t <= highest * 2.5]
            ax.set_yticks(ticks)
            ax.set_yticklabels([f'{t:g} h' for t in ticks])
            ax.minorticks_off()
        else:
            ax.set_ylim(0, max(1, max(plotted)) * 1.3)
        ax.legend(loc='upper right')
    else:
        ax.text(.5, .5, 'No answered issues to compare', ha='center', va='center',
                transform=ax.transAxes)
    ax.set_xlabel("Year the issue was created, with that year's top first responder "
                  '(share of first replies)')
    ax.set_ylabel('Median hours to first response' + (' (log scale)' if ax.get_yscale() == 'log' else ''))
    ax.set_title('How much does the response time depend on one person?')
    ax.yaxis.grid(True, which='major', alpha=.2)
    ax.set_axisbelow(True)
    fig.text(.01, .01, "Dashed line: the same calculation with that person's comments removed. "
                       'It shows dependency, not what would actually have happened without them.',
             fontsize=8)
    fig.tight_layout(rect=(0, .04, 1, 1))
    for extension in ('png', 'svg'):
        fig.savefig(output / f'first_response_without_top_responder.{extension}', dpi=150)
    if show:
        plt.show()
    plt.close(fig)


def _fmt(value, unit=''):
    return 'N/A' if value is None else f'{value:.1f}{unit}'


class ResponseTimeAnalysis:
    def run(self):
        result = analyze(DataLoader().get_issues())
        output = Path(config.get_parameter('output_dir') or 'outputs/response_time')
        output.mkdir(parents=True, exist_ok=True)
        result['dataset'] = str(config.get_parameter('ENPM611_PROJECT_DATA_PATH'))
        (output / 'summary.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        fields = list(result['years'][0]) if result['years'] else ['year']
        with (output / 'first_response_by_year.csv').open('w', newline='', encoding='utf-8') as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(result['years'])

        s = result['summary']
        print('\nQuestion: How long does a new issue wait for its first reply, and is that changing?')
        print('Method: earliest comment by someone other than the issue creator, bots excluded,'
              ' grouped by the year the issue was created.\n')
        print(f"Issues analysed: {s['eligible']} of {s['total']}"
              f" (excluded: {s['missing_created']} missing creation date,"
              f" {s['missing_creator']} missing creator)")
        print(f"Answered: {s['answered']}   No eligible response: {s['unanswered']}"
              f" ({s['unanswered_percent']:.1f}%)\n")
        print('Year | issues | median hours | no response | top first responder (share) | median without them')
        for r in result['years']:
            top = 'N/A' if r['top_responder'] is None else \
                f"{r['top_responder']} ({_fmt(r['top_responder_share_percent'], '%')})"
            print(f"  {r['year']} | {r['issues']} | {_fmt(r['median_hours'])} | "
                  f"{_fmt(r['unanswered_percent'], '%')} | {top} | {_fmt(r['median_hours_without_top'])}")
        if result['top_responders']:
            print('\nMost frequent first responders overall:')
            for name, count in result['top_responders']:
                print(f'  {name}: {count}')
        if len(result['years']) >= 2:
            first, last = result['years'][0], result['years'][-1]
            print(f"\nFinding: median first response went from {_fmt(first['median_hours'], ' h')}"
                  f" in {first['year']} to {_fmt(last['median_hours'], ' h')} in {last['year']}.")
        print('Note: "no eligible response" means none was observed in the dataset,'
              ' not proof that nobody ever replied.')
        show = bool(config.get_parameter('show'))
        save_chart(result['years'], output, show)
        save_dependency_chart(result['years'], output, show)
        print(f'\nSaved table and charts to {output.resolve()}')
        return result


if __name__ == '__main__':
    ResponseTimeAnalysis().run()
