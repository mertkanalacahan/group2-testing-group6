# Milestone 2 verification

Verified on November 1, 2026, using PR #9 implementation commit `47a866db4eecf9a444c066507e3c9c3c4313a33c`. This report records local checks, not a GitHub Actions run.

## Dataset and environment

- Dataset: `poetry_issues_all.json`, 5,573 issues, 52,501,784 bytes.
- Environment: Windows, Python 3.13, with the project runtime dependencies installed.
- All three features ran through `run.py`, using separate custom output folders and the non-interactive Matplotlib backend.

## Results

| Check | Result | Evidence |
| --- | --- | --- |
| Feature 1: time to closure | Passed | 4,849 eligible closures; 317 open issues; six output files |
| Feature 2: contributor profile | Passed | `--user abn`: 3,756 active events; chart saved in the requested folder |
| Feature 3: first response | Passed | 5,030 answered issues; 543 without an eligible response (9.7%); six output files |
| Combined regression suite | Passed | All 65 tests passed |
| Zero-hour response regression | Passed | Same-time creation and reply produced 0.0 hours without the former chart exception |
| Username capitalization regression | Passed | Different capitalizations count as one responder |
| Chart inspection | Passed | All five generated PNG charts were visually checked for readable labels and results |

Feature 1 accounts for 5,256 closed issues as 4,849 eligible closures, 163 bot closures, and 244 unusable closures. The unusable-closure subcounts are 205 missing closure events, 18 undated closures, and 21 reopenings at or after closure. These are subcounts, not additional exclusions.

Feature 3 reports median first-response times of 20.9 hours in 2018 and 0.9 hours in 2024. No eligible response means none was observed in the supplied dataset, not proof that nobody ever replied.

## Repeat the checks

From the repository root, install the dependencies and select a Python environment as described in the README. Obtain the course dataset from Canvas and keep it outside the repository.

In PowerShell, replace the example dataset path with the actual local path:

```powershell
$env:ENPM611_PROJECT_DATA_PATH = "C:/path/to/poetry_issues_all.json"
$env:MPLBACKEND = "Agg"
python run.py --feature 1 --output-dir outputs/verification/feature1
python run.py --feature 2 --user abn --output-dir outputs/verification/feature2
python run.py --feature 3 --output-dir outputs/verification/feature3
python -m unittest discover -s tests -v
```

Each feature should load 5,573 issues and finish without a traceback. The test suite should end with `Ran 65 tests` and `OK` for the recorded implementation. Tests use synthetic fixtures and do not require the course dataset. The zero-hour and capitalization cases are included in the committed test suite; the separate local demonstration scripts are not required.

## Assessment and scope

No blocking issues were found in these checks; the tested implementation is ready for merge. GitHub reported no merge conflicts at verification time. This is a dated verification record, not a claim that a merge has already happened or that every possible input has been tested.

The full-data Feature 2 run used `abn`; other username cases are covered by automated tests rather than exhaustive full-data runs. Existing interpretation and input limitations remain documented in the README. Console logs, generated charts, and tables were retained locally. Course data, personal paths, and virtual environments are not included in this report.
