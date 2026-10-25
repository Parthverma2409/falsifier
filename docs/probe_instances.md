# Step 1 gate, cost half: real-instance measurements (2026-10-25)

Produced by `scripts/probe_instances.py`; raw records in `docs/probe_instances_raw.json`. The corrected cost model is in `docs/probe.md`.

## Method

- Dataset `SWE-bench/SWE-bench_Verified`. The images are the official harness images (`swebench/sweb.eval.x86_64.*`), imported with `images.oci()`, so the environment is exactly the one the official verdict uses.
- **Build** is the eval script's install step (`pip install .` or `-e .`) run once with `disposable=False`. The result is the warm checkpoint, and every other run is a disposable fork of it.
- **interp** is `python -c pass`. **empty** writes `def test_falsifier_empty(): pass` into the targeted test's directory, so the same conftest and plugins load, then runs `pytest -rA` on it. **targeted** applies the test patch and runs the first FAIL_TO_PASS id. **p2p_full** applies the gold and test patches and runs the harness command, `pytest -rA <files the test patch touches>`. The PASS_TO_PASS ids are log-parser keys truncated at the first space, not runnable node ids, so the harness never selects by id and neither do we. **p2p_trimmed** runs only the targeted test's module. Coverage counts the PASS_TO_PASS ids the -rA log reports PASSED.
- Rails: every run has an explicit timeout ({'conda': 20, 'build': 60, 'interp': 10, 'empty': 20, 'targeted': 30, 'p2p': 40}) and is pinned to one CPU, under a spend ceiling of $0.85 checked before each launch at worst case.
- Sandbox: 4 vCPUs; pinned, so CPU-s ≤ wall-s.

## Per instance

### `pallets__flask-5014` (pallets/flask 2.3; F2P 1, P2P 59 in 1 module(s))

| Run | n | CPU s | run wall s | USD | pytest summary |
|---|---:|---:|---:|---:|---|
| conda | 1 | 0.176 | 0.43 | $0.00186 |  |
| build | 1 | 1.938 | 3.50 | $0.01973 |  |
| interp | 1 | 0.018 | 0.13 | $0.00023 |  |
| empty | 2 | 0.204 | 0.50 | $0.00222 | 1 passed in 0.01s |
| targeted | 2 | 0.280 | 0.59 | $0.00302 | 1 failed in 0.08s |
| p2p_full | 1 | 0.390 | 0.76 | $0.00412 | 60 passed in 0.23s |
| p2p_full coverage | | | | | 59/59 PASS_TO_PASS ids PASSED in the log |
| p2p_trimmed | = p2p_full | | | | the test patch touches only the targeted module |

Package imported from `/testbed/src/flask/__init__.py` after the build.

Overhead: the empty test uses **73%** of the targeted test's CPU, and a bare interpreter start uses 6%. The test body itself is 0.076 CPU-s.

**Per-instance cost, corrected model** (build + 1 P2P fork + 12 single-test forks): **$0.060** with full P2P, $0.060 with trimmed P2P.

### `psf__requests-5414` (psf/requests 2.26; F2P 1, P2P 130 in 1 module(s))

| Run | n | CPU s | run wall s | USD | pytest summary |
|---|---:|---:|---:|---:|---|
| build | 1 | 0.747 | 1.33 | $0.00768 |  |
| interp | 1 | 0.014 | 0.13 | $0.00019 |  |
| empty | 2 | 0.182 | 0.46 | $0.00197 | 1 passed in 0.01s |
| targeted | 2 | 0.433 | 0.72 | $0.00457 | 1 failed in 0.26s |
| p2p_full | 1 | 0.619 | 1.50 | $0.00641 | 131 passed, 1 xfailed, 158 errors in 1.04s |
| p2p_full coverage | | | | | 130/130 PASS_TO_PASS ids PASSED in the log |
| p2p_trimmed | = p2p_full | | | | the test patch touches only the targeted module |

Package imported from `/testbed/requests/__init__.py` after the build.

Overhead: the empty test uses **42%** of the targeted test's CPU, and a bare interpreter start uses 3%. The test body itself is 0.251 CPU-s.

**Per-instance cost, corrected model** (build + 1 P2P fork + 12 single-test forks): **$0.069** with full P2P, $0.069 with trimmed P2P.

### `pytest-dev__pytest-7432` (pytest-dev/pytest 5.4; F2P 1, P2P 77 in 1 module(s))

| Run | n | CPU s | run wall s | USD | pytest summary |
|---|---:|---:|---:|---:|---|
| build | 1 | 2.346 | 3.79 | $0.02381 |  |
| interp | 1 | 0.013 | 0.10 | $0.00018 |  |
| empty | 2 | 0.182 | 0.42 | $0.00194 | 1 passed in 0.01s |
| targeted | 2 | 0.254 | 0.50 | $0.00267 | 1 failed in 0.08s |
| p2p_full | 1 | 1.875 | 2.75 | $0.01907 | 79 passed in 2.17s |
| p2p_full coverage | | | | | 77/77 PASS_TO_PASS ids PASSED in the log |
| p2p_trimmed | = p2p_full | | | | the test patch touches only the targeted module |

Package imported from `/testbed/src/pytest/__init__.py` after the build.

Overhead: the empty test uses **72%** of the targeted test's CPU, and a bare interpreter start uses 5%. The test body itself is 0.072 CPU-s.

**Per-instance cost, corrected model** (build + 1 P2P fork + 12 single-test forks): **$0.075** with full P2P, $0.075 with trimmed P2P.

## Estimated cost for every instance in these three repos

These are estimates, not measurements. Build, targeted and empty costs come from the measured instance in the same repo. P2P = empty + (measured per-test P2P cost × the instance's P2P count).

| Instance | version | F2P | P2P | P2P modules | est. USD / instance | measured |
|---|---|---:|---:|---:|---:|---|
| `pytest-dev__pytest-5809` | 4.6 | 1 | 3 | 1 | $0.058 |  |
| `pallets__flask-5014` | 2.3 | 1 | 59 | 1 | $0.060 | yes |
| `pytest-dev__pytest-7571` | 6.0 | 1 | 14 | 1 | $0.061 |  |
| `pytest-dev__pytest-10051` | 7.2 | 1 | 15 | 1 | $0.061 |  |
| `pytest-dev__pytest-5631` | 5.0 | 1 | 15 | 1 | $0.061 |  |
| `pytest-dev__pytest-7205` | 5.4 | 10 | 16 | 1 | $0.061 |  |
| `psf__requests-1142` | 1.1 | 1 | 5 | 1 | $0.065 |  |
| `psf__requests-1724` | 2.0 | 6 | 79 | 1 | $0.067 |  |
| `psf__requests-1766` | 2.0 | 6 | 79 | 1 | $0.067 |  |
| `psf__requests-2931` | 2.9 | 1 | 84 | 1 | $0.067 |  |
| `psf__requests-1921` | 2.3 | 6 | 107 | 1 | $0.068 |  |
| `psf__requests-5414` | 2.26 | 1 | 130 | 1 | $0.069 | yes |
| `psf__requests-2317` | 2.4 | 8 | 133 | 1 | $0.069 |  |
| `pytest-dev__pytest-5840` | 5.1 | 2 | 51 | 1 | $0.069 |  |
| `pytest-dev__pytest-7236` | 5.4 | 1 | 51 | 1 | $0.069 |  |
| `pytest-dev__pytest-7324` | 5.4 | 3 | 58 | 1 | $0.071 |  |
| `psf__requests-6028` | 2.27 | 2 | 185 | 1 | $0.071 |  |
| `pytest-dev__pytest-8399` | 6.3 | 1 | 59 | 1 | $0.071 |  |
| `pytest-dev__pytest-10081` | 7.2 | 1 | 63 | 1 | $0.072 |  |
| `pytest-dev__pytest-6202` | 5.2 | 1 | 72 | 1 | $0.074 |  |
| `pytest-dev__pytest-7432` | 5.4 | 1 | 77 | 1 | $0.075 | yes |
| `pytest-dev__pytest-7490` | 6.0 | 2 | 78 | 1 | $0.075 |  |
| `pytest-dev__pytest-7982` | 6.2 | 1 | 78 | 1 | $0.075 |  |
| `pytest-dev__pytest-10356` | 7.2 | 1 | 79 | 1 | $0.075 |  |
| `pytest-dev__pytest-5262` | 4.5 | 1 | 108 | 2 | $0.082 |  |
| `pytest-dev__pytest-5787` | 5.1 | 2 | 123 | 3 | $0.085 |  |
| `pytest-dev__pytest-7521` | 6.0 | 2 | 125 | 3 | $0.086 |  |
| `pytest-dev__pytest-6197` | 5.2 | 2 | 145 | 2 | $0.090 |  |

## What the measurement cost

- **All attempts, SDK-reported: $0.1568** over 44 distinct runs (2 runs failed before launch and reported no cost). Earlier attempts are kept locally in `runs/` (gitignored); see `docs/plan_deviations.md` for why each one stopped.
- This run: $0.0296 over 3 runs (ceiling $0.85; 0 runs without a reported cost, charged at their worst case).
- Image imports: 3 × ~1 GB in 4 s. The SDK reports no cost for imports.
- Console billing delta: about $0.16 across all four attempts, against $0.157 SDK-reported (plus $0.00006 for the cores check), so the three image imports were free or below display precision
