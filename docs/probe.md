# Step 1 probe: fork latency and cost (2026-10-25)

Produced by `scripts/probe.py`; raw per-run records are in `docs/probe_raw.json`.

## Setup

- Run at 2026-10-25T07:04:43+00:00 against `https://api.tokenfactory.nebius.com/sandboxes/`, contree-sdk 0.3.6, async `Contree` client.
- Account limits (`whoami`): `{'instance_max_timeout': 3600, 'instance_max_concurrency': 50, 'instance_max_layer_bytes': 12884901888, 'images_import_max_concurrency': 8, 'images_import_max_timeout': 3600}`; running instances at start: 0; semaphore 50.
- SDK polling capped at 1.0 s (default max 10 s), so wall clock includes up to ~1 s of polling granularity per run.
- Base image: `python:3.12-slim` imported or resolved in 0.6 s (uuid `4fa16c8f-62a9-35a4-a4ea-07b7e8cd44ae`).
- Checkpoint (`disposable=False`): `pip install --no-cache-dir --quiet --disable-pip-version-check six==1.17.0 && mkdir -p /opt/probe && python -c 'import six; print(six.__version__)' > /opt/probe/marker.txt && cat /opt/probe/marker.txt`

## Checkpoint

- Wall clock 3.18 s, server elapsed 1.09 s, exit 0, stdout `1.17.0`
- Reported cost: `0.011197620000000002`
- Checkpoint image uuid: `60eb631f-f099-480d-abd1-1c8f49eb6cb0` (persisted; cannot be deleted)

## Fan-out: `python -c "print(1)"`, `disposable=True`

| N | ok | total wall s | per-fork min / median / max s | cost sum | cost per fork |
|---:|---:|---:|---|---:|---:|
| 1 | 1/1 | 0.92 | 0.92 / 0.92 / 0.92 | 0.00018717 | 0.00018717 |
| 5 | 5/5 | 1.50 | 0.93 / 1.40 / 1.50 | 0.00089809 | 0.000179618 |
| 10 | 10/10 | 1.72 | 0.98 / 1.37 / 1.72 | 0.0018168 | 0.00018168 |
| 25 | 25/25 | 2.58 | 1.39 / 1.90 / 2.57 | 0.0045191 | 0.000180764 |
| 50 | 50/50 | 2.87 | 1.77 / 2.37 / 2.87 | 0.00894444 | 0.000178889 |

Client wall clock is measured from submit to result, including SDK polling. The sequential equivalent at N=50 is about 50 × the N=1 time.

## Cost vs. runtime

| Fork | client wall s | run wall s (`monotonic_time`) | CPU s (user+sys) | cost |
|---|---:|---:|---:|---:|
| `checkpoint` | 3.18 | 1.62 | 1.0929 | 0.0111976 |
| `sleep_1s` | 2.99 | 1.05 | 0.0030 | 7.971e-05 |
| `sleep_60s` | 61.28 | 60.03 | 0.0025 | 6.435e-05 |
| `busy_10s` | 12.04 | 10.15 | 10.0561 | 0.1039 |

Least-squares fits over all 95 successful runs:

- cost = 4.23e-05 + 0.010326 × CPU_s, R² = 1.00000
- cost = 0.00115 + 0.00026438 × wall_s, R² = 0.02366

`sleep 60` cost 0.81× what `sleep 1` cost. **Cost follows CPU time, not wall time.** An idle process costs almost nothing however long it runs, and a CPU-bound process costs about 0.01033 per CPU-second. Parallel test workers burn CPU-seconds faster than wall-seconds, so parallelism saves time but not money.

The SDK's `.elapsed` (`resources.elapsed_time`) equals user+sys CPU time, not wall time. Real run duration is `resources.monotonic_time`.

Total reported cost of this probe: **0.131607** (the unit is not documented).

## Extrapolation (reported cost units; USD per the reconciliation below)

One instance is 13 forks: original + test, patch + test, patch + PASS_TO_PASS suite, and 10 mutants + test (BUILD_PLAN step 4). The one-off build and checkpoint per instance (`pip install` of the repo) are not included; the probe's `pip install six` checkpoint cost 0.0112.

| Scenario | CPU s per instance | 1 instance | 5 instances |
|---|---:|---:|---:|
| probe fork (`print(1)`) | 0.2 | 0.002241 | 0.01121 |
| targeted test 5 CPU-s, P2P suite 60 CPU-s | 120.0 | 1.24 | 6.199 |
| targeted test 15 CPU-s, P2P suite 180 CPU-s | 360.0 | 3.718 | 18.59 |
| every fork 60 CPU-s | 780.0 | 8.055 | 40.28 |
| every fork 180 CPU-s (minutes-long Django suite) | 2,340.0 | 24.16 | 120.8 |

## Billing reconciliation

Token Factory console billing rose by **about 0.13 USD** across the probe run, against an SDK-reported total of 0.131607. **The SDK's `cost` field is USD**, so Sandboxes are billed: about $0.0103 per CPU-second ($37.18 per CPU-hour) plus $4.2e-05 per run. The figure was read by hand from one before/after pair at the console's display precision.
