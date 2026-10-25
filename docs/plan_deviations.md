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
