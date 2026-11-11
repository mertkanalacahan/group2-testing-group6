"""Feature 1: elapsed calendar days to final recorded closure by label."""
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median
import csv
import json

import config
from data_loader import DataLoader
from issue_utils import inspect_closure, is_bot, utc_date


def analyze(issues):
    """Pure calculation separated from loading and plotting for testing."""
    counts = Counter(total=len(issues), open=0, closed=0, eligible=0,
                     missing_created=0, unusable_closure=0, bot_closure=0,
                     missing_closer=0, negative_duration=0, unknown_state=0,
                     eligible_without_target_labels=0)
    durations = defaultdict(list)
    closure_exclusions = Counter(missing_closure_event=0, undated_closure=0,
                                 undated_reopen=0, reopen_at_or_after_closure=0)
    populations = defaultdict(Counter)
    for issue in issues:
        state = getattr(issue.state, 'value', issue.state)
        labels = sorted({x for x in (issue.labels or [])
                         if isinstance(x, str) and x.startswith(('area/', 'kind/'))})
        for label in labels:
            populations[label]['total'] += 1
            populations[label][state] += 1
        if state == 'open':
            counts['open'] += 1
            continue
        if state != 'closed':
            counts['unknown_state'] += 1
            continue
        counts['closed'] += 1
        created = utc_date(issue.created_date)
        if created is None:
            counts['missing_created'] += 1
            continue
        event, reason = inspect_closure(issue)
        if event is None:
            counts['unusable_closure'] += 1
            closure_exclusions[reason] += 1
            continue
        closed = utc_date(event.event_date)
        if not event.author:
            counts['missing_closer'] += 1
            continue
        if is_bot(event.author):
            counts['bot_closure'] += 1
            continue
        days = (closed - created).total_seconds() / 86400
        if days < 0:
            counts['negative_duration'] += 1
            continue
        counts['eligible'] += 1
        if not labels:
            counts['eligible_without_target_labels'] += 1
        for label in labels:
            durations[label].append(days)
    rows = []
    for label, population in sorted(populations.items()):
        values = durations[label]
        rows.append(dict(label=label, eligible_closed=len(values),
                         median_days=median(values) if values else None,
                         total_issues=population['total'], open_issues=population['open'],
                         open_percent=100 * population['open'] / population['total']))
    counts['open_percent'] = 100 * counts['open'] / counts['total'] if counts['total'] else 0
    return dict(summary=dict(counts), closure_exclusions=dict(closure_exclusions), groups=rows)


def save_charts(rows, output, show=False):
    import matplotlib
    if not show:
        matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    for prefix in ('area/', 'kind/'):
        selected = sorted((r for r in rows if r['label'].startswith(prefix)
                           and r['median_days'] is not None),
                          key=lambda r: (r['median_days'], r['label']))
        fig, ax = plt.subplots(figsize=(11, max(3.5, len(selected) * .42 + 1.8)))
        if selected:
            bars = ax.barh([r['label'] for r in selected],
                           [r['median_days'] for r in selected], color='#3478a6')
            ax.bar_label(bars, labels=[f"{r['median_days']:.1f} d (n={r['eligible_closed']})"
                                      for r in selected], padding=4, fontsize=9)
            ax.set_xlim(0, max(1, max(r['median_days'] for r in selected)) * 1.45)
        else:
            ax.text(.5, .5, 'No eligible closed issues in this label family',
                    ha='center', va='center', transform=ax.transAxes)
            ax.set_yticks([])
        ax.set_xlabel('Median elapsed calendar days to final closure')
        ax.set_title(f"Time to closure by {prefix[:-1]} label")
        ax.xaxis.grid(True, alpha=.2)
        ax.set_axisbelow(True)
        fig.text(.01, .01, 'Currently closed issues; bot closures excluded. Current labels; multi-label issues appear in multiple groups.', fontsize=8)
        fig.tight_layout(rect=(0, .04, 1, 1))
        for extension in ('png', 'svg'):
            fig.savefig(output / f'closure_by_{prefix[:-1]}.{extension}', dpi=150)
        if show:
            plt.show()
        plt.close(fig)


class ResolutionTimeAnalysis:
    def run(self):
        result = analyze(DataLoader().get_issues())
        output = Path(config.get_parameter('output_dir') or 'outputs/resolution_time')
        output.mkdir(parents=True, exist_ok=True)
        result['dataset'] = str(config.get_parameter('ENPM611_PROJECT_DATA_PATH'))
        (output / 'summary.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        fields = ['label', 'eligible_closed', 'median_days', 'total_issues', 'open_issues', 'open_percent']
        with (output / 'closure_by_label.csv').open('w', newline='', encoding='utf-8') as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(result['groups'])
        print('\nTime to final closure (calendar days)')
        for key, value in result['summary'].items():
            print(f'  {key}: {value:.2f}' if isinstance(value, float) else f'  {key}: {value}')
        print('\nBreakdown of unusable_closure (subcounts, not additional exclusions):')
        for key, value in result['closure_exclusions'].items():
            print(f'  {key}: {value}')
        print('\nLabel | median days | eligible closed | open / total')
        for row in result['groups']:
            value = 'N/A' if row['median_days'] is None else f"{row['median_days']:.2f}"
            print(f"  {row['label']} | {value} | {row['eligible_closed']} | {row['open_issues']} / {row['total_issues']}")
        save_charts(result['groups'], output, bool(config.get_parameter('show')))
        print(f'\nSaved tables and charts to {output.resolve()}')
        return result
