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
- `survived`: the mutant passes FAIL_TO_PASS, its witness shows it differs from the patch, and
  it also passes every PASS_TO_PASS test. It clears SWE-bench's full resolution criterion, which
  is the evidence for UNEARNED.
- `caught-by-p2p`: the mutant passes FAIL_TO_PASS and is distinguishable, but PASS_TO_PASS catches
  it. This is the evidence for UNPINNED: the designated test does not pin the bug, and the suite
  catches the mutant incidentally.
- `equivalent`: the test passes, but the witness gives the same result on the patch and the
  mutant. The mutant is discarded and counted separately, never as UNEARNED.
- `not-run`: an earlier verdict short-circuits the run (BROKEN, UNFIXED or REGRESSED), so no
  mutant forks are spent.

The plan's four classes have two fixtures each (`earned_*`, `unearned_*`, `nonfix_*`, `broken_*`).
`unfixed_clamp` and `regressed_last_n` are extras that exercise the other two verdicts.
`unpinned_last_n` exercises UNPINNED (added 2026-10-25 with the verdict split).
`unearned_clamp_float` covers a domain wider than the test: clamp accepts floats, the test covers
integers only, and m4 differs from the patch only on a float. Its sibling `earned_clamp` restricts
clamp to integers, so there the same m4 is equivalent over the whole domain.

`fixture.toml` may state the code's input `domain`. Equivalence is relative to it: a mutant
equivalent over one domain can be distinguishable over a wider one.

Expectations changed after the fact, each with Parth's approval and recorded in
`docs/plan_deviations.md`: `earned_clamp` m4, from `killed` to `equivalent` (2026-10-25; an oracle
bug, found when the oracle contradicted the fixture).
