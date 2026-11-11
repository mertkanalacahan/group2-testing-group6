# ENPM611 Fall 2026 Group 6 Project

Team 6 is extending the course Python application to analyze Poetry GitHub issue activity: time to closure, contributor activity, and time to first response.

This is our shared fork of the [ENPM611 application template](https://github.com/enpm611/project-application-template).

## Team

| Member | GitHub | Milestone 1 responsibility |
| --- | --- | --- |
| Marcin Poplawski | [mpoplaw1](https://github.com/mpoplaw1) | Sequence diagram and repository |
| Ashish Bhoya | [11Ashish11](https://github.com/11Ashish11) | Component diagram after changes |
| Mahima Shenoy | [s-mahima09](https://github.com/s-mahima09) | Component diagram before changes |

Marcin implements and tests Feature 1 (time to closure) and the shared issue helpers. Ashish implements and tests Feature 2 (contributor profile over time). Mahima implements and tests Feature 3 (time to first response).

## Current status

This version contains the course template, all three Milestone 1 diagrams, shared issue helpers, Feature 1 (time to closure), Feature 2 (contributor profile over time), and Feature 3 (time to first response). Feature 0 remains the provided example.

Milestone 1 diagrams are available in docs/milestone1 on main and linked below. These describe the existing architecture and planned changes.

## Milestone 1 Design

| Artifact | Mermaid source | Image |
| --- | --- | --- |
| Component diagram before changes | [TXT](docs/milestone1/team_6_component_diagram_before.txt) | [SVG](docs/milestone1/team_6_component_diagram_before.svg) |
| Component diagram after changes | [TXT](docs/milestone1/team_6_component_diagram_after.txt) | [SVG](docs/milestone1/team_6_component_diagram_after.svg) |
| Contributor profile sequence diagram | [TXT](docs/milestone1/team_6_sequence_diagram.txt) | [SVG](docs/milestone1/team_6_sequence_diagram.svg) |

The sequence diagram follows `python run.py --feature 2 --user abn`, from configuration and data loading through contributor comparison and output.

[Repository URL submission file](docs/milestone1/team_6_repo.txt). GitHub stores the work and review history; required assignment files must also be submitted through Canvas.

## Analyses

Features 1, 2 and 3 are implemented below.

### Feature 1 Time to closure by area and kind

**Question:** Which issue areas and kinds have the longest median elapsed time to closure?

**Module:** `resolution_time_analysis.py`.

**Method:** For eligible closed issues, calculate days from creation to the final recorded closure. Group by current `area/*` and `kind/*` labels. Exclude bot closures and unusable records with explicit exclusion counts. Report the proportion still open separately.

**Input:** None beyond the feature selection.

**Output:** Sorted horizontal bar charts of median days with sample sizes, CSV label statistics, JSON summary and exclusion counts, and a console explanation.

```bash
python run.py --feature 1
```

By default, files are saved in `outputs/resolution_time/` without opening chart windows:

- `closure_by_area.png` and `.svg`
- `closure_by_kind.png` and `.svg`
- `closure_by_label.csv`
- `summary.json`

Use `python run.py --feature 1 --output-dir outputs/my-run` to select another directory. Add `--show` to display charts on a graphical desktop. The `--user` and `--label` options are reserved for other analyses and do not filter Feature 1.

Elapsed days use UTC timestamps and 86,400 seconds per day; timestamps without a time zone are assumed UTC. Only currently closed issues with a usable final closure are eligible. A reopening at or after the last closure, or an undated closure/reopening, makes the closure unusable. Missing creation dates, missing closing authors, bot final closures, and negative durations are also excluded. A zero-day duration is valid. The bot rule checks a case-insensitive `[bot]` suffix.

Open percentages use all issues in the dataset (or all issues carrying a label for the per-label percentage), not just eligible closed issues. Current duplicate labels are counted once per issue; an issue with several labels contributes to several groups. Eligible issues without `area/` or `kind/` labels are counted separately. Groups with no eligible closures have a blank CSV median and JSON `null`; they are omitted from median bars. Empty datasets still produce tables and placeholder charts. Closure-exclusion subcounts explain `unusable_closure`; they are not additional exclusions.

The JSON report records the dataset path for provenance. Generated reports are ignored by Git; check that path before sharing reports separately.

### Feature 2 Contributor profile over time

**Question:** What does a given contributor do on Poetry's issues, how has that changed year by year, and where do they fit in the history of who did the project's triage work?

**Module:** `contributor_profile_analysis.py` (class `ContributorProfileAnalysis`).

**Input:** a GitHub username through `--user`. Matching is case-insensitive (GitHub usernames are), so `--user ABN` and `--user abn` give the same result.

```bash
python run.py --feature 2 --user abn
```

**Method:**

1. Keep only *active* events: a known author and a valid date. `mentioned`, `subscribed` and `unsubscribed` are excluded because GitHub records the person who was tagged or auto-subscribed as their author, not someone who acted. (In the full dataset, 96% of `mentioned` authors appear as an `@username` in that issue's text or comments.) Exclusion counts are printed.
2. **Project view:** for each year (UTC), take all `labeled`, `unlabeled` and `closed` events by non-bot accounts ("triage actions") and compute each person's share. The requested user is highlighted, and the top person's share is shown above each year.
3. **User view:** the requested user's event mix per year (`commented`, `labeled`, `unlabeled`, `closed`, everything else as `other`), with the event count for each year.
4. **Pooled comparison:** the user's all-years mix against the combined events of the 10 most active *other* non-bot contributors.
5. **Areas:** the `area/*` labels on issues the user was active on, counting each issue once per label.

**Output:**

- A console report: the pooled mix vs baseline, a year-by-year table (events, main activity, the user's triage share, that year's top triager), top areas, and exclusion counts.
- A three-panel chart saved to `outputs/contributor_profile/contributor_profile_<user>.png`. Use `--output-dir <folder>` to save it elsewhere, and add `--show` to also open it on a graphical desktop.

**Example finding (full dataset):** the top triager's share fell from 76% (sdispater, 2018) to 16% (2024), so triage work became spread across more people over time. `abn` shifted from mostly commenting (2020–21) to mostly removing labels (2022, 2024), with no active events in 2023, a change that a single all-years average hides.

**Edge cases:**

| Input | Behavior |
| --- | --- |
| No `--user` | Prints usage and exits normally |
| Unknown user | Prints "No activity found" and suggests the 5 most active non-bot contributors |
| Numeric or JSON-like names (`--user 12345`, `--user true`) | The configuration system decodes these; the analysis restores the typed string. `--user null` cannot be distinguished from a missing value and is treated as missing |
| Bot account (`--user "github-actions[bot]"`) | Profiled and labeled as automation; bots never appear in the triage shares or the baseline |
| Year with no activity by the user | Shown as an empty bar with `n=0` |
| Events with no author or no date | Excluded and counted in the report |

**Tests:**

```bash
python -m unittest discover -s tests -p "test_contributor*" -v
```

19 tests cover username normalization, passive/undated/authorless exclusions, case-insensitive matching, pooled percentages, baseline selection (bots and the requested user excluded, ties broken by name, capped at 10), per-year triage shares, zero-activity years, UTC year boundaries, bot users, area counting, chart output, the default and `--output-dir` output folders, and end-to-end runs for known, unknown and missing users using a temporary synthetic dataset.

**Limitations:**

- Triage share counts actions, not effort: removing a label and resolving a hard issue each count once.
- The baseline is the most active accounts, not a verified maintainer list.
- Area labels are the issue's current labels, which may differ from its labels when the user was active.
- The bot rule is the shared `[bot]`-suffix heuristic from `issue_utils.is_bot`.
- The final year in the dataset may be partial (the full dataset ends in October 2024) and is marked with `*`.

### Feature 3 Time to first response by year

**Question:** How quickly do issues receive their first response, and how has that changed over time?

**Module:** `response_time_analysis.py` (class `ResponseTimeAnalysis`).

**Method:**

- For each issue, find the first reply from someone other than the person who opened it. Bot accounts (names ending in `[bot]`) don't count. This uses `get_first_response()` from `issue_utils.py`.
- Measure the hours between the issue being opened and that first reply.
- Group issues by the year they were opened.
- For each year, show the typical wait (the median) and the share of issues that got no reply.
- Issues missing an opening date or an author are left out and counted separately. They are not counted as unanswered.

**Extra check:** For each year, the analysis names the person who replied first most often. It then works out what the typical wait would have been without their replies. This shows how much the project depends on one person. The original data is not changed.

**Input:** None. Just run the command.

**Output:**

- On screen: the question, how it was answered, a table for each year, the five people who replied first most often, and a one-line finding.
- Saved in `outputs/response_time/`:
  - `first_response_by_year.png` and `.svg`: a line chart with two lines, typical wait in hours and % with no reply.
  - `first_response_without_top_responder.png` and `.svg`: a line chart comparing the typical wait with all replies against the wait without that year's top replier. Each year is labeled with that person's name and share of first replies.
  - The numbers as `first_response_by_year.csv` and `summary.json`.

```bash
python run.py --feature 3
```

Add `--show` to open the chart in a window as well. To save the files somewhere else, add `--output-dir <folder>`. You can also run this feature on its own with `python response_time_analysis.py`.

**Finding (full dataset):** The typical wait for a first reply dropped from about 21 hours in 2018 (and 108 hours in 2019) to about 1 hour from 2022 onward. Each year, 7% to 14% of issues got no reply. Since 2023, one volunteer (`dimbleby`) gave about three out of four first replies. Without his replies, the typical wait would be about 10 to 12 hours.

**Limitations:**

- Any comment counts as a reply, even if it doesn't help.
- 2024 is only a partial year, and newer issues have had less time to get a reply.
- Bots are spotted by name only, so some may be missed.
- The "without the top replier" number shows how much the project relies on that person. It does not prove what would have happened without them.

Tests: `python -m unittest tests.test_response_time -v`

## Setup

Use Python 3 and pip. Feature 1 has been tested with Python 3.13 on Windows; a minimum supported version has not been established. Dependencies in `requirements.txt` are python-dateutil, pandas, and matplotlib.

### Clone the repository

```bash
git clone https://github.com/mpoplaw1/Fa26-Group6-project.git
cd Fa26-Group6-project
```

For an existing clone of the team fork under its previous name, run this inside that clone:

```bash
git remote set-url origin https://github.com/mpoplaw1/Fa26-Group6-project.git
```

### Install dependencies

Windows PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

macOS or Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

### Configure the dataset

Download `poetry_issues.json` or `poetry_issues_all.json` from Canvas. Keep the dataset outside the repository. Use the full dataset for project-wide results and identify the dataset used when presenting findings.

Set the environment variable in the same terminal used to run the application. Replace the example path with your actual file location.

Windows PowerShell:

```powershell
$env:ENPM611_PROJECT_DATA_PATH = 'C:\path\to\poetry_issues_all.json'
```

macOS or Linux:

```bash
export ENPM611_PROJECT_DATA_PATH='/path/to/poetry_issues_all.json'
```

Alternatively, edit that setting in your local `config.json`. Environment variables take precedence. Do not commit personal paths.

### Run the existing example

From the repository root, with the environment active and dataset configured:

```bash
python run.py --feature 0
```

The template prints an event count and displays a bar chart of top issue creators. A graphical desktop session is needed to view its chart window.

## Application structure

| File | Responsibility | Status |
| --- | --- | --- |
| `run.py` | Parse arguments and dispatch analyses | Features 0, 1, 2 and 3 connected |
| `config.py` | Settings and argument overrides | Existing |
| `data_loader.py` | Load and cache Issue objects | Existing |
| `model.py` | Issue and Event data model | Existing |
| `example_analysis.py` | Demonstrate analysis and chart output | Existing |
| `resolution_time_analysis.py` | Feature 1 | Implemented |
| `contributor_profile_analysis.py` | Feature 2 | Implemented |
| `response_time_analysis.py` | Feature 3 | Implemented |
| `issue_utils.py` | Shared bot, closure-date and response helpers | Implemented; see [helper contract](SHARED_HELPERS.txt) |

## Testing Features 1, 2 and 3 and shared helpers

After installing the runtime dependencies, run from the repository root:

```bash
python -m unittest discover -s tests -v
```

The 26 tests include 14 closure-analysis tests, 10 shared-helper tests, and two CLI integration tests. Integration tests create temporary synthetic JSON datasets, invoke Feature 1, and check the numerical CSV/JSON results and PNG/SVG artifacts. No course dataset or network access is needed. Coverage includes final closures after reopening, bot closures, UTC offsets, zero and negative durations, missing dates, duplicate labels, open-issue denominators, medians, and empty data.

Feature 2 adds 19 tests in `tests/test_contributor_profile_analysis.py` (described under Feature 2 above), bringing the suite to 45 tests.

Feature 3 adds 20 tests in `tests/test_response_time.py`, bringing the suite to 65 tests. They cover bot and creator replies, earliest-reply selection, usernames that differ only in capital letters, grouping by the year an issue was opened, time zones, missing dates and creators, years with no replies, 0-hour replies, the "without the top replier" check, empty data, and both saved charts.

The inherited loader expects the course JSON schema. Invalid issue states or malformed JSON can stop loading; the CLI reports a failure rather than claiming those records were analyzed. The `unknown_state` unit case exercises the pure calculation with an already constructed object.

## Interpretation and limitations

- Closure does not necessarily mean successful resolution. Elapsed calendar time does not measure developer effort.
- Current labels may differ from labels at the time of an event. Multi-label issues can contribute to multiple groups.
- Bot identification using a username suffix such as `[bot]` is a heuristic.
- The top 10 active contributors are an activity-based comparison group, not a verified maintainer list. Event types alone do not establish whether comments are answers or questions.
- Unanswered means no eligible response observed within the dataset. Recent issues have shorter observation periods, and 2024 is a partial year in the supplied data.
- Removing one contributor's comments is a sensitivity analysis, not proof of what would happen if that person left.
- Configuration parsing can convert usernames such as `12345` and `true` into other types. Feature 2 restores the typed string; `--user null` cannot be distinguished from a missing value and is treated as missing.

## Team workflow

Create a branch for each independent change, commit meaningful work, and open a pull request targeting this team's main branch for review. Merge approved implementation work before the implementation milestone. Record completed contributions and verified run instructions as work progresses.

Keep datasets, virtual environments, credentials, personal configuration, and temporary outputs out of Git. Keep Mermaid sources and required SVG design deliverables together.

The inherited auto-close workflow is restricted to the original course repository and does not close pull requests in this team fork.

## Milestone 2 full-dataset verification

The November 1, 2026 check of implementation commit `47a866d` passed all three features on `poetry_issues_all.json` (5,573 issues), plus all 65 automated tests. See the [verification report](docs/milestone2/verification.md) for results, regression checks, and scope.

After completing Setup and configuring the full dataset in the same terminal, run from the repository root:

```powershell
$env:MPLBACKEND = "Agg"
python run.py --feature 1 --output-dir outputs/verification/feature1
python run.py --feature 2 --user abn --output-dir outputs/verification/feature2
python run.py --feature 3 --output-dir outputs/verification/feature3
python -m unittest discover -s tests -v
```

`Agg` saves charts without opening chart windows. Feature 2 is exercised with the dataset contributor `abn`. Each feature should finish without a traceback and save its outputs under the specified folder. The recorded test suite ends with `Ran 65 tests` and `OK`; the tests use synthetic data, independently of the full-dataset runs. Keep generated outputs and the course dataset local.
