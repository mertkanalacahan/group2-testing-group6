# Team 2 — Defect Report

## Defect 1: Numeric output directory names cause Feature 1 to fail

**Affected module / feature:** `config.py` (`convert_to_typed_value`, `get_parameter`), affecting Feature 1 (`resolution_time_analysis.py`) through the `--output-dir` option.

**Associated test case:** `tests/test_group2_resolution_time.py` — `Group2ResolutionCLIIntegrationTests.test_numeric_output_directory_name_is_accepted`.

**Preconditions / test data:** A valid JSON issue dataset is available through the `ENPM611_PROJECT_DATA_PATH` environment variable. The regression test creates a temporary dataset with one closed `kind/bug` issue, a creation timestamp, and a valid human-authored closure event. Its working directory is a temporary folder without a pre-existing `2024` output directory.

**Steps to reproduce:**
1. From the repository root, run the regression test:
   `python -m unittest tests.test_group2_resolution_time.Group2ResolutionCLIIntegrationTests.test_numeric_output_directory_name_is_accepted`
2. The test launches `run.py --feature 1 --output-dir 2024` against its valid temporary JSON fixture.
3. As a control, using `--output-dir ./2024` with the same dataset succeeds.

**Expected result:** The application accepts `2024` as a valid relative directory name, exits successfully, and creates `2024/summary.json` and the other Feature 1 output files.

**Actual result:** The application exits with code 1 and does not produce the expected files. The configuration parser interprets the string `"2024"` as the integer `2024`, which the analysis then passes to `pathlib.Path`.

**Relevant failure output:**

```text
AssertionError: 1 != 0 : Unable to run analysis: argument should be a str or an os.PathLike object where __fspath__ returns a str, not 'int'
Check the dataset path and JSON format.
```

The defect was reproduced against the unchanged Group 6 application code. No production-code fix was applied as part of Team 2's testing.
