"""Run every fixture through the real pipeline in Nebius sandboxes and compare with its expected
verdict. Writes reports/fixtures/<id>.json and .html plus index.html; prints plain-text lines.
Exits 1 if any fixture's verdict or mutant statuses disagree with what it expects.

The fixtures' expectations are never edited to make this pass (falsifier/fixtures/README.md).
"""

from __future__ import annotations

import asyncio
import json
import sys

from dotenv import load_dotenv

from falsifier.config import ROOT, SPEND_CEILING_USD, SPEND_LEDGER, SpendLimits
from falsifier.instance import build_fixture, build_fixture_base, load_fixtures
from falsifier.report import index, write
from falsifier.sandbox import SandboxForker, SpendCeilingExceeded, SpendGuard, Uploader
from falsifier.verify import verify

OUT = ROOT / "reports" / "fixtures"


async def main_async() -> int:
    from contree_sdk import Contree
    from contree_sdk.config import ContreeConfig

    client = Contree(ContreeConfig(operation_poll_secs_max=1.0, transport_timeout=30.0))
    info = await client.get_token_info()
    cap = info.limits.get("instance_max_concurrency", 50)
    guard = SpendGuard(SpendLimits.from_env(SPEND_CEILING_USD), ledger=SPEND_LEDGER)
    print(
        f"ceiling ${guard.limits.ceiling_usd:.2f}, already spent ${guard.prior_usd:.4f} "
        f"(ledger {SPEND_LEDGER.relative_to(ROOT)}), concurrency cap {cap}"
    )
    upload = Uploader(client)
    fixtures = load_fixtures()
    builds, verdicts, disagreements = {}, [], []
    try:
        base, rec = await build_fixture_base(client, guard)
        builds["base"] = rec
        print(
            f"base checkpoint {base.uuid}"
            + (
                " (reused)"
                if rec is None
                else f" built: {rec['cpu_s']:.2f} CPU-s ${rec['cost_usd']:.4f}"
            )
        )
        for inst in fixtures:
            ckpt, rec = await build_fixture(client, guard, upload, base, inst)
            builds[inst.id] = rec
            fork = SandboxForker(ckpt, guard, upload, inst.workdir, inst.id, concurrency=cap)
            v = await verify(inst, fork)
            verdicts.append(v)
            write(v, inst, OUT)
            mutant_gaps = [
                (m.id, m.expected_status, m.status)
                for m in v.mutants
                if m.expected_status and m.expected_status != m.status
            ]
            ok = v.verdict == inst.expected_verdict and not mutant_gaps
            print(
                f"{inst.id}: expected {inst.expected_verdict}, produced {v.verdict}, "
                f"{'PASS' if ok else 'FAIL'} ({len(v.all_records())} forks, {v.cpu_s:.2f} CPU-s, "
                f"${v.cost_usd:.4f})"
            )
            if not ok:
                disagreements.append((inst, v, mutant_gaps))
    except SpendCeilingExceeded as exc:
        print(f"ABORTED by the spend ceiling: {exc}")
        return 2
    finally:
        s = guard.summary()
        print(
            f"spent this run ${s['spent_this_process_usd']:.4f} over {s['runs']} runs; "
            f"ledger total ${s['spent_usd']:.4f} of ${s['ceiling_usd']:.2f}"
        )
        (OUT / "builds.json").parent.mkdir(parents=True, exist_ok=True)
        (OUT / "builds.json").write_text(json.dumps(builds, indent=2, default=str) + "\n")

    agree = sum(v.verdict == v.expected_verdict for v in verdicts)
    index(
        verdicts,
        OUT,
        "Falsifier fixture suite",
        f"<p>{agree} of {len(verdicts)} verdicts agree with the expected verdict.</p>",
    )
    for inst, v, gaps in disagreements:
        print(f"\nDISAGREEMENT {inst.id}")
        print(f"  expected verdict {inst.expected_verdict}, produced {v.verdict}")
        for mid, want, got in gaps:
            print(f"  mutant {mid}: expected {want}, produced {got}")
        print(f"  oracle reasoning: {v.reason}")
        print(f"  evidence: {(OUT / (inst.id + '.json')).relative_to(ROOT)}")
    return 1 if disagreements else 0


def main() -> int:
    load_dotenv(ROOT / ".env")
    return asyncio.run(main_async())


if __name__ == "__main__":
    sys.exit(main())
