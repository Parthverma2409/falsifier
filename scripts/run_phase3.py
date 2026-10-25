"""Phase 3: Configuration A on five SWE-bench Verified instances.

Per instance:
1. a warm checkpoint (reused from phase 2), plus a layer with every __pycache__ removed;
2. calibration: the targeted test and PASS_TO_PASS on the gold patch, so timeouts can be set from
   measured CPU time (10x, floored at 15 s);
3. ten mutants of the gold patch from Nemotron, each with a WITNESS;
4. verify, whose negative control (the canary) must fail before any mutant result is trusted.

Escalation, committed before this run (docs/plan_deviations.md): if zero mutants survive across
all five instances, re-run the same five with 30 mutants each, never different instances.

Spend: a $2 ceiling in its own ledger, generation included. If it trips, stop and report.
Writes reports/instances/ (comparison index, per-instance pages and JSON) and docs/results.md.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import math
import os
import sys

from dotenv import load_dotenv

from falsifier.config import ROOT, USD_PER_CPU_SECOND, USD_PER_RUN, SpendLimits
from falsifier.evidence import (
    CAUGHT_BY_P2P,
    EQUIVALENT,
    KILLED,
    NOT_RUN,
    PASS,
    SURVIVED,
    classify_test_run,
)
from falsifier.generate import (
    LLM,
    overlay_reader,
    propose_mutant_records,
    tree_reader,
    validate_diff,
)
from falsifier.instance import (
    REPOS,
    Mutant,
    build_swebench,
    clean_checkpoint,
    load_swebench,
)
from falsifier.official import load_rows, official
from falsifier.report import comparison, write
from falsifier.sandbox import SandboxForker, SpendCeilingExceeded, SpendGuard, Uploader
from falsifier.verify import pytest_command, verify

INSTANCES = [
    "pallets__flask-5014",
    "psf__requests-5414",
    "psf__requests-6028",
    "pytest-dev__pytest-7432",
    "pytest-dev__pytest-7571",
]
CEILING_USD = float(os.environ.get("FALSIFIER_SPEND_CEILING_USD", 5.0))
"""Raised from $2 to $5 by Parth after the $2 ceiling tripped (2026-10-25); same ledger."""
LEDGER = ROOT / "runs" / "spend_ledger_phase3.jsonl"
OUT = ROOT / "reports" / "instances"
N_MUTANTS, N_ESCALATED = 10, 30
F2P_SURVIVOR = (SURVIVED, CAUGHT_BY_P2P)
"""The pre-committed escalation (8fd9bc8) was written when "survive" meant surviving
FAIL_TO_PASS, so it keeps that meaning: distinguishable mutants passing FAIL_TO_PASS, whether or
not PASS_TO_PASS then catches them."""
FLOOR_S = 15


def worst_case(t, n: int) -> tuple[int, float]:
    """Every fork running to its timeout: 2 baseline tests + P2P + canary + n mutants + 2n
    witnesses. Returns (CPU-seconds, USD)."""
    cpu = 3 * t.test + t.regression + n * t.test + 2 * n * t.witness
    return cpu, (4 + 3 * n) * USD_PER_RUN + USD_PER_CPU_SECOND * cpu


async def prepare(client, guard, upload, row):
    """Clean checkpoint, measured timeouts. Returns (inst, fork, calibration dict)."""
    inst = load_swebench(row)
    warm, _ = await build_swebench(client, guard, inst, row)
    ckpt, clean_rec = await clean_checkpoint(client, guard, inst, warm)
    fork = SandboxForker(ckpt, guard, upload, inst.workdir, inst.id)
    both = {**inst.patched, **inst.test}
    t0 = inst.timeouts
    cal_t, cal_p = await asyncio.gather(
        fork("calibrate/gold+f2p", both, pytest_command(inst, inst.f2p), t0.test),
        fork("calibrate/gold+p2p", both, pytest_command(inst, inst.p2p_files), t0.regression),
    )
    if classify_test_run(cal_t)[0] != PASS or cal_p.exit_code not in (0, 1):
        raise RuntimeError(
            f"{inst.id}: calibration on the gold patch failed (environment problem): "
            f"{classify_test_run(cal_t)[1]}; P2P exit {cal_p.exit_code}"
        )
    inst.timeouts = dataclasses.replace(
        t0,
        test=max(FLOOR_S, math.ceil(10 * cal_t.cpu_s)),
        regression=max(FLOOR_S, math.ceil(10 * cal_p.cpu_s)),
        witness=FLOOR_S,
    )
    cal = {
        "checkpoint": str(ckpt.uuid),
        "clean_layer": clean_rec,
        "f2p_cpu_s": cal_t.cpu_s,
        "p2p_cpu_s": cal_p.cpu_s,
        "timeouts": dataclasses.asdict(inst.timeouts),
        "records": [cal_t.to_dict(), cal_p.to_dict()],
    }
    return inst, fork, cal


async def mutants_for(guard, inst, row, n: int, tag: str) -> tuple[list[Mutant], dict]:
    guard.require_room(f"{inst.id}/generate{tag}", 0.05)
    llm = LLM()
    recs = propose_mutant_records(
        row["patch"], n, repo_dir=REPOS / inst.id, issue_text=row["problem_statement"], llm=llm
    )
    await guard.charge(f"{inst.id}/generate{tag}", llm.total_usd)
    read = overlay_reader(tree_reader(REPOS / inst.id), inst.patched)
    mutants = []
    for i, r in enumerate(recs, 1):
        v = validate_diff(r["diff"], read)
        mutants.append(
            Mutant(
                id=f"m{i}",
                kind=r["kind"] or "",
                rationale=r["rationale"],
                witness=r["witness"],
                overlay={p: t for p, t in v.after.items() if t is not None},
                diff=r["diff"],
            )
        )
    gen = {
        "asked": n,
        "returned": len(recs),
        "usd": llm.total_usd,
        "calls": llm.ledger(),
        "events": llm.events,
        "records": recs,
    }
    return mutants, gen


FAILURES: dict[str, str] = {}
"""Instances that could not be run at all (transport or environment errors), with the reason."""


async def run(n: int, tag: str, client, guard, upload, rows, out_dir) -> list:
    results = []
    out_dir.mkdir(parents=True, exist_ok=True)
    for iid in INSTANCES:
        try:
            results.append(await run_one(iid, n, tag, client, guard, upload, rows, out_dir))
        except SpendCeilingExceeded:
            raise
        except Exception as exc:  # recorded and reported; the other instances still run
            FAILURES[iid] = f"{type(exc).__name__}: {str(exc)[:400]}"
            print(f"{iid}: NOT RUN: {FAILURES[iid]}")
    if results and len(INSTANCES) == 5:  # partial completions are re-rendered by render_results
        comparison([r[0] for r in results], {r[0].instance_id: r[2] for r in results}, out_dir)
    return results


async def run_one(iid, n, tag, client, guard, upload, rows, out_dir):
    row = rows[iid]
    inst, fork, cal = await prepare(client, guard, upload, row)
    cpu, usd = worst_case(inst.timeouts, n)
    print(
        f"{iid}: timeouts test {inst.timeouts.test} s (gold targeted test "
        f"{cal['f2p_cpu_s']:.2f} CPU-s), P2P {inst.timeouts.regression} s "
        f"({cal['p2p_cpu_s']:.2f} CPU-s), witness {inst.timeouts.witness} s; "
        f"worst case with {n} mutants {cpu} CPU-s, ${usd:.2f}"
    )
    inst.mutants, gen = await mutants_for(guard, inst, row, n, tag)
    print(f"  generated {gen['returned']} of {n} mutants, ${gen['usd']:.4f}")
    v = await verify(inst, fork)
    o = official(row).to_dict()
    write(v, inst, out_dir, o)
    (out_dir / f"{iid}.generation.json").write_text(
        json.dumps(gen | {"calibration": cal}, indent=2, default=str) + "\n"
    )
    k = sum(m.status == KILLED for m in v.mutants)
    s = sum(m.status == SURVIVED for m in v.mutants)
    q = sum(m.status == EQUIVALENT for m in v.mutants)
    print(
        f"  verdict {v.verdict}; killed {k} of {k + s} distinguishable; {q} equivalent "
        f"discarded; canary exit {v.counts.get('canary_exit')}; ${v.cost_usd:.4f}"
    )
    return v, inst, o


async def main_async(n_mutants: int) -> int:
    from contree_sdk import Contree
    from contree_sdk.config import ContreeConfig

    client = Contree(ContreeConfig(operation_poll_secs_max=1.0, transport_timeout=30.0))
    guard = SpendGuard(SpendLimits(ceiling_usd=CEILING_USD), ledger=LEDGER)
    print(f"phase 3 ceiling ${CEILING_USD:.2f}; already spent in this phase ${guard.prior_usd:.4f}")
    upload = Uploader(client)
    rows = load_rows(INSTANCES)
    status, results = 0, []
    try:
        if n_mutants != N_MUTANTS:  # the pre-committed escalation, run directly (8fd9bc8)
            print(f"escalation run: {n_mutants} mutants on the same five instances")
            results = await run(
                n_mutants,
                f"-x{n_mutants}",
                client,
                guard,
                upload,
                rows,
                OUT / f"escalation-{n_mutants}",
            )
            return status
        results = await run(N_MUTANTS, "", client, guard, upload, rows, OUT)
        ran = [v for v, _, _ in results if any(m.status != NOT_RUN for m in v.mutants)]
        survivors = sum(m.status in F2P_SURVIVOR for v, _, _ in results for m in v.mutants)
        print(f"survivors across all five at {N_MUTANTS} mutants: {survivors}")
        if survivors == 0 and ran:
            print(f"pre-committed escalation: same five instances, {N_ESCALATED} mutants each")
            results = await run(
                N_ESCALATED, "-x30", client, guard, upload, rows, OUT / "escalation-30"
            )
            survivors = sum(m.status in F2P_SURVIVOR for v, _, _ in results for m in v.mutants)
            print(f"survivors across all five at {N_ESCALATED} mutants: {survivors}")
    except SpendCeilingExceeded as exc:
        print(f"STOPPED by the $ {CEILING_USD:.2f} ceiling (not raised): {exc}")
        status = 2
    finally:
        s = guard.summary()
        print(
            f"phase 3 spend: ${s['spent_usd']:.4f} of ${s['ceiling_usd']:.2f} "
            f"(this process ${s['spent_this_process_usd']:.4f}, {s['runs']} sandbox runs)"
        )
    print("render docs/results.md and reports/instances/index.html with scripts/render_results.py")
    return status


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--mutants", type=int, default=N_MUTANTS)
    ap.add_argument(
        "--only", nargs="*", help="complete these instances only (e.g. after a transport failure)"
    )
    args = ap.parse_args()
    if args.only:
        INSTANCES[:] = [i for i in INSTANCES if i in set(args.only)]
    load_dotenv(ROOT / ".env")
    return asyncio.run(main_async(args.mutants))


if __name__ == "__main__":
    sys.exit(main())
