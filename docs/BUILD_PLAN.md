# Falsifier: build plan

Hand this to Claude Code. It is written to be executed in order, with a hard gate after
step 1 and acceptance criteria on every step.

---

## 0. Context

**What we are building.** Falsifier is a verdict service for AI-generated patches. Given a bug
and a candidate fix with its test, it decides whether that test actually constrains the fix. It
decides by executing things, never by asking a model.

**The claim it rests on.** A passing test is not evidence unless it would have failed on a wrong
fix.

**The verdicts.**

| Verdict | Means |
|---|---|
| EARNED | fails on original, passes on patch, no regressions, kills every mutant |
| BROKEN | passes on the original code; the test never reproduced the bug |
| UNFIXED | fails on the patch; the patch does not satisfy its own test |
| REGRESSED | passes, but the repo's existing suite breaks |
| UNEARNED | passes on the patch **and** on at least one mutant that does not fix the bug |

UNEARNED is the contribution. Everything else already exists somewhere.

**The output we are aiming at.** A table comparing the official benchmark verdict with ours:

| Instance | SWE-bench says | Falsifier says | Evidence |
|---|---|---|---|
| django__django-11099 | RESOLVED | EARNED | killed 12/12 mutants |
| astropy__astropy-12907 | RESOLVED | UNEARNED | mutant 7 survived: boundary flipped, test still passes |

**Governing rule, taken from Kelp.** The model proposes; execution decides. No function returns a
verdict unless it can cite a branch id, an exit code and a captured log. Nemotron may write
patches, tests and mutants. It never says whether something passed.

**Prior art to credit in the README, no code copied.**
- PatchProof (Apache-2.0): the red, patch, green loop and per-attempt evidence
- Kelp (MIT): evidence-gated findings
- CodeMore (MIT): pairing every rule with true-positive and false-positive fixtures

---

## 1. Constraints

- **Python 3.11+, on Linux.** Not Windows. The author previously lost a day to `fcntl` being
  Unix-only; assume anything in this space is Unix-only.
- **Execution runs on Nebius Sandboxes** via `contree-sdk`. Sandboxes are free during beta, so
  fork count is limited by wall-clock and the 50-concurrent cap, not by money.
- **Generation runs on Nebius Token Factory** with an NVIDIA Nemotron model. This is mandatory:
  hackathon rules require at least one NVIDIA open model. Budget is about $30, so use the
  smallest Nemotron that writes coherent diffs. List the catalogue and choose; do not hardcode a
  model id from memory.
- Token Factory exposes an OpenAI-compatible endpoint. Read the quickstart on the Sandboxes page
  for the exact `base_url`; verify rather than assume.
- `NEBIUS_API_KEY` from the environment. **No secrets in the repo, ever.**
- Public repo, open source licence, because the hackathon requires it.

---

## 2. Non-goals

Do not build these. Each one has been considered and rejected.

- **No Terraform, Kubernetes, AWS or any other cloud infrastructure.** Execution must run on
  Nebius to satisfy the rules, Sandboxes already provide isolation and orchestration, and
  standing up a cluster would consume the entire remaining build window while making the
  submission weaker, not stronger. If a future version needs scale, that is a line in
  "What's next", not work for this fortnight.
- No patch generator as a product. Generation is the subject under audit.
- No new benchmark. We consume SWE-bench and SWT-bench.
- No general evaluation framework other people configure.
- No hosted service, leaderboard or dashboard product.
- No languages other than Python.
- Not all 2,294 instances. Five to ten, named, from light repos.

---

## 3. Modules

```
falsifier/
  sandbox.py     Nebius client: create, checkpoint, fork, exec, collect
  instance.py    load a bench instance, build the repo, take the warm checkpoint
  generate.py    Nemotron: candidate patch, candidate test, N mutants
  verify.py      the five verdicts, by forking and executing
  evidence.py    every claim carries branch id, exit code, captured log
  report.py      verdict plus surviving mutants; JSON and one small HTML view
  official.py    reproduce the SWE-bench / SWT-bench verdict for comparison
  cli.py
  fixtures/      known-good and known-bad cases; the self-test
tests/
```

---

## 4. Build order

### Step 1. `sandbox.py` and the fork-timing probe. THIS IS A GATE.

Write the thinnest possible wrapper: create a sandbox, run a command, checkpoint, fork the
checkpoint, run a command in the fork, roll back, destroy.

Then a script `probe.py` that:
1. creates a sandbox from a Python image
2. installs a small package and writes a file, so the checkpoint is not empty
3. checkpoints
4. forks it N times for N in 1, 5, 10, 25, 50
5. runs `python -c "print(1)"` in each fork
6. prints wall-clock for checkpoint, per-fork, and total at each N

**Acceptance:** the timings are printed and recorded in `docs/probe.md`.

**Gate.** If a fork takes more than about 10 seconds, or concurrency does not actually help, stop
and report before writing anything else. The mutation step is only affordable if forking is
cheap. If it is not, Falsifier collapses to steps A to C, which is PatchProof on another runtime
and not worth entering. **Do not proceed past this step without reporting the numbers.**

### Step 2. `generate.py`. No sandbox needed, can be done while waiting for beta access.

Three functions against Nemotron on Token Factory:

- `propose_patch(issue_text, repo_context) -> unified diff`
- `propose_test(issue_text, repo_context) -> test file contents`
- `propose_mutants(patch, n) -> list[unified diff]`

The mutant prompt is the one that matters and deserves real thought. We do not want operator
flips. We want **plausible wrong fixes**: the off-by-one, the right shape with the wrong
condition, the fix that handles the reported case but not the general one, the one that silences
the symptom. Each mutant must still apply cleanly and still be a syntactically valid program.
Ask for a short rationale per mutant and keep it as evidence.

**Acceptance:** given one real SWE-bench issue, it returns a patch, a test, and 10 mutants that
all apply cleanly to the patched tree.

### Step 3. `instance.py`

Load a SWE-bench instance (repo, base commit, issue text, gold patch, FAIL_TO_PASS and
PASS_TO_PASS lists). Clone at the commit inside a sandbox, install dependencies, run the test
suite once to confirm the environment is sane, then checkpoint.

Cache the checkpoint id per instance. Building is the expensive part and must happen once.

**Acceptance:** five instances build and checkpoint; build time per instance recorded.

### Step 4. `verify.py`

From one warm checkpoint, fork for each of:

- original code + candidate test, expect FAIL, else BROKEN
- patched code + candidate test, expect PASS, else UNFIXED
- patched code + PASS_TO_PASS suite, expect no new failures, else REGRESSED
- for each mutant: mutant + candidate test, expect FAIL; any PASS means UNEARNED

Run mutant forks concurrently, respecting the 50 cap. Short-circuit the early verdicts: if BROKEN,
do not spend forks on mutants.

**Acceptance:** returns one verdict and the full set of branch results for a real instance.

### Step 5. `evidence.py` and `report.py`

Every result carries branch id, command, exit code, captured stdout and stderr, and duration.
`report.py` emits JSON plus a single static HTML page showing the verdict, the mutant grid, and
for each survivor its diff and rationale side by side with the test that failed to catch it.

**Acceptance:** the HTML page renders a real run and is legible on screen at recording resolution.
This page is what gets filmed.

### Step 6. `official.py`

> Revised 2026-10-25: reduced to the dataset's published label. See §6 and `docs/plan_deviations.md`.

Reproduce the official verdict: apply the gold or candidate patch, run FAIL_TO_PASS and
PASS_TO_PASS, apply the benchmark's own resolution criteria. Match their definitions exactly; read
the SWE-bench harness source rather than guessing.

**Acceptance:** on the gold patch for five instances, our official verdict agrees with the
published result. If it disagrees, investigate before proceeding; a disagreement is either a bug
in our harness or a finding, and we must know which.

### Step 7. `fixtures/` and the self-test

Four classes, at least two of each:

- fixes the bug, test pins it, expect EARNED
- fixes the bug, test does not pin it, expect UNEARNED
- does not fix the bug, test passes anyway, expect UNEARNED
- test never failed on the original, expect BROKEN

**Acceptance:** `pytest tests/` runs Falsifier against its own fixtures and all classify
correctly. This answers "who checks the checker" and is the single strongest moment in the demo.

### Step 8. Adversarial self-audit

> Revised 2026-10-25: reduced to hand-constructed cases plus a limitations section. See §6.

Use Nemotron to attack the oracle rather than the patch. Ask it to produce cases designed to fool
Falsifier: mutants that are semantically identical to the patch and should not count as survivors,
tests that pass for environmental reasons, patches that fix the bug by deleting the feature.

Record which attacks succeed. **Fix what can be fixed and document the rest as known limitations.**
A limitations section that names real holes is worth more than one that claims none.

### Step 9. The run and the write-up

Run the full pipeline on the chosen instances, including tests SWT-bench already marked
successful. Produce the comparison table. State the number plainly and scope it to the instances
tested. Do not generalise to the whole benchmark.

---

## 5. Submission deliverables

- Public repo, licence, README with prior art and limitations
- Demo video, YouTube or Vimeo, **only the first 3 minutes are reviewed**
- Working demo URL, or the HTML report hosted statically
- Feedback write-up on Sandboxes beta for the Most Valuable Feedback prize; keep notes with dates
  as you go rather than reconstructing at the end

## 6. Schedule

Deadline 30 October, 10:00 PDT. MPI submits on the 22nd; Devfest and travel take the 24th.

Revised 2026-10-25 (the original table is in git history). Reasons are in
`docs/plan_deviations.md`.

| Day | Date | Work |
|---|---|---|
| 1 | Sun 25 Oct | step 1 gate, latency and cost (done); step 2 `generate.py` |
| 2 | Mon 26 Oct | step 7 fixtures first; step 3 `instance.py` on the official SWE-bench images |
| 3 | Tue 27 Oct | step 4 `verify.py`, built and tested against the fixtures; step 5 evidence and report |
| 4 | Wed 28 Oct | rough video (the first 3 minutes); step 6 `official.py`; first run on the chosen instances |
| 5 | Thu 29 Oct | step 8 hand-constructed adversarial cases and limitations; step 9 run, write-up, final video, README |
| 6 | Fri 30 Oct | buffer until 10:00 PDT, not build time |

Changes from the original order and scope:

- **Fixtures (step 7) before `verify.py` (step 4).** The fixtures are the only cases with a known
  correct verdict, so they are the test harness for `verify.py`. They have to exist first.
- **Rough video on day 4**, so the final day refines a cut that already exists instead of making one.
- **`official.py` reports the dataset's published label** instead of reproducing SWE-bench's harness
  logic.
- **The adversarial audit (step 8) is hand-constructed cases plus a limitations section**, not
  Nemotron-generated attacks.
