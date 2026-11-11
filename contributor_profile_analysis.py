"""Feature 2: how a contributor's role changed over time.

Question: What does a given contributor do on Poetry's issues, how has that
changed year by year, and where do they fit in the history of who did the
project's triage work?

Run: python run.py --feature 2 --user <github-username>
"""
from collections import Counter, defaultdict
from pathlib import Path
import json

import config
from data_loader import DataLoader
from issue_utils import is_bot, utc_date

CATEGORIES = ('commented', 'labeled', 'unlabeled', 'closed', 'other')
# On GitHub these record the person who was @-mentioned or auto-subscribed,
# not an action taken by that person, so they are not counted as activity.
PASSIVE_EVENTS = frozenset({'mentioned', 'subscribed', 'unsubscribed'})
# Actions that shape an issue's lifecycle; used for the per-year share chart.
TRIAGE_EVENTS = frozenset({'labeled', 'unlabeled', 'closed'})
BASELINE_SIZE = 10
SUGGESTION_COUNT = 5
LEADER_MIN_SHARE = 10.0   # % of a year's triage actions to get a named band
LEADER_PER_YEAR = 3       # only a year's top N can qualify for a named band
DEFAULT_OUTPUT_DIR = 'outputs/contributor_profile'


def normalize_user(value):
    """Recover the username string the user typed.

    config.get_parameter() JSON-decodes values, so '--user 12345' arrives as
    the int 12345 and '--user true' as True. Re-encode non-strings so they can
    be compared with author names. '--user null' cannot be told apart from a
    missing argument and is treated as missing.
    """
    if value is None:
        return None
    text = value if isinstance(value, str) else json.dumps(value)
    text = text.strip()
    return text or None


def category(event_type):
    return event_type if event_type in CATEGORIES else 'other'


def percentages(counts):
    total = sum(counts.values())
    return {name: (100 * counts.get(name, 0) / total if total else 0.0) for name in CATEGORIES}


def _ranked(counter):
    """Deterministic ranking: highest count first, then name."""
    return sorted(counter.items(), key=lambda item: (-item[1], item[0]))


def analyze(issues, requested_user):
    """Pure calculation, separated from loading, printing and plotting.

    Only active events count: events with a known author and a valid date,
    excluding passive event types. Username matching is case-insensitive,
    as GitHub usernames are.
    """
    excluded = Counter(passive=0, missing_author=0, undated=0)
    active = []                      # (author, year, category, event_type, issue)
    spellings = defaultdict(Counter)  # casefolded name -> spellings seen
    for issue in issues:
        for event in issue.events:
            if event.event_type in PASSIVE_EVENTS:
                excluded['passive'] += 1
                continue
            author = event.author
            if not isinstance(author, str) or not author.strip():
                excluded['missing_author'] += 1
                continue
            date = utc_date(event.event_date)
            if date is None:
                excluded['undated'] += 1
                continue
            spellings[author.casefold()][author] += 1
            active.append((author, date.year, category(event.event_type), event.event_type, issue))

    canonical = {key: _ranked(names)[0][0] for key, names in spellings.items()}
    key = requested_user.casefold() if requested_user else None
    user = canonical.get(key, requested_user)

    per_author = Counter()
    for author, *_ in active:
        per_author[canonical[author.casefold()]] += 1
    humans = Counter({a: n for a, n in per_author.items() if not is_bot(a)})

    result = dict(requested_user=requested_user, user=user, user_is_bot=is_bot(user),
                  found=key in canonical, excluded=dict(excluded),
                  suggestions=[a for a, _ in _ranked(humans)[:SUGGESTION_COUNT]])

    # Project-wide: who did each year's triage actions (bots excluded).
    triage = defaultdict(Counter)
    for author, year, _, event_type, _ in active:
        name = canonical[author.casefold()]
        if event_type in TRIAGE_EVENTS and not is_bot(name):
            triage[year][name] += 1
    years = sorted(triage)
    triage_years = []
    for year in years:
        total = sum(triage[year].values())
        ranked = _ranked(triage[year])
        triage_years.append(dict(
            year=year, total=total,
            shares={a: 100 * n / total for a, n in ranked},
            top_author=ranked[0][0], top_share=100 * ranked[0][1] / total))
    result['triage_years'] = triage_years

    if not result['found']:
        return result

    # The requested user: pooled mix, yearly mix, areas worked on.
    pooled, yearly, areas = Counter(), defaultdict(Counter), defaultdict(set)
    for author, year, cat, _, issue in active:
        if author.casefold() != key:
            continue
        pooled[cat] += 1
        yearly[year][cat] += 1
        for label in set(issue.labels or []):
            if isinstance(label, str) and label.startswith('area/'):
                areas[label].add(id(issue))

    # Baseline: the top non-bot contributors other than the requested user.
    baseline_users = [a for a, _ in _ranked(humans) if a.casefold() != key][:BASELINE_SIZE]
    baseline_keys = {a.casefold() for a in baseline_users}
    baseline = Counter(cat for author, _, cat, _, _ in active if author.casefold() in baseline_keys)

    all_years = sorted(set(years) | set(yearly))
    result.update(
        total_events=sum(pooled.values()),
        pooled_counts={c: pooled.get(c, 0) for c in CATEGORIES},
        pooled_percent=percentages(pooled),
        baseline_users=baseline_users,
        baseline_total=sum(baseline.values()),
        baseline_percent=percentages(baseline),
        user_years=[dict(year=y, total=sum(yearly[y].values()),
                         counts={c: yearly[y].get(c, 0) for c in CATEGORIES},
                         percent=percentages(yearly[y]),
                         triage_share=next((t['shares'].get(user, 0.0) for t in triage_years
                                            if t['year'] == y), 0.0))
                    for y in all_years],
        top_areas=[(label, len(ids)) for label, ids in
                   sorted(areas.items(), key=lambda item: (-len(item[1]), item[0]))[:5]],
    )
    return result


def band_authors(triage_years, user):
    """Who gets a named band in the share chart: a year's top contributors
    with a large enough share, plus the requested user."""
    names = []
    for entry in triage_years:
        for author, share in list(entry['shares'].items())[:LEADER_PER_YEAR]:
            if share >= LEADER_MIN_SHARE and author not in names:
                names.append(author)
    if user and not is_bot(user) and user not in names:
        names.append(user)
    return names


COLORS = {'commented': '#4C78A8', 'labeled': '#72B7B2', 'unlabeled': '#F58518',
          'closed': '#54A24B', 'other': '#BAB0AC'}
HIGHLIGHT = '#D6450F'
MUTED = ['#9ecae1', '#c7e9c0', '#dadaeb', '#fdd0a2', '#c6dbef', '#d9f0a3',
         '#e5d8bd', '#fbb4c4', '#ccebc5', '#f2f2b0']
OTHERS = '#eeeeee'


def save_chart(result, output, show=False):
    """Three views: project triage shares by year, the user's yearly mix,
    and the user's all-years mix against the baseline."""
    import matplotlib
    if not show:
        matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch

    user = result['user']
    tri = result['triage_years']
    last_year = tri[-1]['year'] if tri else None
    tick = lambda y: f"{y}*" if y == last_year else str(y)

    fig = plt.figure(figsize=(16, 9.5))
    grid = fig.add_gridspec(2, 2, height_ratios=(3.2, 1), width_ratios=(1.35, 1),
                            hspace=0.55, wspace=0.18)
    ax_share, ax_user, ax_base = fig.add_subplot(grid[0, 0]), fig.add_subplot(grid[0, 1]), fig.add_subplot(grid[1, :])

    # Panel A: share of each year's triage actions.
    names = band_authors(tri, user)
    colors = {n: (HIGHLIGHT if n == user else MUTED[i % len(MUTED)]) for i, n in enumerate(names)}
    for x, entry in enumerate(tri):
        bottom = 0.0
        for name in names + ['everyone else']:
            value = (entry['shares'].get(name, 0.0) if name != 'everyone else'
                     else 100 - sum(entry['shares'].get(n, 0.0) for n in names))
            if value <= 0:
                continue
            ax_share.bar(x, value, bottom=bottom, color=colors.get(name, OTHERS),
                         edgecolor='white', linewidth=0.8)
            if value >= 8 and name != 'everyone else':
                ax_share.text(x, bottom + value / 2, f"{name}\n{value:.0f}%", ha='center',
                              va='center', fontsize=8,
                              color='white' if name == user else '#333',
                              fontweight='bold' if name == user else 'normal')
            bottom += value
        ax_share.text(x, 101.5, f"top: {entry['top_share']:.0f}%", ha='center', fontsize=8, color='#555')
    ax_share.set_xticks(range(len(tri)), [f"{tick(e['year'])}\nn={e['total']:,}" for e in tri])
    ax_share.set_ylim(0, 108)
    ax_share.set_ylabel("Share of the year's triage actions (%)")
    who = (f"{user} in red" if not result['user_is_bot']
           else f"{user} is a bot, so it has no band")
    ax_share.set_title(f"Who did the triage each year? ({who}; labeled, unlabeled, closed; bots excluded)",
                       fontsize=11, loc='left')

    # Panel B: the user's own mix per year.
    years = result['user_years']
    for x, entry in enumerate(years):
        bottom = 0.0
        for cat in CATEGORIES:
            value = entry['percent'][cat]
            if value <= 0:
                continue
            ax_user.bar(x, value, bottom=bottom, color=COLORS[cat], edgecolor='white')
            if value >= 9:
                ax_user.text(x, bottom + value / 2, f"{value:.0f}%", ha='center', va='center',
                             color='white', fontsize=8, fontweight='bold')
            bottom += value
        ax_user.text(x, 101.5, f"n={entry['total']:,}", ha='center', fontsize=8, color='#333')
        if entry['total'] == 0:
            ax_user.text(x, 50, 'no\nactivity', ha='center', va='center', fontsize=8, color='#999')
    ax_user.set_xticks(range(len(years)), [tick(e['year']) for e in years])
    ax_user.set_ylim(0, 108)
    ax_user.set_ylabel(f"Share of {user}'s events (%)")
    kind = ' (automation account)' if result['user_is_bot'] else ''
    ax_user.set_title(f"What {user}{kind} did each year", fontsize=11, loc='left')

    # Panel C: all years pooled, user vs baseline.
    rows = [(f"{user}\nall years, n={result['total_events']:,}", result['pooled_percent']),
            (f"Top-{len(result['baseline_users'])} others\nn={result['baseline_total']:,}",
             result['baseline_percent'])]
    for y, (_, mix) in enumerate(rows):
        left = 0.0
        for cat in CATEGORIES:
            ax_base.barh(y, mix[cat], left=left, color=COLORS[cat], edgecolor='white')
            if mix[cat] >= 5:
                ax_base.text(left + mix[cat] / 2, y, f"{mix[cat]:.0f}%", ha='center', va='center',
                             color='white', fontsize=8.5, fontweight='bold')
            left += mix[cat]
    ax_base.set_yticks(range(len(rows)), [r[0] for r in rows], fontsize=9)
    ax_base.invert_yaxis()
    ax_base.set_xlim(0, 100)
    ax_base.set_xlabel('Share of events (%)')
    ax_base.set_title('All years pooled: compared with the most active other contributors',
                      fontsize=11, loc='left')
    ax_base.legend(handles=[Patch(color=COLORS[c], label=c) for c in CATEGORIES], ncol=5,
                   loc='lower right', bbox_to_anchor=(1, 1.02), frameon=False, fontsize=9)

    for ax in (ax_share, ax_user, ax_base):
        for side in ('top', 'right'):
            ax.spines[side].set_visible(False)
    fig.suptitle(f"Contributor profile: {user}", fontsize=14, fontweight='bold', x=0.01, ha='left')
    fig.text(0.01, 0.005, f"* {last_year} may be a partial year (data ends during it). "
             "Dates in UTC. 'mentioned'/'subscribed' events excluded: they record who was tagged, "
             "not an action.", fontsize=8, color='#666')
    fig.subplots_adjust(left=0.08, right=0.99, top=0.91, bottom=0.1)

    output.mkdir(parents=True, exist_ok=True)
    path = output / f"contributor_profile_{safe_name(user)}.png"
    fig.savefig(path, dpi=150)
    if show:
        plt.show()
    plt.close(fig)
    return path


def safe_name(user):
    return ''.join(ch if ch.isalnum() or ch in '-_' else '_' for ch in user) or 'user'


def print_report(result):
    user = result['user']
    print(f"\nContributor profile: {user}" + (' (automation account)' if result['user_is_bot'] else ''))
    print('Question: what does this contributor do, and how has that changed over time?')
    print(f"Active events: {result['total_events']:,} "
          f"(excluded dataset-wide: {result['excluded']['passive']:,} passive, "
          f"{result['excluded']['undated']:,} undated, {result['excluded']['missing_author']:,} no author)")

    print(f"\nAll years pooled vs top-{len(result['baseline_users'])} other non-bot contributors")
    print(f"  {'event':<11}{user[:14]:>14}{'baseline':>11}")
    for cat in CATEGORIES:
        print(f"  {cat:<11}{result['pooled_percent'][cat]:>13.1f}%{result['baseline_percent'][cat]:>10.1f}%")
    print(f"  Baseline: {', '.join(result['baseline_users'])}")

    print(f"\nBy year  (triage share = {user}'s share of that year's labeled/unlabeled/closed actions)")
    print(f"  {'year':<6}{'events':>8}  {'main activity':<20}{'triage share':>13}   top triager that year")
    top = {t['year']: t for t in result['triage_years']}
    for entry in result['user_years']:
        main = max(CATEGORIES, key=lambda c: entry['counts'][c]) if entry['total'] else '-'
        main_text = f"{main} {entry['percent'][main]:.0f}%" if entry['total'] else '-'
        leader = top.get(entry['year'])
        leader_text = f"{leader['top_author']} ({leader['top_share']:.0f}%)" if leader else '-'
        print(f"  {entry['year']:<6}{entry['total']:>8,}  {main_text:<20}"
              f"{entry['triage_share']:>12.1f}%   {leader_text}")

    if result['top_areas']:
        print('\nAreas worked on (issues with any activity by this user, current area/* labels):')
        for label, count in result['top_areas']:
            print(f"  {label}: {count}")
    if result['triage_years']:
        first, last = result['triage_years'][0], result['triage_years'][-1]
        print(f"\nProject-wide: the top triager held {first['top_share']:.0f}% of triage actions in "
              f"{first['year']} and {last['top_share']:.0f}% in {last['year']}.")


class ContributorProfileAnalysis:
    def __init__(self):
        self.user = normalize_user(config.get_parameter('user'))

    def run(self):
        if self.user is None:
            print('Feature 2 needs a contributor. Usage: python run.py --feature 2 --user <github-username>')
            return None
        result = analyze(DataLoader().get_issues(), self.user)
        if not result['found']:
            print(f"\nNo activity found for '{self.user}'.")
            if result['suggestions']:
                print(f"Try one of the most active contributors: {', '.join(result['suggestions'])}")
            return result
        print_report(result)
        output = Path(config.get_parameter('output_dir') or DEFAULT_OUTPUT_DIR)
        path = save_chart(result, output, bool(config.get_parameter('show')))
        print(f"\nSaved chart to {path.resolve()}")
        return result


if __name__ == '__main__':
    ContributorProfileAnalysis().run()
