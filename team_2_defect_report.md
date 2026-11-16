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

## Defect 2: Exponent-style usernames are changed before Feature 2 looks them up

**Affected module / feature:** Feature 2 (`contributor_profile_analysis.py`, `ContributorProfileAnalysis.__init__` and `normalize_user`), through the `--user` option.

**Associated test case:** `tests/test_group2_contributor_profile.py` — `Group2ContributorProfileCLIIntegrationTests.test_exponent_like_username_is_looked_up_as_typed`.

**Preconditions / test data:** A valid JSON issue dataset is available through the `ENPM611_PROJECT_DATA_PATH` environment variable. The test creates a temporary dataset with one issue on which the user `1e3` commented and added a label. `1e3` is a valid GitHub username (letters and digits, starting with a digit).

**Steps to reproduce:**
1. From the repository root, run the regression test:
   `python -m unittest tests.test_group2_contributor_profile.Group2ContributorProfileCLIIntegrationTests.test_exponent_like_username_is_looked_up_as_typed`
2. The test runs `run.py --feature 2 --user 1e3` against its valid temporary JSON fixture.
3. As a control, a digits-only username such as `12345` is found correctly (`test_numeric_username_is_looked_up_as_typed` passes).

**Expected result:** The analysis looks up the contributor `1e3` as typed, prints the profile, and saves `contributor_profile_1e3.png`. The `normalize_user` docstring states that it recovers the username string the user typed.

**Actual result:** The program prints `No activity found for '1000.0'` and, in the same output, suggests `1e3` as one of the most active contributors. The configuration parser turns the string `"1e3"` into the float `1000.0`, and `normalize_user` converts it back with `json.dumps`, which gives `"1000.0"` instead of the original text. The same happens for names such as `2e5` or `1E10`.

**Relevant failure output:**

```text
FAIL: test_exponent_like_username_is_looked_up_as_typed
A valid GitHub username such as 1e3 must not be turned into a number.
AssertionError: "No activity found for '1000.0'" unexpectedly found in "Loaded 1 issues from ...issues.json.\n\nNo activity found for '1000.0'.\nTry one of the most active contributors: 1e3\n"
```

The defect was reproduced against the unchanged Group 6 application code. No production-code fix was applied as part of Team 2's testing.