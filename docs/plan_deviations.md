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
