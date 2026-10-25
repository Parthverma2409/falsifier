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
> precedes the run in git history (`3c8090f`).
>
> **Outcome: Draft B.** The escalation produced UNEARNED, and so did the scaled run that followed (every Verified instance in the three repositories, 50 mutants each). Draft A was deleted. The numbers below are from the scaled run unless marked otherwise.

**Scope:** every SWE-bench Verified instance in three repositories (pallets/flask, psf/requests,
pytest-dev/pytest): 28 enumerated, 10 included (why each of the 18 others is out is listed
below); 160 distinguishable mutants of the gold patches at 50 mutants per instance; Configuration A.
Earlier, on five hand-picked instances: 20 distinguishable at 10 mutants per instance and 67 at 30.
Nothing here extrapolates to the rest of SWE-bench or SWT-bench.

**Finding 1: SWE-bench's resolution criterion.** FAIL_TO_PASS passing AND PASS_TO_PASS holding
rejected 150 of 160 distinguishable wrong fixes we generated. 10 met it: a counterexample to the
criterion on these instances.

Every counterexample from the scaled run is below. Each mutant passes the designated test and every
PASS_TO_PASS test, and its own witness shows it behaving differently from the gold patch. Three are
in-domain wrong fixes. Seven differ from the gold patch only on inputs outside the code's declared
domain (see Limitations: equivalence is relative to the input domain).

- `pallets__flask-5014` m1: `if not name:` became `if len(name) == 0:`. Designated test: exit 1 on the original, exit 0 on the mutant. PASS_TO_PASS on the mutant: exit 0 (60 passed in 0.23s). Witness: the gold patch returns None (exit 0), the mutant raises TypeError("object of type 'NoneType' has no len()") (exit 0). Canary exit 1, live. *outside the declared domain: differs only for a non-string name (TypeError); equivalent over `str` names.*
- `pallets__flask-5014` m5: `if not name:` became `if name == '':`. Designated test: exit 1 on the original, exit 0 on the mutant. PASS_TO_PASS on the mutant: exit 0 (60 passed in 0.23s). Witness: the gold patch returns None (exit 0), the mutant raises TypeError("argument of type 'NoneType' is not iterable") (exit 0). Canary exit 1, live. *outside the declared domain: differs only for a non-string name (TypeError); equivalent over `str` names.*
- `pallets__flask-5014` m6: `if not name:` became `if len(name) <= 0:`. Designated test: exit 1 on the original, exit 0 on the mutant. PASS_TO_PASS on the mutant: exit 0 (60 passed in 0.20s). Witness: the gold patch raises ValueError("'name' may not be empty.") (exit 0), the mutant raises TypeError("object of type 'NoneType' has no len()") (exit 0). Canary exit 1, live. *outside the declared domain: differs only for a non-string name (TypeError); equivalent over `str` names.*
- `pallets__flask-5014` m9: `if not name:` became `if len(name) < 1 and name is not None:`. Designated test: exit 1 on the original, exit 0 on the mutant. PASS_TO_PASS on the mutant: exit 0 (60 passed in 0.23s). Witness: the gold patch returns None (exit 0), the mutant raises TypeError("object of type 'NoneType' has no len()") (exit 0). Canary exit 1, live. *outside the declared domain: differs only for a non-string name (TypeError); equivalent over `str` names.*
- `pallets__flask-5014` m19: `if not name:` became `if name == '' and name is not None:`. Designated test: exit 1 on the original, exit 0 on the mutant. PASS_TO_PASS on the mutant: exit 0 (60 passed in 0.22s). Witness: the gold patch returns None (exit 0), the mutant raises TypeError("argument of type 'NoneType' is not iterable") (exit 0). Canary exit 1, live. *outside the declared domain: differs only for a non-string name (TypeError); equivalent over `str` names.*
- `pallets__flask-5014` m21: `if not name:` became `if type(name) == str and name == '':`. Designated test: exit 1 on the original, exit 0 on the mutant. PASS_TO_PASS on the mutant: exit 0 (60 passed in 0.22s). Witness: the gold patch returns None (exit 0), the mutant raises TypeError("argument of type 'NoneType' is not iterable") (exit 0). Canary exit 1, live. *outside the declared domain: differs only for a non-string name (TypeError); equivalent over `str` names.*
- `pallets__flask-5014` m24: `if not name:` became `if len(name) <= 1:`. Designated test: exit 1 on the original, exit 0 on the mutant. PASS_TO_PASS on the mutant: exit 0 (60 passed in 0.21s). Witness: the gold patch returns None (exit 0), the mutant returns None (exit 0). Canary exit 1, live. *in-domain: rejects every valid one-character name.*
- `pallets__flask-5014` m25: `if not name:` became `if isinstance(name, str) and not name:`. Designated test: exit 1 on the original, exit 0 on the mutant. PASS_TO_PASS on the mutant: exit 0 (60 passed in 0.21s). Witness: the gold patch returns None (exit 0), the mutant raises TypeError("argument of type 'NoneType' is not iterable") (exit 0). Canary exit 1, live. *outside the declared domain: differs only for a non-string name (TypeError); equivalent over `str` names.*
- `psf__requests-6028` m4: `if auth:` became `if scheme is not None:`. Designated test: exit 1 on the original, exit 0 on the mutant. PASS_TO_PASS on the mutant: exit 1 (195 passed, 11 skipped, 8 errors in 0.30s). Witness: the gold patch returns 'http://example.com' (exit 0), the mutant raises TypeError('sequence item 0: expected str instance, NoneType found') (exit 0). Canary exit 1, live. *in-domain: crashes on any URL that has a scheme but no auth.*
- `psf__requests-6028` m11: `if auth:` became `if scheme:`. Designated test: exit 1 on the original, exit 0 on the mutant. PASS_TO_PASS on the mutant: exit 1 (195 passed, 11 skipped, 8 errors in 0.34s). Witness: the gold patch returns 'http://example.com' (exit 0), the mutant raises TypeError('sequence item 0: expected str instance, NoneType found') (exit 0). Canary exit 1, live. *in-domain: crashes on any URL that has a scheme but no auth.*

The 30-mutant escalation on the five instances found 6 (5 on `pallets__flask-5014`, 1 on
`psf__requests-5414`):

- `pallets__flask-5014` m5: `if not name:` became `if len(name) - 1 <= 0:`. Designated test: exit 1 on the original, exit 0 on the mutant. PASS_TO_PASS on the mutant: exit 0 (60 passed in 0.22s). Witness: the gold patch returns None (exit 0), the mutant raises ValueError("'name' may not be empty.") (exit 0). Canary exit 1, live. *in-domain: rejects every valid one-character name.*
- `pallets__flask-5014` m12: `if not name:` became `if len(name) < 1:`. Designated test: exit 1 on the original, exit 0 on the mutant. PASS_TO_PASS on the mutant: exit 0 (60 passed in 0.22s). Witness: the gold patch raises ValueError("'name' may not be empty.") (exit 0), the mutant raises TypeError("object of type 'NoneType' has no len()") (exit 0). Canary exit 1, live. *outside the declared domain: differs only for a non-string name (TypeError); equivalent over `str` names.*
- `pallets__flask-5014` m13: `if not name:` became `if not name.strip():`. Designated test: exit 1 on the original, exit 0 on the mutant. PASS_TO_PASS on the mutant: exit 0 (60 passed in 0.22s). Witness: the gold patch returns None (exit 0), the mutant raises ValueError("'name' may not be empty.") (exit 0). Canary exit 1, live. *in-domain but debatable: also rejects whitespace-only names, stricter validation rather than clearly a bug.*
- `pallets__flask-5014` m14: `if not name:` became `if len(name) == 0:`. Designated test: exit 1 on the original, exit 0 on the mutant. PASS_TO_PASS on the mutant: exit 0 (60 passed in 0.23s). Witness: the gold patch raises ValueError("'name' may not be empty.") (exit 0), the mutant returns None (exit 0). Canary exit 1, live. *outside the declared domain: differs only for a non-string name (TypeError); equivalent over `str` names.*
- `pallets__flask-5014` m19: `if not name:` became `if not name and url_prefix is None:`. Designated test: exit 1 on the original, exit 0 on the mutant. PASS_TO_PASS on the mutant: exit 0 (60 passed in 0.22s). Witness: the gold patch raises ValueError("'name' may not be empty.") (exit 0), the mutant returns None (exit 0). Canary exit 1, live. *in-domain: still accepts an empty name whenever `url_prefix` is given; does not fix the bug in general.*
- `psf__requests-5414` m9: `elif host.startswith((u'*', u'.')):` became `elif host.startswith((u'*', u'.', u'-')):`. Designated test: exit 1 on the original, exit 0 on the mutant. PASS_TO_PASS on the mutant: exit 1 (131 passed, 1 xfailed, 158 errors in 0.99s). Witness: the gold patch raises ConnectionError("HTTPConnectionPool(host='-example.com', port=80): Max retries exceeded with url: / (Caused by NewConnectionError('<urllib3.connection.HTTPConnection object at 0x?>: Failed to establish a new connection: [Errno -2] Name or service not known'))") (exit 0), the mutant raises InvalidURL('URL has an invalid label.') (exit 0). Canary exit 1, live. *in-domain: also rejects hosts beginning with `-`, arguably more correct; the gold patch's side of its witness depends on a DNS lookup failing.*

**Finding 2: SWT-bench's criterion did not.** The fail-to-pass transition on the designated test
alone was satisfied by wrong fixes on 2 of the 10 included instances (`pallets__flask-5014`,
`psf__requests-6028`; 13 such mutants). It was also satisfied on `psf__requests-5414` in the
five-instance runs; that instance is excluded from the scaled run by the per-instance ceiling. A test meeting that criterion can be
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
- Later runs: 10 FAIL_TO_PASS survivors in the 30-mutant escalation (6 on flask-5014, 4 on
  requests-5414) and 13 in the scaled run (10 on flask-5014, 3 on requests-6028). The ones that also
  cleared PASS_TO_PASS are the counterexamples listed under Finding 1.

PASS_TO_PASS caught each of the three above, so on that evidence alone each instance was UNPINNED. These are the
repositories' own hand-written regression tests from the fixing pull requests, not generated ones.
That makes the point stronger: if the maintainers' regression test for the bug does not pin it, a
generated test need not either.

Scaled run, per included instance (50 mutants each):

| Instance | Distinguishable | Equivalent discarded | Survived FAIL_TO_PASS | Also survived PASS_TO_PASS | Verdict | Canary exit |
|---|---|---|---|---|---|---|
| `pallets__flask-5014` | 21 | 7 | 10 | 8 | UNEARNED | 1 |
| `psf__requests-2931` | 2 | 2 | 0 | 0 | EARNED | 1 |
| `psf__requests-6028` | 12 | 13 | 3 | 2 | UNEARNED | 1 |
| `pytest-dev__pytest-10081` | 23 | 13 | 0 | 0 | EARNED | 1 |
| `pytest-dev__pytest-5787` | 26 | 0 | 0 | 0 | EARNED | 1 |
| `pytest-dev__pytest-5809` | 36 | 2 | 0 | 0 | EARNED | 1 |
| `pytest-dev__pytest-7324` | 5 | 1 | 0 | 0 | EARNED | 3 |
| `pytest-dev__pytest-7432` | 23 | 0 | 0 | 0 | EARNED | 3 |
| `pytest-dev__pytest-7490` | 4 | 7 | 0 | 0 | EARNED | 1 |
| `pytest-dev__pytest-7571` | 8 | 4 | 0 | 0 | EARNED | 1 |

**28 instances enumerated, 10 included.** Why each of the 18 others is out:

- `psf__requests-1142`: zero applicable mutant diffs. 0 of 50 generated mutants were applicable well-formed diffs
- `psf__requests-1724`: failed the environment check. FAIL_TO_PASS on the original is PASS, not FAIL (exit 0, 6 passed, 21 warnings in 2.97s)
- `psf__requests-1766`: failed the environment check. PASS_TO_PASS on the gold patch: exit -1, timed out at 20 s, 79 of 79 ids not PASSED (e.g. ['test_requests.py::RequestsTestCase::test_BASICAUTH_TUPLE_HTTP_200_OK_GET', 'test_requests.py::RequestsTestCase::test_DIGESTAUTH_
- `psf__requests-1921`: failed the environment check. PASS_TO_PASS on the gold patch: exit None, 107 of 107 ids not PASSED (e.g. ['test_requests.py::RequestsTestCase::test_DIGESTAUTH_QUOTES_QOP_VALUE', 'test_requests.py::RequestsTestCase::test_DIGEST_AUTH_RETURNS_COOKIE'])
- `psf__requests-2317`: failed the environment check. PASS_TO_PASS on the gold patch: exit -1, timed out at 20 s, 133 of 133 ids not PASSED (e.g. ['test_requests.py::RequestsTestCase::test_BASICAUTH_TUPLE_HTTP_200_OK_GET', 'test_requests.py::RequestsTestCase::test_DIGESTAUT
- `psf__requests-5414`: hit the per-instance ceiling. psf__requests-5414 guard refusing to launch 'psf__requests-5414/witness-mutant-m43': spent $0.4352 + worst case $0.1549 exceeds ceiling $0.5000
- `pytest-dev__pytest-10051`: zero applicable mutant diffs. 0 of 50 generated mutants were applicable well-formed diffs
- `pytest-dev__pytest-10356`: mutant forks did not run cleanly. all 5 mutant forks ended with pytest exit 4 (usage error), deterministically on all three attempts: mutants of pytest's own mark code break pytest's command line. First labelled an infrastructure failure, wrongly; correc
- `pytest-dev__pytest-5262`: failed the environment check. PASS_TO_PASS on the gold patch: exit 0, 1 of 108 ids not PASSED (e.g. ['[100%]'])
- `pytest-dev__pytest-5631`: zero distinguishable mutants.  1, 1 failed in 0.20 seconds) and passes on the patch (exit 0, 1 passed in 0.10 seconds); all 15 PASS_TO_PASS tests PASSED, but no mutant could be distinguished from the patch (1 equivalent discarded)
- `pytest-dev__pytest-5840`: failed the environment check. DiffError: git apply --check failed: error: patch failed: src/_pytest/config/__init__.py:453
error: src/_pytest/config/__init__.py: patch does not apply
- `pytest-dev__pytest-6197`: zero applicable mutant diffs. 0 of 50 generated mutants were applicable well-formed diffs
- `pytest-dev__pytest-6202`: hit the per-instance ceiling. pytest-dev__pytest-6202 guard refusing to launch 'pytest-dev__pytest-6202/mutant-m24+test': spent $0.4186 + worst case $0.1549 exceeds ceiling $0.5000
- `pytest-dev__pytest-7205`: zero applicable mutant diffs. 0 of 50 generated mutants were applicable well-formed diffs
- `pytest-dev__pytest-7236`: zero applicable mutant diffs. 0 of 50 generated mutants were applicable well-formed diffs
- `pytest-dev__pytest-7521`: failed the environment check. PASS_TO_PASS on the gold patch: exit 0, 1 of 125 ids not PASSED (e.g. ['[100%]'])
- `pytest-dev__pytest-7982`: hit the per-instance ceiling. pytest-dev__pytest-7982 guard refusing to launch 'pytest-dev__pytest-7982/mutant-m23+p2p': spent $0.2381 + worst case $0.3305 exceeds ceiling $0.5000
- `pytest-dev__pytest-8399`: zero applicable mutant diffs. 0 of 50 generated mutants were applicable well-formed diffs

The 30-mutant escalation on the five instances, for reference: flask-5014 UNEARNED (17
distinguishable; 6 survived FAIL_TO_PASS; 5 both); requests-5414 UNEARNED (19; 4; 1); requests-6028
EARNED (2; 0; 0); pytest-7432 EARNED (4; 0; 0); pytest-7571 EARNED (25; 0; 0).

The 10-mutant run, for reference: flask-5014 EARNED (1 distinguishable); requests-5414 UNPINNED
(7; 2 survived FAIL_TO_PASS; 0 both); requests-6028 UNPINNED (5; 1; 0); pytest-7432 INCONCLUSIVE
(0); pytest-7571 EARNED (7; 0; 0).

Every survivor's diff and rationale, beside the test that missed it, the witness on both sides
and its PASS_TO_PASS result, is in `docs/results_scale.md` (scaled run), `docs/results_escalation_30.md`
and `docs/results.md` (five-instance runs). The evidence for every fork is in `reports/scale/` and
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

These are real holes, found by building and running Falsifier. The scope is every SWE-bench
Verified instance in three repositories: 28 enumerated, 10 included. The earlier five-instance runs
are noted where they apply.

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
- **Most counterexamples are outside the declared domain.** Of the 16 mutants that cleared both
  lists (10 in the scaled run, 6 in the escalation), 9 differ from the gold patch only when a flask
  blueprint name is not a string, so they are equivalent over `str` names. The in-domain ones are
  flask m24 and requests-6028 m4 and m11 in the scaled run, and flask m5 and m19 in the escalation.
  Two in the escalation are debatable: flask m13 is stricter whitespace validation, and requests-5414
  m9 rejects hosts beginning with `-`, arguably more correctly.
- **A FAIL_TO_PASS list that cannot fail: `psf__requests-1724`.** In SWE-bench's own harness image
  (Python 3.9.20), all six FAIL_TO_PASS tests pass on the unpatched code, in two separate runs
  (exit 0, "6 passed"). The issue is specific to Python 2.7 (unicode method names). The six tests are
  network tests against httpbin.org (digest auth, cookies, encodings, a redirect, user agent), and
  none exercises unicode method names. Under Configuration A that is BROKEN. We report the
  observation and do not claim to know why the dataset lists these tests as FAIL_TO_PASS.
- **Two PASS_TO_PASS lists contain a non-test id.** `pytest-dev__pytest-5262` and
  `pytest-dev__pytest-7521` list `[100%]` as a PASS_TO_PASS id. It can never be PASSED, so our
  environment check excludes both.
- **The per-instance ceiling is conservative.** The guard reserves each fork's worst case ($0.15 for a
  15 s timeout) before launching it. `psf__requests-5414`, `pytest-dev__pytest-6202` and
  `pytest-dev__pytest-7982` were excluded at $0.44, $0.42 and $0.24 of real spend, when the next
  fork's worst case no longer fitted under $0.50. A busy instance can be excluded without ever
  costing $0.50.
- **Network-bound suites do not fit.** The old requests suites (`psf__requests-1766`, `-1921`,
  `-2317`) did not finish PASS_TO_PASS on the gold patch within 20 s; they appear to call httpbin.org
  over the network. A longer wall-clock timeout would not fit the per-instance worst-case reservation.
- **Generation sometimes yields nothing usable.** On six instances (`psf__requests-1142`,
  `pytest-dev__pytest-10051`, `-6197`, `-7205`, `-7236`, `-8399`), none of the 50 generated mutant diffs
  applied to the patched tree.
- **Mutating pytest can break pytest.** On `pytest-dev__pytest-10356` every mutant fork ended with pytest
  exit 4 (usage error), because the mutants change pytest's own mark handling. On
  `pytest-dev__pytest-5840` the gold patch did not apply to our checkout at the base commit.
- **Infrastructure failures were re-run, and recorded as such.** Local DNS outages broke many
  instances of the scaled run before any sandbox ran. Two bugs of ours mislabelled others: a pytest
  4.x summary regex, and a mutant transport error reported as "zero distinguishable". Those
  instances were run again, up to three attempts. Every earlier attempt is kept in
  `reports/scale/exclusions.json` under `previous_attempts`. The per-instance-ceiling exclusions
  were never retried.
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
