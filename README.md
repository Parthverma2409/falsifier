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

> **Pre-registered (2026-10-25).** This section was written and committed *before* the
> pre-committed escalation ran: 30 mutants per instance, on the same five instances, through the
> same code path, with no instance substitution. It holds two drafts. After the run, the draft
> matching the outcome is kept, its ⟨placeholders⟩ are filled with measured numbers, and the
> other draft is deleted. Nothing else in the framing changes. The commit adding this section
> precedes the run in git history.

### Draft A: the escalation yields zero UNEARNED

**Scope:** five SWE-bench Verified instances (`pallets__flask-5014`, `psf__requests-5414`,
`psf__requests-6028`, `pytest-dev__pytest-7432`, `pytest-dev__pytest-7571`) across three
repositories (flask, requests, pytest); ⟨N⟩ distinguishable mutants of the gold patches (20 at 10
mutants per instance, ⟨N30⟩ at 30); Configuration A. Nothing here extrapolates to the rest of
SWE-bench or SWT-bench.

**Finding 1: SWE-bench's resolution criterion held.** FAIL_TO_PASS passing AND PASS_TO_PASS
holding rejected every wrong fix we generated: 0 of ⟨N⟩ distinguishable mutants met it. The stronger
criterion survived a larger sample: 0 of 20 at 10 mutants per instance, and 0 of ⟨N30⟩ at 30.

**Finding 2: SWT-bench's criterion did not.** The fail-to-pass transition on the designated test
alone was satisfied by wrong fixes on ⟨K⟩ of 5 instances. A test meeting that criterion can be
satisfied by a wrong fix: one that does not fix the bug in general, or one that fixes the
reported case while breaking behaviour outside it.

Evidence: each is a mutant of the gold patch. The designated FAIL_TO_PASS test fails on the
original code and passes on the mutant. The mutant provably behaves differently from the gold patch
on its own witness, and the instance's negative-control canary is live.

- `psf__requests-5414` m4 (too narrow). `elif host.startswith((u'*', u'.')):` became
  `elif host == '.example.com':`. Designated test `test_invalid_url[InvalidURL-http://.example.com]`:
  exit 1 on the original, exit 0 on the mutant. Witness `requests.get('http://.evil.com')`: the
  gold patch raises `InvalidURL`, the mutant raises urllib3's `LocationParseError`, the original
  bug's symptom (witness exits 0 and 0). Canary exit 1, live. It does not fix the bug in general.
- `psf__requests-5414` m1. The same line became `elif host.startswith(u'.'):`. Designated test: exit 1
  on the original, exit 0 on the mutant. Witness `requests.get('http://*.example.com')`: the gold
  patch raises `InvalidURL`, the mutant proceeds to a network `ConnectionError` (exits 0 and 0).
  Canary exit 1, live. It fixes the reported case and drops the existing `*` check.
- `psf__requests-6028` m1. `if auth:` became `if netloc:`. Both designated tests: exit 1 on the
  original, exit 0 on the mutant. Witness `prepend_scheme_if_needed('http://example.org/', 'https')`:
  the gold patch returns `'http://example.org/'`, the mutant raises `TypeError` (exits 0 and 0).
  Canary exit 1, live. It fixes the reported case and crashes on URLs without auth.
- ⟨FAIL_TO_PASS survivors from the 30-mutant run, in the same form, or "none further"⟩

PASS_TO_PASS caught every one of these, so each instance is UNPINNED, not UNEARNED. These are the
repositories' own hand-written regression tests from the fixing pull requests, not generated ones.
That makes the point stronger: if the maintainers' regression test for the bug does not pin it, a
generated test need not either.

⟨Per-instance table from the 30-mutant run: distinguishable, equivalents discarded, survived
FAIL_TO_PASS, also survived PASS_TO_PASS, verdict, canary exit.⟩

The 10-mutant run, for reference: flask-5014 EARNED (1 distinguishable); requests-5414 UNPINNED
(7; 2 survived FAIL_TO_PASS; 0 both); requests-6028 UNPINNED (5; 1; 0); pytest-7432 INCONCLUSIVE
(0); pytest-7571 EARNED (7; 0; 0).

Every survivor's diff and rationale, beside the test that missed it, the witness on both sides
and its PASS_TO_PASS result, is in `docs/results.md`. The evidence for every fork is in
`reports/instances/`.

### Draft B: the escalation yields at least one UNEARNED

**Scope:** five SWE-bench Verified instances (`pallets__flask-5014`, `psf__requests-5414`,
`psf__requests-6028`, `pytest-dev__pytest-7432`, `pytest-dev__pytest-7571`) across three
repositories (flask, requests, pytest); ⟨N⟩ distinguishable mutants of the gold patches (20 at 10
mutants per instance, ⟨N30⟩ at 30); Configuration A. Nothing here extrapolates to the rest of
SWE-bench or SWT-bench.

**Finding 1: SWE-bench's resolution criterion.** FAIL_TO_PASS passing AND PASS_TO_PASS holding
rejected ⟨R⟩ of ⟨N⟩ distinguishable wrong fixes we generated. ⟨U⟩ met it: a counterexample to the
criterion on these instances.

⟨The counterexample(s): instance, mutant, diff, designated-test exit codes on the original and on
the mutant, PASS_TO_PASS exit code and summary, witness on both sides with exit codes, canary exit
code.⟩

**Finding 2: SWT-bench's criterion did not.** The fail-to-pass transition on the designated test
alone was satisfied by wrong fixes on ⟨K⟩ of 5 instances. A test meeting that criterion can be
satisfied by a wrong fix: one that does not fix the bug in general, or one that fixes the
reported case while breaking behaviour outside it.

Evidence: each is a mutant of the gold patch. The designated FAIL_TO_PASS test fails on the
original code and passes on the mutant. The mutant provably behaves differently from the gold patch
on its own witness, and the instance's negative-control canary is live.

- `psf__requests-5414` m4 (too narrow). `elif host.startswith((u'*', u'.')):` became
  `elif host == '.example.com':`. Designated test `test_invalid_url[InvalidURL-http://.example.com]`:
  exit 1 on the original, exit 0 on the mutant. Witness `requests.get('http://.evil.com')`: the
  gold patch raises `InvalidURL`, the mutant raises urllib3's `LocationParseError`, the original
  bug's symptom (witness exits 0 and 0). Canary exit 1, live. It does not fix the bug in general.
- `psf__requests-5414` m1. The same line became `elif host.startswith(u'.'):`. Designated test: exit 1
  on the original, exit 0 on the mutant. Witness `requests.get('http://*.example.com')`: the gold
  patch raises `InvalidURL`, the mutant proceeds to a network `ConnectionError` (exits 0 and 0).
  Canary exit 1, live. It fixes the reported case and drops the existing `*` check.
- `psf__requests-6028` m1. `if auth:` became `if netloc:`. Both designated tests: exit 1 on the
  original, exit 0 on the mutant. Witness `prepend_scheme_if_needed('http://example.org/', 'https')`:
  the gold patch returns `'http://example.org/'`, the mutant raises `TypeError` (exits 0 and 0).
  Canary exit 1, live. It fixes the reported case and crashes on URLs without auth.
- ⟨FAIL_TO_PASS survivors from the 30-mutant run, in the same form, or "none further"⟩

PASS_TO_PASS caught every one of these, so each instance is UNPINNED, not UNEARNED. These are the
repositories' own hand-written regression tests from the fixing pull requests, not generated ones.
That makes the point stronger: if the maintainers' regression test for the bug does not pin it, a
generated test need not either.

⟨Per-instance table from the 30-mutant run: distinguishable, equivalents discarded, survived
FAIL_TO_PASS, also survived PASS_TO_PASS, verdict, canary exit.⟩

The 10-mutant run, for reference: flask-5014 EARNED (1 distinguishable); requests-5414 UNPINNED
(7; 2 survived FAIL_TO_PASS; 0 both); requests-6028 UNPINNED (5; 1; 0); pytest-7432 INCONCLUSIVE
(0); pytest-7571 EARNED (7; 0; 0).

Every survivor's diff and rationale, beside the test that missed it, the witness on both sides
and its PASS_TO_PASS result, is in `docs/results.md`. The evidence for every fork is in
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
