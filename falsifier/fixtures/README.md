# Fixtures: cases with a known correct verdict

These are the test harness for `verify.py` (BUILD_PLAN step 7, moved ahead of step 4). Each
fixture's expected verdict was committed before any verify code existed. Expected verdicts are
never edited to make the code pass. A disagreement is reported as either a bug in the oracle or a
finding.

Each directory holds:

- `original/`: the repository before any fix. It includes `tests/test_existing.py`, whose tests are
  the PASS_TO_PASS set.
- `patched/`: the full contents of every file the patch under audit changes. This is Configuration
  A: the patch is the gold patch.
- `test/`: the test under audit, `tests/test_issue.py`. Its tests are FAIL_TO_PASS (`f2p`).
- `fixture.toml`: the class, the expected verdict, the issue, `f2p`, `p2p`, and the mutants.

Each mutant is an exact `old` → `new` replacement in the **patched** file. It has a one-sentence
rationale, and a **witness**: Python source whose final expression's value, or the exception it
raises, should differ between the patch and the mutant. Each mutant's `expected_status` is one of:

- `killed`: the test fails on the mutant.
- `survived`: the test passes on the mutant, and the witness shows it differs from the patch.
  This status is evidence for UNEARNED.
- `equivalent`: the test passes, but the witness gives the same result on the patch and the
  mutant. The mutant is discarded and counted separately, never as UNEARNED.
- `not-run`: an earlier verdict short-circuits the run (BROKEN, UNFIXED or REGRESSED), so no
  mutant forks are spent.

The plan's four classes have two fixtures each (`earned_*`, `unearned_*`, `nonfix_*`, `broken_*`).
`unfixed_clamp` and `regressed_last_n` are extras that exercise the other two verdicts.
