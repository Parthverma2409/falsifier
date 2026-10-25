# Where reality differs from BUILD_PLAN.md

This is a dated log of places where the build plan's assumptions didn't match what the services and SDK actually do.
It doubles as raw material for the Sandboxes beta feedback write-up (BUILD_PLAN §5).

## 2026-10-25: step 0 service verification

**Environment.** The setup request said WSL2. The dev machine is native Fedora 43 (kernel
`7.1.13-100.fc43`). Nothing changes, because the plan already requires Linux. The repo lives at `~/falsifier`.

**§1 "Read the quickstart on the Sandboxes page for the exact base_url."** There are two different URLs:

| Service | base_url | Source |
|---|---|---|
| Token Factory inference (OpenAI-compatible) | `https://api.tokenfactory.nebius.com/v1/` | https://docs.tokenfactory.nebius.com/quickstart.md |
| Sandboxes (contree-sdk) | `https://api.tokenfactory.nebius.com/sandboxes/` | SDK default, `ContreeEndpoint.TOKEN_FACTORY_SANDBOXES` in contree-sdk 0.3.6 |

**§1 "`NEBIUS_API_KEY` from the environment."** That isn't enough. contree-sdk also requires
`NEBIUS_PROJECT_ID`, which it sends as the `Project` header. `NEBIUS_AI_PROJECT`, the variable the CLI uses, does not replace it.
Both variables are listed in `.env.example`.

**§1 "Sandboxes are free during beta, so fork count is limited by wall-clock … not by money."**
I couldn't confirm this. Every run returns a nonzero `result.cost`, for example `4.975e-05` for a trivial
`cat`, and the unit isn't documented. The docs say not to reconcile invoices against `cost`.
Watch the billing page after the step 1 probe.

**§1 "Sandboxes beta access requested 15 Oct, may be pending."** Access is live. `whoami` reports these permissions:
`import, spawn, spawn_disposable, list, cancel, set_image_tag`. These are the limits:

| Limit | Value |
|---|---|
| `instance_max_concurrency` | 50, confirming the plan's cap |
| `instance_max_timeout` | 3600 s |
| `images_import_max_concurrency` | 8 |
| `images_import_max_timeout` | 3600 s |
| `instance_max_layer_bytes` | 12 GiB |

**§3/§4 step 1 "create, checkpoint, fork, exec, roll back, destroy".** The SDK has no create, destroy or
rollback calls. The model is image UUIDs, as set out in `docs/sandbox_api.md`:

| Plan verb | What it is in the SDK |
|---|---|
| create | `images.oci(ref)` (import if missing) or `images.use(uuid)` |
| exec | `run(...)` |
| checkpoint | `run(..., disposable=False)`, which returns a new `.uuid` |
| fork | `run()` again on the same checkpoint |
| roll back | `images.use(old_uuid)` |
| destroy | no API. Disposable runs leave nothing behind; kept images are retained for 180 days and can't be deleted |

`sandbox.py` will have to define these verbs itself.

**§4 step 1 "creates a sandbox from a Python image".** On a fresh project, `images.use(tag, strict=True)` returns 404
`Image not found by tag`. Use `images.oci("python:3.x-slim")`, which imports the image once and leaves it tagged in the project.

**§4 step 1 gate, preliminary data (not the probe).** A checkpoint of a one-line write on `alpine:3.19` took about 1.0 s.
Two forks run in parallel with `asyncio.gather` took about 1.9 s in total. Forks were isolated, and the checkpoint was unchanged afterwards.
That is well under the 10 s per fork threshold, but the step 1 probe at N = 1…50 on a Python image is still the gate.

**§4 step 5 "captured stdout and stderr".** The SDK truncates each stream at **64 KiB by default**
(`ContreeConfig.default_truncate_output_at = 65535`), even though the server allows 1 MiB by default and 10 MiB at most.
pytest logs will be cut short unless `run(..., truncate_output_at=...)` is set.
`ContreeResult.truncated` reports when a stream was cut.

**§1 "smallest Nemotron that writes coherent diffs".** The two cheapest models,
`nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` and `nvidia/Nemotron-3_5-Lightning`, both at $0.06 in / $0.24 out per 1M tokens,
are reasoning models that **think by default**. Thinking tokens bill as output.
- With `max_tokens=64`, Nano returned `content=None` and Lightning returned its thinking as `content`.
- Sending `extra_body={"chat_template_kwargs": {"enable_thinking": False}}` produced a clean answer in 2 output tokens.

`generate.py` must either set this or budget for the thinking tokens.

**SDK warning noise.** `whoami` reports `token_expiration` about 300 s ahead, so the SDK logs
`Token expires in 0 hours` on every client. Runs are unaffected.

**§6 schedule.** It is 25 Oct and step 1, the gate, has not run, while the plan has steps 1–4 finished by 22 Oct.
Beta access is live, so step 1 is unblocked.

## 2026-10-25: step 1 gate amended to latency AND cost

**Original gate (BUILD_PLAN §4 step 1):** wall clock only. Stop if a fork takes more than about 10 s,
or if concurrency doesn't help.

**Why it changed:** the plan assumed Sandboxes are free during beta (§1). That assumption is wrong,
or at least unverified. Every run reports a nonzero `result.cost` with no documented unit
(see the step 0 entry above). If cost scales with runtime, the plan's fan-out budget
breaks: a Django test suite runs for minutes, not milliseconds.

**Amended gate (Parth, 2026-10-25):** step 1 passes only if both conditions hold.

1. **Latency:** per-fork wall clock is under about 10 s, and running forks in parallel cuts total wall clock.
2. **Cost:** the projected Sandboxes cost of the full run (5 instances × 13 forks at realistic test
   durations, plus builds) is known in real currency and fits the ~$30 total budget alongside
   generation.

Establishing the unit means comparing the probe's summed `cost` against the Token Factory
console's billing page before and after the run.

The probe records `cost` on every run and runs `sleep 1`, `sleep 60` and a 10 s CPU-busy fork, so it
can tell fixed per-run cost from wall-time or CPU-time billing. Results are in `docs/probe.md`.

## 2026-10-25: step 1 probe results against the amended gate

The full data is in `docs/probe.md`, with raw records in `docs/probe_raw.json`.

**Latency: pass.** Forks of a `python:3.12-slim` checkpoint running `python -c "print(1)"`:

| N | Total wall clock | Slowest fork |
|---:|---:|---:|
| 1 | 0.9 s | 0.9 s |
| 5 | 1.5 s | 1.5 s |
| 10 | 1.7 s | 1.7 s |
| 25 | 2.6 s | 2.6 s |
| 50 | 2.9 s | 2.9 s |

All 91 runs exited 0. Running in parallel took 2.9 s for 50 forks, against about 46 s one after another. The checkpoint (`pip install six` plus a file write) took 3.2 s.

**Cost: billed, and it scales with CPU time.**
- **§1 "Sandboxes are free during beta" is wrong.** Across the probe run the console billing rose by about $0.13, against an SDK-reported total of 0.1316. `cost` is in USD.
- **Model:** cost = $4.2e-05 per run + **$0.0103 per CPU-second** (user+sys). R² = 1.000 over 95 runs; fitting against wall time gives R² = 0.02.
- **Idle time is free:** `sleep 60` cost the same as `sleep 1`, about $0.00007.
- **CPU time is not:** a 10 CPU-second busy loop cost $0.104.
- Each `print(1)` fork cost about $0.00018, most of that Python startup CPU.

**What this means for the budget.** $30 buys about 2,900 CPU-seconds of sandbox time in total, before
generation and builds. For 5 instances that is roughly 580 CPU-s per instance across all 13 forks and the build.
- A full PASS_TO_PASS run of a large suite can use more than that on its own.
- Parallel test workers don't help: they burn CPU-seconds faster than wall-seconds, so they save time but not money.

**Gate status: latency passes. Cost passes only if per-instance CPU stays at roughly ≤ 500 CPU-s.**
That can't be confirmed until the real per-fork CPU time of a chosen instance is measured.
This is Parth's call; no work past step 1 has started.

## 2026-10-25: default-timeout exposure, and the rails added for it (Sandboxes feedback)

**The footgun.** Sandboxes bill about **$0.0103 per CPU-second** (`docs/probe.md`). The unit isn't documented anywhere: the docs only
say not to reconcile invoices against `cost`. Meanwhile, a `run()` without `timeout=` gets a long one by default:

- **contree-sdk 0.3.6 default:** `ContreeConfig.operation_timeout = 1000.0` s, sent as the spawn
  `timeout` whenever `run()` gets none (`image_like/_base.py`, `_await`). One busy core left at that default
  costs **$10.33**, a third of this project's budget, from a single fork.
- **Account maximum:** `whoami` reports `instance_max_timeout = 3600` s. A run at that ceiling costs
  **$37.17 per busy core**, more than the whole budget.
- **Cores multiply it:** cost follows user+sys CPU time summed over threads, so a multi-threaded runaway
  (parallel test workers, a compiled extension spinning) multiplies the figure.
- **Mutants are designed to be wrong:** they will include wrong loop conditions on purpose, so
  an infinite loop is an expected input, not an edge case.
- **We were already exposed:** all 91 fan-out forks in the 2026-10-25 probe ran at the 1000 s default.
- **Related:** the SDK truncates stdout/stderr at 64 KiB by default, so long test logs are cut short
  unless `truncate_output_at` is set.

**Feedback for the Sandboxes team:**
- document the `cost` unit and the billing basis (CPU-seconds, not wall);
- give `run()` a short default timeout, or require one;
- offer a per-project spend cap enforced server-side;
- name `.elapsed` / `resources.elapsed_time` for what it is (CPU time).

**Rails added (all sandbox runs now go through `falsifier.sandbox.guarded_run`):**
- **Explicit timeout on every run.** `timeout_s` is a required keyword, an int in (0, `max_timeout_s` = 600]. A test
  (`tests/test_rails.py`) parses every file in `falsifier/` and `scripts/` and fails on any `.run(` call
  without `timeout=`. It caught `scripts/probe.py` and `scripts/sandbox_check.py`, which are now fixed.
- **Spend ceiling, checked before each launch.** `falsifier/config.py` `SpendLimits(ceiling_usd, cores)`
  can be overridden by `FALSIFIER_SPEND_CEILING_USD` / `FALSIFIER_SANDBOX_CORES`.
  - Each run reserves its worst case, `$4.2e-05 + $0.0103 × timeout_s × cores`, before launch.
  - If in-flight reservations leave no room, the run waits. If completed spend leaves no room, the run raises
    `SpendCeilingExceeded` and launches nothing.
  - The ceiling therefore can't be crossed even if every in-flight fork hits its timeout.
  - The trade-off is that tight timeouts are what buy concurrency, which is the right pressure.
- **Cost on every evidence record.** `falsifier.evidence.RunRecord` has `cost_usd` (SDK-reported) and
  `cost_upper_bound_usd` (the reserved worst case). A failed run with no reported cost is
  charged to the guard at its upper bound.

## 2026-10-25: cost gate measured on real instances

Full data is in `docs/probe_instances.md`. The cost model in `docs/probe.md` is corrected to 1 build +
1 regression fork + 12 single-test forks. PASS_TO_PASS never runs against a mutant.

**Measured** on the official SWE-bench Verified harness images, with every run pinned to one CPU:

| Instance | Build | Targeted test | PASS_TO_PASS | Per instance |
|---|---:|---:|---:|---:|
| `pallets__flask-5014` | 1.94 CPU-s, $0.020 | 0.28 CPU-s, $0.0030 | 59 ids, 0.39 CPU-s, $0.0041 | **$0.060** |
| `psf__requests-5414` | 0.75 CPU-s, $0.0077 | 0.43 CPU-s, $0.0046 | 130 ids, 0.62 CPU-s, $0.0064 | **$0.069** |
| `pytest-dev__pytest-7432` | 2.35 CPU-s, $0.024 | 0.25 CPU-s, $0.0027 | 77 ids, 1.88 CPU-s, $0.019 | **$0.075** |

Five instances cost about $0.30–0.40 of sandbox time. **The cost gate passes with roughly two orders
of magnitude of headroom** for these repos. Django, sympy, astropy and matplotlib were excluded by
design and were not measured.

**Overhead dominates the single-test forks.**
- An empty test in the same directory costs 72–73% of the targeted test's CPU for flask and pytest,
  and 42% for requests. Interpreter start alone is 3–6%.
- The rest is pytest start-up, plugins and conftest.
- The test bodies themselves take 0.07–0.25 CPU-s.

**Findings that change later steps:**
- **PASS_TO_PASS ids are not runnable node ids.** SWE-bench builds them from the `pytest -rA` log, truncated at the first space,
  for example `test_xfail_raises[TypeError-TypeError-*1`. Passing them to pytest gives exit 4, "not found".
  The harness runs the files the test patch touches and grades by parsing the log. `verify.py` and
  `official.py` must do the same. Doing it that way, all P2P ids were PASSED in the log: 59/59, 130/130 and 77/77.
- **"PASS_TO_PASS trimmed to the touched module" saves nothing.** P2P is already scoped to the test files the
  test patch touches. In 24 of the 28 Verified instances in flask, requests and pytest, that is a single module. In
  the 4 multi-module instances (pytest 5262, 5787, 6197, 7521) the targeted module alone would undercount P2P.
- **The official images are the cheapest build.** `images.oci("swebench/sweb.eval.x86_64.<id>:latest")` imported in
  1–4 s per ~1 GB image and isn't SDK-billed. The console moved by about $0.16 against $0.157 SDK-reported, so imports are free
  or negligible. The "build" is then only the eval script's install step: 0.7–2.3 CPU-s. This beats the
  plan's clone-and-install (step 3), and the environment is exactly the official one (step 6).
- **Sandboxes run with no `$HOME`.** Commands like `git config --global` fail with exit 128 (attempt 1). Set `HOME=/root`.
- **Avoid `conda activate` per fork.** It costs 0.18 CPU-s, about as much as the empty test. Putting
  `/opt/miniconda3/envs/testbed/bin` on `PATH` gives the same environment.
- **requests installs non-editable** (`pip install .`), but tests import `/testbed/requests` from source,
  so patched forks don't need a reinstall.

**Rail behaviour seen in the field (attempt 2).** Two runs failed during file upload with `ApiTimeoutError`
on `POST /v1/files` (the SDK's 10 s transport timeout), before any operation started.
- With no reported cost, the guard charged them their $0.31 worst case each and correctly refused
  the P2P phase.
- Real spend was unaffected. Uploads now happen before the reservation, with retries, and the transport
  timeout is 30 s.

**What the whole measurement cost:** $0.157 SDK-reported over 44 distinct runs in four attempts, plus
the $0.00006 cores check. The console showed about $0.16.

## 2026-10-25: schedule revised, and why the fixtures moved

The revised table is in BUILD_PLAN §6.

**Why fixtures (step 7) now come before `verify.py` (step 4).** The fixtures are the only cases whose
correct verdict is known in advance. The plan had them build `verify.py` first and add the fixtures
as a self-test at the end, but then `verify.py` would be written with no oracle. Every early
verdict on a real instance would be unfalsifiable, and a bug in the verdict logic would surface only
on day 5, inside the run that produces the submission's numbers. With the fixtures first, they
become `verify.py`'s test harness from its first line: each verdict path has to classify known
EARNED, UNEARNED and BROKEN cases correctly before it ever runs on a SWE-bench instance.

**Other scope changes, recorded as decided:**
- Rough video on day 4.
- `official.py` reduced to the dataset's published label.
- The adversarial audit reduced to hand-constructed cases plus a limitations section.

**Open question for day 4 (not a decision).** SWE-bench Verified publishes a label only for the
gold patch, and that label is RESOLVED by construction, since FAIL_TO_PASS and PASS_TO_PASS were
derived from it. The dataset publishes nothing for Nemotron-generated patches. So the "SWE-bench
says" column for a generated patch needs one of:
- the harness, which this change dropped;
- a published leaderboard submission's per-instance results;
- the column restricted to gold patches.

## 2026-10-25: step 2, `generate.py`

The live run is in `docs/generate_demo.md`, and the tests are in `tests/test_generate.py`, which makes no live calls.

**Config.** The instructions said to read the base_url "recorded in the README", but the README
didn't record one. Base_url, model and prices now live in `falsifier/config.py` (`GenerationConfig`, with env
overrides), and the README lists them from there. Base_url `https://api.tokenfactory.nebius.com/v1/`
comes from the Token Factory quickstart; model `nvidia/Nemotron-3_5-Lightning`, $0.06/$0.24 per 1M tokens.

**Signatures.**
- `propose_patch` and `propose_mutants` take a keyword-only `repo_dir`, because validation needs a tree to
  `git apply --check` against.
- `propose_mutants` also takes an optional `issue_text`.
- The cache key covers model, messages, max_tokens, temperature and the thinking flag. That is more
  than "prompt plus model id", so a changed sampling parameter can't return a stale answer.

**What the live runs on `pallets__flask-5014` showed** (Lightning, thinking off):
- **The model writes mutants as alternative fixes to the original code**, whichever source it is
  shown and whatever base it is told to use. Prompt v1 asked for diffs against the patched source;
  9 of 10 came back against the original. Validation now accepts either base, and the returned diff
  is regenerated by git from the patched tree, so it always applies to the patched tree, as step 2
  requires.
- **It wraps labels in markdown** (`**KIND:**`), so the parser now tolerates it.
- **Apply rate is dominated by sampling variance, not the prompt.** In a bake-off of 3 samples × 2
  prompts, mutants that applied out of 10:

  | Prompt | Samples |
  |---|---|
  | v2 | 3, 10, 8 |
  | v3 | 10, 2, 0 |

- **59 of 64 apply failures were blank-line or indentation slips in context lines**, with the code
  intent intact. 5 were real content mismatches. Under the specified rule (drop failures, re-ask at
  most twice), three final-prompt runs returned 10, 4 and 0 mutants.
- **Parth chose whitespace re-anchoring.** When git rejects a diff even with `--recount`, each hunk's
  non-blank original-side lines must match exactly one place in the source, ignoring whitespace.
  Context and removed lines are taken from the source, added lines verbatim. The result is
  regenerated by git, must apply strictly, and is recorded as `repaired`, separate from `clean`.
  Ambiguous or content-mismatched hunks are still rejected. With it, the 0-of-10 run's own
  round-0 answer yields 8 accepted, and 9 of 10 after two re-asks.
- **Equivalent mutants.** Prompt v2 produced 3 of 10 mutants equivalent to the patch for string input
  (`name == ""`, `len(name) < 1`, `len(name) <= 0`), and two rationales said so. An equivalent mutant
  survives every test and would produce a false UNEARNED. Prompt v3 requires each mutant to differ
  from the patch on a concrete input it names. Still, 3 of the 9 accepted v3 mutants are bare
  inversions of the guard (`if name:`), despite the prompt forbidding it, and rationales often
  run past one sentence.
- **Equivalence can't be decided in `generate.py` without judging behaviour**, which this module may
  not do. It belongs to `verify.py` and the step 8 limitations: a mutant that survives must be
  shown to differ from the patch on some input before its survival counts.
- **`propose_patch` failed on flask-5014: 3 asks, 0 valid diffs.** It inserted the guard into about ten
  methods with invented context. At temperature 0.2 the re-asks returned the identical 3,049-token
  answer, so re-asks now raise the temperature (base, +0.3, +0.6), but the patch still failed.
  Candidate patches are the subject under audit (§2 non-goal), so this is reported, not tuned.
  `propose_test` worked first time.
- **The openai SDK's default request timeout is 600 s**, and one smoke run hung on it. It is now 120 s
  with 2 retries (`GenerationConfig.request_timeout_s`).

**Generation spend for step 2:** $0.027 across 25 calls, including mutant runs, the bake-off and the
patch/test smoke test. One ten-mutant run costs $0.0013–0.0031.

## 2026-10-25: phase 1 (verify, evidence, report, fixture suite)

The verdict pages are in `reports/fixtures/` (open `index.html`); the code is in `falsifier/verify.py`, `evidence.py`, `report.py` and `instance.py`.

**How it behaves (Configuration A: mutate the gold patch, audit the benchmark's FAIL_TO_PASS tests):**
- **Baseline forks run in parallel:** original + test, patched + test, and the single PASS_TO_PASS fork. Precedence follows BUILD_PLAN step 4: BROKEN, then UNFIXED, then REGRESSED. All three short-circuit, so no mutant forks are spent on them. The PASS_TO_PASS fork has already run in parallel by then, and it is recorded in the evidence because it was paid for.
- **Mutant forks run the targeted test only**, are disposable, and run in parallel (cap 50).
- **UNEARNED is conjunctive.** A surviving mutant counts only if its own witness, run in a fork of the patch and a fork of the mutant, gives a different value or exception. Otherwise it is discarded as equivalent and counted separately.
- **INCONCLUSIVE is not one of the plan's five verdicts.** It is reported when a run that a verdict needs did not complete: platform error, pytest exit 3, 4 or 5, or no distinguishable mutant.
- **Every verdict carries complete evidence:** branch id, command, exit code, stdout and stderr with an explicit truncate_output_at, duration, CPU-s and cost. `Verdict.__post_init__` refuses to construct one without it.
- **No model is called** anywhere in verify.
- **Every run is pinned to one CPU** with `taskset -c 0` and given an explicit timeout sized from `docs/probe_instances.md`:

  | Run | Timeout |
  |---|---:|
  | Test | 15 s |
  | P2P | 45 s |
  | Witness | 10 s |
  | Build | 90 s |

- **The $8 ceiling is global:** `runs/spend_ledger.jsonl` persists spend across processes.
- **Patches and mutants are uploaded as file overlays** into forks of the warm checkpoint, not applied with `git apply`.

**Fixtures.** There are ten: the plan's four classes with two each, plus UNFIXED and REGRESSED. They
were committed in `3115bc3`, before any verify code existed.
- Their mutants are hand-written, each with a witness and an expected status, so the oracle is
  deterministic. Nemotron mutants are not used in fixtures.
- **Step 7 acceptance deviation (needs sign-off):** "`pytest tests/` runs Falsifier against its own
  fixtures". `tests/test_verify.py` runs all ten through verify locally (real pytest, no sandbox,
  free) on every `make test`. The sandbox version runs only when `FALSIFIER_SANDBOX_TESTS=1`,
  because it spends money (about $0.10).

**Disagreement (reported, not fixed):** `earned_clamp` mutant m4, `if x > hi - 1:`.
- **Expected:** killed. **Produced:** equivalent.
- The verdict (EARNED) agrees.
- This is a bug in the oracle, not the code. For integers, `x > hi - 1` is `x >= hi`, and at
  `x == hi` both versions return `hi`. So m4 is equivalent to the patch on integers, the test
  passes it (exit 0), and its own witness `clamp(9, 0, 10)` returns 9 on both (exit 0 and exit 0).
- The fixture's rationale ("returns 10 instead of 9") was wrong.
- Left as is, pending Parth's decision. `tests/test_verify.py::test_fixture_verdict_locally[earned_clamp]`
  fails until then.

**Structural revert check.** Mutant de-duplication now compares Python files by `ast.dump`, not
exact text. Over the 154 cached flask-5014 mutants (19 responses):
- **Reverts** (structurally the original code): 2, of which the old exact-text check caught 1.
- **Identical to the gold patch:** 0. **Duplicates within a response:** 8. **Distinct and applicable:** 134.
- **Don't apply:** 7. **Parse errors:** 3.

**Phase 1 sandbox spend:** $0.1985 across two full fixture runs. The second run re-checked the evidence
after the P2P-recording fix.

## 2026-10-25: after hard stop 1 (Parth's decisions)

**`earned_clamp` m4 corrected to `equivalent`**, with Parth's agreement on the analysis. The fixture
now makes its domain explicit: `clamp` is annotated `int` and raises `TypeError` for anything else, so
the equivalence holds over the whole domain by construction instead of implicitly. m4's witness is
now `clamp(9.5, 0, 10)`, just outside that domain, and both versions raise `TypeError`.

**New fixture `unearned_clamp_float`**, the domain-wider-than-coverage case. clamp accepts floats, the
test covers integers only, and m4 (`x > hi - 1`) has witness `clamp(9.5, 0, 10)`: the patch returns 9.5 and the
mutant returns 10. Expected verdict UNEARNED, with m4 `survived`.

**Limitation: equivalence is relative to the input domain, not absolute.** A mutant equivalent over
one domain can be distinguishable over a wider one, so the equivalence discard is sound only
within the domain its witness explores. **How we found it:** our own oracle contradicted our own
fixture. The fixture expected m4 `killed`, verify reported `equivalent` with both witness runs
returning 9 (exit 0, exit 0), and the fixture was wrong. The limitation is also in the README.

**Configuration B, later.** Gate the PASS_TO_PASS fork behind the original-code fork instead of
launching them in parallel, so a BROKEN verdict does not pay for the regression suite.
Configuration A keeps them in parallel: BROKEN should be impossible there, because FAIL_TO_PASS fails on
the original by construction.

## 2026-10-25: phase 2 (official.py, five instances built and checked)

**`official.py` is thin.** It returns the dataset's published label for the gold patch, RESOLVED by
construction, plus the FAIL_TO_PASS and PASS_TO_PASS lists. It runs nothing and reproduces none of the
harness's logic. The README says "benchmark oracle" means the repository's own FAIL_TO_PASS tests.

**Instances.** Five, from the three lightest repos measured; no django, sympy, astropy or matplotlib:
- `pallets__flask-5014`
- `psf__requests-5414`
- `psf__requests-6028`
- `pytest-dev__pytest-7432`
- `pytest-dev__pytest-7571`

All have FAIL_TO_PASS ids without spaces, so they can be run directly. Each is built from the
official harness image by running the harness's own install step once (`disposable=False`).

**Overlays.** Patches become exact file overlays by applying them to a local checkout at the base
commit (`.cache/repos`, gitignored; the files are read, never executed).

**Environment check (all five pass).** FAIL_TO_PASS fails on the original and passes with the gold
patch, in forks of the warm checkpoint. None came back BROKEN.

**requests installs non-editable (`pip install .`).** Its tests still import `/testbed/requests` from
source: the gold-patched fork passes without a reinstall.

**`generate.py` now asks for a WITNESS with every mutant.** It must be a Python block ending in one
expression, the input the rationale names. Mutants without a well-formed witness are rejected
and re-asked. `propose_mutant_records` returns records with the witness;
`propose_mutants` still returns (diff, rationale). The new prompt has not been run live yet; phase 3
is its first use.

## 2026-10-25: phase 3 rules, committed BEFORE the run

**Pre-committed escalation (Parth).** If zero mutants survive across all five instances
(flask-5014, requests-5414, requests-6028, pytest-7432, pytest-7571), the response is to raise
the mutant count from 10 to 30 **on the same five instances**: a larger sample of the same
question. It is NOT to swap in different instances until a survivor appears. A zero across five
instances and three repositories is a real result and is reported as one.

**Negative control.** Before any mutant result is trusted, each instance runs a canary mutant
built mechanically, with no model involved: the body of the patched function is replaced with
`raise AssertionError("canary")`. The canary is applied through the same overlay path as real
mutants, and the targeted test runs on it. The test MUST fail. If the canary passes or errors,
patch application is not proven live in that environment, so every mutant result for the
instance is void, not negative: the instance is reported as INCONCLUSIVE. Every verdict cites
its canary's exit code. Bytecode: `PYTHONDONTWRITEBYTECODE=1` is set in every command, and
`__pycache__` under the work tree is cleared in the checkpoint.

**Timeouts.** Each instance's targeted-test timeout is 10x the targeted test's CPU time on the
gold patch, measured, floored at 15 s. The same rule applies to the PASS_TO_PASS fork, using its
own measured CPU time. Witness forks use the 15 s floor.

**Spend.** The phase 3 ceiling is $2, held in its own ledger (`runs/spend_ledger_phase3.jsonl`)
and counting generation as well as sandboxes. If the ceiling trips, the run stops and is reported;
the ceiling is not raised.

## 2026-10-25: phase 3 run log

**Before the run:** the eleven fixtures were re-run through the new canary path in sandboxes. All
agree, and every canary was live. Cost $0.1247, charged to the phase 3 ledger.

**First attempt, which crashed:**
- **Zero mutants accepted** on the three instances it reached. The WITNESS contract was too strict
  for what the model writes: shell wrappers and doctest transcripts.
- **REGRESSED on the `psf__requests-6028` gold patch.** This was a grading bug: path-parameter ids
  are normalized in the dataset and were not normalized by us.
- **Every warm checkpoint was rebuilt.** The build key included the env prefix, which had just
  gained `PYTHONDONTWRITEBYTECODE`.
- **The run crashed on the pytest-7432 rebuild.** It hit an API read timeout, and the guard charged
  that build its 120 s worst case, $1.24.

**Fixes, all in code, with no expectation changed:**
- witness normalization, with printed output compared and `PYTHONHASHSEED=0`;
- dataset-style id normalization for requests;
- build keys on the image and install step only (existing builds reused);
- build and calibration timeouts sized from measurement (build 22 s, test 15 s, P2P 20 s);
- per-instance errors recorded instead of crashing the run.

**Second attempt:**
- **pallets__flask-5014:** EARNED, but on 1 mutant.
- **psf__requests-5414:** UNEARNED, 2 survivors.
- **psf__requests-6028:** UNEARNED, 1 survivor and 5 equivalents.
- **pytest-dev__pytest-7432:** INCONCLUSIVE. The canary was live, but there were no usable mutants.
- **The $2 ceiling then tripped** during pytest-dev__pytest-7571's mutant forks. Per the rule, the run
  stopped and the ceiling was not raised.
- **Spend:** the second attempt cost $0.4162. The phase 3 ledger ends at $1.8989.

**The escalation rule did not apply:** survivors exist.

## 2026-10-25: verdict split, PASS_TO_PASS now runs against mutants

**What was wrong.** Mutant forks ran FAIL_TO_PASS only. PASS_TO_PASS never ran against a mutant.
That was Parth's instruction at the start of phase 1 ("PASS_TO_PASS never runs against a
mutant, because a mutant is not a candidate for acceptance"), and I implemented it as stated.
Parth has since withdrawn it, and his reason is right: **a mutant is precisely the stand-in for a
candidate patch, so it must face the same criterion a candidate faces.** SWE-bench resolves a
patch when FAIL_TO_PASS passes AND PASS_TO_PASS does not regress. Grading mutants on FAIL_TO_PASS
alone measured something weaker than the benchmark's own bar. In phase 3 it showed: two of the
three survivors broke behaviour that PASS_TO_PASS ids appear to cover.

**Correction.** Every distinguishable survivor of FAIL_TO_PASS now runs PASS_TO_PASS, with the same
command and id normalization the gold patch faces.
- **UNEARNED:** a distinguishable mutant passes FAIL_TO_PASS AND PASS_TO_PASS. It clears
  SWE-bench's full resolution criterion.
- **UNPINNED (new):** a distinguishable mutant passes FAIL_TO_PASS but is caught by PASS_TO_PASS.
  The designated test does not pin the bug; the suite catches the mutant incidentally.
- Precedence after the baseline forks: UNEARNED, then INCONCLUSIVE for mutant forks that did not
  complete, then UNPINNED, then EARNED.
- **Statuses:** `survived` now means FAIL_TO_PASS and PASS_TO_PASS were both survived;
  `caught-by-p2p` is new.

**Cost.** The cost model's "PASS_TO_PASS never runs against a mutant" no longer holds. Only
distinguishable survivors pay for a PASS_TO_PASS fork, typically $0.004-0.02 each, and killed and
equivalent mutants still cost one targeted test.

**New fixture.** `unpinned_last_n` was committed (08fb233) before any sandbox run with the split. Its m2
passes FAIL_TO_PASS, differs on its witness, and is caught only by PASS_TO_PASS. Expected verdict UNPINNED.

**The existing fixtures' expectations are unchanged.** Every fixture survivor also passes PASS_TO_PASS,
which was checked locally and is checked again in sandboxes below.

**Ceiling.** The phase 3 ceiling is raised from $2 to $5 on Parth's instruction, on the same ledger.

**Witness normalization, extended** after pytest-7432's responses:
- a `python3 -c "..."` wrapper followed by a shell suffix (`2>&1 | head -5`);
- a ```python witness block with no `WITNESS:` label.

**Results after the split (phase 3 completed, five instances, ledger $2.3533 of $5).**
The generation responses were cached, so the mutants are the same ones as in the $2 run.
- **pallets__flask-5014:** EARNED, 1 distinguishable mutant, killed.
- **psf__requests-5414:** UNPINNED. 7 distinguishable, 1 equivalent. 2 survived FAIL_TO_PASS (m1, m4),
  and both were caught by the same five wildcard PASS_TO_PASS tests. m4's rewrite also dropped the `*` branch,
  so its catch is incidental to its too-narrow rationale.
- **psf__requests-6028:** UNPINNED. 5 distinguishable, 5 equivalent. 1 survived FAIL_TO_PASS (m1), caught
  by the three no-auth `prepend_scheme_if_needed` cases.
- **pytest-dev__pytest-7432:** INCONCLUSIVE. The canary was live (exit 3). Witnesses now parse, but 12 of 13
  diffs did not apply, and 1 changed nothing.
- **pytest-dev__pytest-7571:** EARNED. 7 of 7 distinguishable mutants killed, 3 equivalent discarded.
- **Headline:** 0 of 20 distinguishable mutants cleared both lists.

**The pre-committed escalation was not triggered.** It was written in terms of surviving
FAIL_TO_PASS, and 3 mutants did. Under the stricter post-split meaning (cleared both lists) the
count is zero. Whether that zero should trigger the 10-to-30 escalation on the same five
instances is Parth's decision. It was not run.
