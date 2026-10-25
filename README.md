# Falsifier

Falsifier checks model-proposed code patches by running them in isolated sandboxes, and keeps only the findings that execution supports.

## Problem

_TODO: describe the problem Falsifier addresses._

## How it works

_TODO: describe the red, patch, green loop and how evidence is collected._

**"Benchmark oracle" means the repository's own FAIL_TO_PASS tests**, as listed in SWE-bench
Verified. It does not mean a reproduction of SWE-bench's harness, which Falsifier does not
reimplement. The "SWE-bench says" column is the dataset's published label (`falsifier/official.py`).

## Verdicts

- **EARNED**: the test fails on the original, passes on the patch, the PASS_TO_PASS suite still
  passes, and the test kills every mutant that can be told apart from the patch.
- **BROKEN**: the test passes on the original code, so it never reproduced the bug.
- **UNFIXED**: the test fails on the patch.
- **REGRESSED**: the patch passes its test but breaks the existing PASS_TO_PASS suite.
- **UNEARNED**: at least one mutant that its own witness shows to behave differently from the
  patch clears SWE-bench's full resolution criterion: it passes FAIL_TO_PASS and PASS_TO_PASS.
- **UNPINNED**: no mutant clears both lists, but at least one distinguishable mutant passes
  FAIL_TO_PASS and is caught only by PASS_TO_PASS. The designated test does not pin the bug; the
  suite catches the mutant incidentally.
- **INCONCLUSIVE** (not a verdict): a run that a verdict needs did not produce its evidence. That
  includes the negative-control canary not proving that patches reach the code, and no mutant
  that can be told apart from the patch.

## Results

**Scope: five SWE-bench Verified instances across three repositories (pallets/flask,
psf/requests, pytest-dev/pytest). Configuration A: mutants of the gold patch, held to SWE-bench's
full resolution criterion (FAIL_TO_PASS passes and PASS_TO_PASS does not regress). Nothing here
extrapolates to the rest of the benchmark.**

| Instance | SWE-bench says | Falsifier says | Distinguishable | Equivalent | Survived FAIL_TO_PASS | Survived both | Canary exit |
|---|---|---|---|---|---|---|---|
| `pallets__flask-5014` | RESOLVED | EARNED (on 1 mutant) | 1 | 0 | 0 | 0 | 1 |
| `psf__requests-5414` | RESOLVED | UNPINNED | 7 | 1 | 2 | 0 | 1 |
| `psf__requests-6028` | RESOLVED | UNPINNED | 5 | 5 | 1 | 0 | 1 |
| `pytest-dev__pytest-7432` | RESOLVED | INCONCLUSIVE (no usable mutants) | 0 | 0 | 0 | 0 | 3 |
| `pytest-dev__pytest-7571` | RESOLVED | EARNED | 7 | 3 | 0 | 0 | 1 |

**Headline: 0 of 20 distinguishable mutants cleared both FAIL_TO_PASS and PASS_TO_PASS.** Three
passed FAIL_TO_PASS and were each caught only by PASS_TO_PASS. The designated FAIL_TO_PASS tests
did not pin those behaviours; the repositories' existing suites did.

The survivors, each with its diff and rationale beside the test that missed it, the witness on both
sides and its PASS_TO_PASS result, are in `docs/results.md`. Full evidence for every fork is in
`reports/instances/`.

## Usage

_TODO: installation and CLI usage._

### Configuration

Settings live in `falsifier/config.py`; this list mirrors it.

| Setting | Value | Override |
|---|---|---|
| Token Factory base_url (OpenAI-compatible) | `https://api.tokenfactory.nebius.com/v1/` | `FALSIFIER_BASE_URL` |
| Generation model | `nvidia/Nemotron-3_5-Lightning`, thinking off | `FALSIFIER_MODEL` |
| Model price, USD per 1M tokens in / out | 0.06 / 0.24 | `FALSIFIER_USD_PER_M_INPUT`, `FALSIFIER_USD_PER_M_OUTPUT` |
| Response cache (gitignored) | `.cache/generate/` | `FALSIFIER_GENERATE_CACHE` |
| Sandbox spend ceiling | set per script | `FALSIFIER_SPEND_CEILING_USD` |

`NEBIUS_API_KEY` and `NEBIUS_PROJECT_ID` are read from the environment or a local `.env`; see
`.env.example`.

## Limitations

These are real holes, found by building and running Falsifier. The scope throughout is five
instances across three repositories.

- **Equivalence is relative to the input domain, not absolute.** Falsifier discards a surviving
  mutant as equivalent when its own witness cannot tell it apart from the patch. That discard is
  sound only within the domain the witness explores. A mutant equivalent over one domain can be
  distinguishable over a wider one. `clamp` with `x > hi - 1` is the same as the patch for
  integers and different for `clamp(9.5, 0, 10)`. If the code accepts more than its witness
  tries, a discarded mutant may be a real survivor, and EARNED may be too generous.
  The fixtures `earned_clamp` (integers only, enforced) and `unearned_clamp_float` (floats
  accepted, integer-only test) pin both sides. We found this when our own oracle contradicted
  our own fixture: the fixture said `killed`, the oracle said `equivalent`, and the oracle was
  right.
- **UNEARNED was at first relative to the FAIL_TO_PASS tests only (now corrected).** Until the
  verdict split, mutants never ran against PASS_TO_PASS, by an instruction given at the start of
  phase 1. That was wrong: a mutant stands in for a candidate patch and must face the criterion
  a candidate faces. Two of the first run's three survivors broke behaviour that PASS_TO_PASS ids
  appeared to cover: `psf__requests-5414` m1 drops the pre-existing `*` wildcard check, and
  `psf__requests-6028` m1 crashes on URLs without auth. Once PASS_TO_PASS ran, all three were
  caught. That includes `psf__requests-5414` m4, which accepts only the literal `.example.com`
  from the issue: it was caught incidentally, by the same five wildcard tests, because its
  rewrite also dropped the `*` branch, not because any test pins the too-narrow `.` handling.
- **UNEARNED is now scoped to SWE-bench's full resolution criterion.** UNEARNED means a
  distinguishable mutant passes FAIL_TO_PASS AND PASS_TO_PASS. A survivor that PASS_TO_PASS
  catches makes the instance UNPINNED instead. Both statements are only as strong as the
  repository's PASS_TO_PASS list. Mutants are never run against tests outside it.
- **`propose_patch` hallucinated on `pallets__flask-5014`.** Asked for a fix, Nemotron 3.5
  Lightning inserted the guard into about ten methods with invented context. Its re-asks
  returned the identical answer, even with rising temperature, so no candidate patch was
  produced. Candidate patches are the subject under audit, so this is reported, not tuned.
- **The WITNESS field's first live run.** The model ignored the witness contract:
  - It wrote shell wrappers (`python3 -c "..."`), doctest transcripts with outputs it claimed to
    expect, or no witness block at all.
  - Deterministic normalization (unwrap, including shell suffixes such as `2>&1 | head -5`;
    strip prompts; drop claimed outputs; accept an unlabelled witness block) and comparing
    printed output recovered most of them. On `pytest-dev__pytest-7432` the witnesses now parse.
    The ones inspected call `pytest.main([__file__])`, which in a witness script raises the same
    NameError on both sides, so it cannot distinguish anything.
  - The witnesses print the model's own labels ("CORRECT", "MUTANT"). Those labels are
    constants, so they cannot create a difference, but a reader should ignore them.
  - One witness calls `requests.get`, which resolves DNS, so part of its output depends on the
    network.
- **Mutant yield is low and erratic.** On `pallets__flask-5014`, 9 of 10 mutant diffs did not
  apply, even after whitespace re-anchoring, so its EARNED rests on a single killed mutant. On
  `pytest-dev__pytest-7432`, 12 of 13 diffs did not apply (at `skipping.py:291`) and the other
  changed nothing, so it yielded none.
- **INCONCLUSIVE and incomplete instances.** `pytest-dev__pytest-7432` had a live canary (exit 3,
  `INTERNALERROR> AssertionError: canary`) but no distinguishable mutant, so it is INCONCLUSIVE.
  `pytest-dev__pytest-7571` first stopped when the $2 phase 3 ceiling tripped during its mutant
  forks. It was completed after the ceiling was raised to $5 (EARNED: 7 of 7 distinguishable
  mutants killed, 3 equivalent discarded).
- **The ceiling tripped on conservative accounting.** An API read timeout on one build left its cost
  unknown, so the guard charged that build its worst case, $1.24. That was most of the $2, and the
  ceiling tripped with only about $0.55 of reported run costs. The guard is built to fail safe, and
  here it stopped the run early.
- **Test-id formats differ by repository.** The first run reported REGRESSED for the
  `psf__requests-6028` gold patch, which is impossible by construction. The cause was our grading:
  SWE-bench reduces absolute-path parameters in requests' test ids to their basename, and we had
  not. Ids are now normalized the dataset's way.
- **The loop-termination check is a heuristic.** Per-fork timeouts are the backstop. Witness
  determinism is partly enforced (`PYTHONHASHSEED=0`, object addresses masked), but not for
  network, time or randomness.

## Prior art

Falsifier is an independent implementation. Three projects shaped the design:

- PatchProof (Apache-2.0) for the red, patch, green loop and per-attempt evidence
- Kelp (MIT) for evidence-gated findings: the model proposes, execution decides
- CodeMore (MIT) for pairing every rule with true-positive and false-positive fixtures

No code was copied from any of them.

## License

MIT. See [LICENSE](LICENSE).
