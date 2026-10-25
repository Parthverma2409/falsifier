"""Phase 2: build and checkpoint the five SWE-bench Verified instances, then check the environment.

For each instance: import the official harness image, run the harness's install step once with
disposable=False (the warm checkpoint), then two forks of it: FAIL_TO_PASS on the original code
(must FAIL) and FAIL_TO_PASS with the gold patch (must PASS).

- Either direction disagreeing is an environment problem, not a finding: stop.
- FAIL_TO_PASS passing on the original would be BROKEN, which Configuration A makes impossible by
  construction: stop at once and say so. It would be a finding about the benchmark.

Writes reports/instances/builds.json and prints plain-text lines. No verdicts are run here.
"""

from __future__ import annotations

import asyncio
import json
import sys

from dotenv import load_dotenv

from falsifier.config import ROOT, SPEND_CEILING_USD, SPEND_LEDGER, SpendLimits
from falsifier.evidence import FAIL, PASS, classify_test_run
from falsifier.instance import build_swebench, load_swebench
from falsifier.official import load_rows, official
from falsifier.sandbox import SandboxForker, SpendCeilingExceeded, SpendGuard, Uploader
from falsifier.verify import pytest_command

INSTANCES = [
    "pallets__flask-5014",
    "psf__requests-5414",
    "psf__requests-6028",
    "pytest-dev__pytest-7432",
    "pytest-dev__pytest-7571",
]
OUT = ROOT / "reports" / "instances" / "builds.json"


async def main_async() -> int:
    from contree_sdk import Contree
    from contree_sdk.config import ContreeConfig

    client = Contree(ContreeConfig(operation_poll_secs_max=1.0, transport_timeout=30.0))
    guard = SpendGuard(SpendLimits.from_env(SPEND_CEILING_USD), ledger=SPEND_LEDGER)
    print(f"ceiling ${guard.limits.ceiling_usd:.2f}, already spent ${guard.prior_usd:.4f}")
    upload = Uploader(client)
    rows = load_rows(INSTANCES)
    results, status = {}, 0
    try:
        for iid in INSTANCES:
            row = rows[iid]
            inst = load_swebench(row)
            ckpt, build = await build_swebench(client, guard, inst, row)
            if build is None:
                print(f"{iid}: checkpoint {ckpt.uuid} reused; build cost recorded earlier")
            else:
                print(
                    f"{iid}: build {build['cpu_s']:.2f} CPU-s, ${build['cost_usd']:.4f}, "
                    f"{build['run_wall_s']:.1f} s wall, checkpoint {ckpt.uuid}"
                )
            fork = SandboxForker(ckpt, guard, upload, inst.workdir, iid)
            cmd = pytest_command(inst, inst.f2p)
            before, after = await asyncio.gather(
                fork("env-check/original+f2p", dict(inst.test), cmd, inst.timeouts.test),
                fork("env-check/gold+f2p", {**inst.patched, **inst.test}, cmd, inst.timeouts.test),
            )
            (b, b_why), (a, a_why) = classify_test_run(before), classify_test_run(after)
            print(f"  FAIL_TO_PASS before the gold patch: {b} ({b_why}), ${before.cost_usd:.4f}")
            print(f"  FAIL_TO_PASS after the gold patch: {a} ({a_why}), ${after.cost_usd:.4f}")
            results[iid] = {
                "official": official(row).to_dict(),
                "checkpoint": str(ckpt.uuid),
                "build": build,
                "env_check": {"before": before.to_dict(), "after": after.to_dict()},
                "install": row["eval_script"].split("conda activate testbed")[2].split("\n")[1],
            }
            if b == PASS:
                print(
                    f"STOP: {iid} FAIL_TO_PASS passes on the original code. That is BROKEN under "
                    "Configuration A, impossible by construction: a finding about the benchmark."
                )
                status = 3
                break
            if b != FAIL or a != PASS:
                print(f"STOP: {iid} environment problem (before {b}, after {a}); not a finding.")
                status = 4
                break
    except SpendCeilingExceeded as exc:
        print(f"ABORTED by the spend ceiling: {exc}")
        status = 2
    finally:
        s = guard.summary()
        print(
            f"spent this run ${s['spent_this_process_usd']:.4f} over {s['runs']} runs; "
            f"ledger total ${s['spent_usd']:.4f} of ${s['ceiling_usd']:.2f}"
        )
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(results, indent=2, default=str) + "\n")
    return status


def main() -> int:
    load_dotenv(ROOT / ".env")
    return asyncio.run(main_async())


if __name__ == "__main__":
    sys.exit(main())
