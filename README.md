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
- **UNEARNED**: the test also passes on at least one mutant that its own witness shows to behave
  differently from the patch.
- **INCONCLUSIVE** (not a verdict): a run that a verdict needs did not produce its evidence. That
  includes the negative-control canary not proving that patches reach the code, and no mutant
  that can be told apart from the patch.

## Results

**Scope: five SWE-bench Verified instances across three repositories (pallets/flask,
psf/requests, pytest-dev/pytest). Configuration A: the gold patch, audited against the
benchmark's own FAIL_TO_PASS tests. Nothing here extrapolates to the rest of the benchmark.**

| Instance | SWE-bench says | Falsifier says | Killed / distinguishable | Equivalent | Canary exit |
|---|---|---|---|---|---|
| `pallets__flask-5014` | RESOLVED | EARNED (on 1 mutant) | 1 / 1 | 0 | 1 |
| `psf__requests-5414` | RESOLVED | UNEARNED | 5 / 7 | 1 | 1 |
| `psf__requests-6028` | RESOLVED | UNEARNED | 4 / 5 | 5 | 1 |
| `pytest-dev__pytest-7432` | RESOLVED | INCONCLUSIVE (no usable mutants) | 0 / 0 | 0 | 3 |
| `pytest-dev__pytest-7571` | RESOLVED | not completed (spend ceiling) | | | |

The survivors, each with its diff and rationale beside the test that missed it and the witness on
both sides, are in `docs/results.md`. Full evidence for every fork is in `reports/instances/`.

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
- **UNEARNED is relative to the FAIL_TO_PASS tests only.** Under Configuration A, mutants never
  run against PASS_TO_PASS, by design. Two of the three survivors break behaviour that
  PASS_TO_PASS ids appear to cover, so the repository's own suite would probably catch them:
  `psf__requests-5414` m1 drops the pre-existing `*` wildcard check, and `psf__requests-6028` m1
  crashes on URLs without auth. Neither was run against PASS_TO_PASS. The clearest survivor,
  `psf__requests-5414` m4, accepts only the literal `.example.com` from the issue, and no
  PASS_TO_PASS id names a comparable host.
- **`propose_patch` hallucinated on `pallets__flask-5014`.** Asked for a fix, Nemotron 3.5
  Lightning inserted the guard into about ten methods with invented context. Its re-asks
  returned the identical answer, even with rising temperature, so no candidate patch was
  produced. Candidate patches are the subject under audit, so this is reported, not tuned.
- **The WITNESS field's first live run.** The model ignored the witness contract:
  - It wrote shell wrappers (`python3 -c "..."`), doctest transcripts with outputs it claimed to
    expect, or no witness block at all.
  - Deterministic normalization (unwrap, strip prompts, drop claimed outputs) and comparing
    printed output recovered most of them. `pytest-dev__pytest-7432` still produced no usable
    witness, which is why it is INCONCLUSIVE.
  - The witnesses print the model's own labels ("CORRECT", "MUTANT"). Those labels are
    constants, so they cannot create a difference, but a reader should ignore them.
  - One witness calls `requests.get`, which resolves DNS, so part of its output depends on the
    network.
- **Mutant yield is low and erratic.** On `pallets__flask-5014`, 9 of 10 mutant diffs did not
  apply, even after whitespace re-anchoring, so its EARNED rests on a single killed mutant.
  `pytest-dev__pytest-7432` yielded none.
- **INCONCLUSIVE and incomplete instances.** `pytest-dev__pytest-7432` had a live canary (exit 3,
  `INTERNALERROR> AssertionError: canary`) but no distinguishable mutant. `pytest-dev__pytest-7571`
  stopped when the $2 phase 3 ceiling tripped during its mutant forks.
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
