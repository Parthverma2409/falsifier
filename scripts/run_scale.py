"""Configuration A on every SWE-bench Verified instance in pallets/flask, psf/requests and
pytest-dev/pytest. Enumerated from the dataset, never hand-picked.

Guards:
- a $10 global ceiling in its own ledger;
- a $0.50 per-instance ceiling (a guard nested in the global one). An instance that hits it is
  excluded, not retried;
- per-fork timeouts from the instance's measured gold-patch CPU time (10x, floored at 15 s);
- the canary per instance, as before: not live voids the instance.

Every instance not in the final table is listed with its reason: failed the environment check,
canary not live, hit the per-instance ceiling, zero distinguishable mutants, or zero applicable
mutant diffs. Writes reports/scale/ and reports/scale/exclusions.json.
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import json
import math
import sys

from dotenv import load_dotenv

from falsifier.config import ROOT, SpendLimits
from falsifier.evidence import (
    CAUGHT_BY_P2P,
    FAIL,
    INCONCLUSIVE,
    KILLED,
    PASS,
    SURVIVED,
    canary_live,
    classify_test_run,
    passed_ids,
)
from falsifier.generate import (
    LLM,
    overlay_reader,
    propose_mutant_records,
    tree_reader,
    validate_diff,
)
from falsifier.instance import REPOS, Mutant, build_swebench, clean_checkpoint, load_swebench
from falsifier.official import DATASET, official
from falsifier.report import write
from falsifier.sandbox import SandboxForker, SpendCeilingExceeded, SpendGuard, Uploader
from falsifier.verify import pytest_command, verify

REPOS3 = ("pallets/flask", "psf/requests", "pytest-dev/pytest")
GLOBAL_CEILING_USD = 10.0
INSTANCE_CEILING_USD = 0.50
LEDGER = ROOT / "runs" / "spend_ledger_scale.jsonl"
OUT = ROOT / "reports" / "scale"
FLOOR_S = 15
PARALLEL_INSTANCES = 4

ENV, CANARY, CEILING, NO_DISTINGUISHABLE, NO_DIFFS, INFRA = (
    "failed the environment check",
    "canary not live",
    "hit the per-instance ceiling",
    "zero distinguishable mutants",
    "zero applicable mutant diffs",
    "infrastructure failure (transport or DNS), not a property of the instance",
)
_TRANSPORT = (
    "ApiTimeoutError",
    "ContreeTransportError",
    "APIConnectionError",
    "name resolution",
    "Could not resolve host",
    "CalledProcessError",
)


class Excluded(Exception):
    def __init__(self, reason: str, detail: str, evidence: list | None = None):
        super().__init__(f"{reason}: {detail}")
        self.reason, self.detail, self.evidence = reason, detail, evidence or []


def enumerate_instances() -> list[dict]:
    from datasets import load_dataset

    rows = [dict(r) for r in load_dataset(DATASET, split="test") if r["repo"] in REPOS3]
    return sorted(rows, key=lambda r: r["instance_id"])


async def prepare(client, guard, upload, row):
    """Build, clean, then the environment check on the clean checkpoint: FAIL_TO_PASS fails on the
    original and passes on the gold patch, and every PASS_TO_PASS id PASSES on the gold patch.
    The gold-patch runs also measure CPU time for the timeouts."""
    inst = load_swebench(row)
    warm, _ = await build_swebench(client, guard, inst, row)
    ckpt, _ = await clean_checkpoint(client, guard, inst, warm)
    fork = SandboxForker(ckpt, guard, upload, inst.workdir, inst.id, concurrency=8)
    both, t0 = {**inst.patched, **inst.test}, inst.timeouts
    f2p, p2p = pytest_command(inst, inst.f2p), pytest_command(inst, inst.p2p_files)
    orig, gold, gold_p2p = await asyncio.gather(
        fork("envcheck/original+f2p", dict(inst.test), f2p, t0.test),
        fork("envcheck/gold+f2p", both, f2p, t0.test),
        fork("envcheck/gold+p2p", both, p2p, t0.regression),
    )
    (o, o_why), (g, g_why) = classify_test_run(orig), classify_test_run(gold)
    evidence = [r.to_dict() for r in (orig, gold, gold_p2p)]
    for r in (orig, gold, gold_p2p):
        if r.error and any(t in r.error for t in _TRANSPORT):
            raise Excluded(INFRA, f"{r.label}: {r.error[:300]}", evidence)
    if o != FAIL:
        raise Excluded(ENV, f"FAIL_TO_PASS on the original is {o}, not FAIL ({o_why})", evidence)
    if g != PASS:
        raise Excluded(ENV, f"FAIL_TO_PASS on the gold patch is {g}, not PASS ({g_why})", evidence)
    seen = passed_ids(gold_p2p.stdout, normalize_options=inst.log_parser == "parse_log_requests")
    missing = [i for i in inst.p2p if i not in seen]
    if gold_p2p.exit_code not in (0, 1) or missing:
        timed = f", timed out at {gold_p2p.timeout_s} s" if gold_p2p.timed_out else ""
        raise Excluded(
            ENV,
            f"PASS_TO_PASS on the gold patch: exit {gold_p2p.exit_code}{timed}, {len(missing)} "
            f"of {len(inst.p2p)} ids not PASSED (e.g. {missing[:2]})",
            evidence,
        )
    inst.timeouts = dataclasses.replace(
        t0,
        test=max(FLOOR_S, math.ceil(10 * gold.cpu_s)),
        regression=max(FLOOR_S, math.ceil(10 * gold_p2p.cpu_s)),
        witness=FLOOR_S,
    )
    return inst, fork, {"gold_f2p_cpu_s": gold.cpu_s, "gold_p2p_cpu_s": gold_p2p.cpu_s}


async def generate(guard, inst, row, n: int):
    guard.require_room(f"{inst.id}/generate", 0.05)
    llm = LLM()
    recs = await asyncio.to_thread(
        propose_mutant_records,
        row["patch"],
        n,
        repo_dir=REPOS / inst.id,
        issue_text=row["problem_statement"],
        llm=llm,
    )
    await guard.charge(f"{inst.id}/generate", llm.total_usd)
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
    gen = {"asked": n, "returned": len(recs), "usd": llm.total_usd, "events": llm.events}
    return mutants, gen


async def run_one(client, top: SpendGuard, upload, row, n: int) -> dict:
    iid = row["instance_id"]
    guard = SpendGuard(SpendLimits(ceiling_usd=INSTANCE_CEILING_USD), parent=top, name=iid)
    entry: dict = {"instance_id": iid, "repo": row["repo"]}
    try:
        inst, fork, cal = await prepare(client, guard, upload, row)
        entry["calibration"] = cal | {"timeouts": dataclasses.asdict(inst.timeouts)}
        inst.mutants, gen = await generate(guard, inst, row, n)
        entry["generation"] = {k: gen[k] for k in ("asked", "returned", "usd")}
        (OUT / f"{iid}.generation.json").write_text(json.dumps(gen, indent=2, default=str) + "\n")
        if not inst.mutants:
            raise Excluded(
                NO_DIFFS, f"0 of {n} generated mutants were applicable well-formed diffs"
            )
        v = await verify(inst, fork)
        o = official(row).to_dict()
        write(v, inst, OUT, o)
        entry["verdict"] = v.verdict
        if v.verdict == INCONCLUSIVE:
            live, why = canary_live(v.forks.get("canary"))
            if not live:
                raise Excluded(CANARY, why)
            if v.counts.get("error"):
                raise Excluded(INFRA, f"{v.counts['error']} mutant fork(s) did not complete")
            if not any(m.status in (KILLED, SURVIVED, CAUGHT_BY_P2P) for m in v.mutants):
                raise Excluded(NO_DISTINGUISHABLE, v.reason[-200:])
            raise Excluded(ENV, f"INCONCLUSIVE: {v.reason[-300:]}")
        if v.verdict not in ("EARNED", "UNEARNED", "UNPINNED"):
            raise Excluded(ENV, f"gold patch came back {v.verdict}: {v.reason[:300]}")
        entry["included"] = True
    except Excluded as exc:
        entry |= {"included": False, "reason": exc.reason, "detail": exc.detail}
        if exc.evidence:
            entry["evidence"] = exc.evidence
    except SpendCeilingExceeded as exc:
        if exc.scope == "global":
            raise
        entry |= {"included": False, "reason": CEILING, "detail": str(exc)}
    except Exception as exc:  # build, import or transport failure: reported, never dropped
        detail = f"{type(exc).__name__}: {exc}"[:400]
        reason = INFRA if any(t in detail for t in _TRANSPORT) else ENV
        entry |= {"included": False, "reason": reason, "detail": detail}
    entry["spent_usd"] = guard.spent_usd
    line = entry.get("verdict", "") if entry.get("included") else f"EXCLUDED ({entry['reason']})"
    print(f"{iid}: {line}; ${guard.spent_usd:.4f}", flush=True)
    return entry


async def main_async(n: int, only: list[str] | None = None) -> int:
    from contree_sdk import Contree
    from contree_sdk.config import ContreeConfig

    OUT.mkdir(parents=True, exist_ok=True)
    all_rows = enumerate_instances()
    rows = [r for r in all_rows if not only or r["instance_id"] in set(only)]
    if only:
        print(f"re-running {len(rows)} instance(s) never evaluated in the first attempt")
    print(
        f"enumerated {len(rows)} SWE-bench Verified instances in {', '.join(REPOS3)}; "
        f"{n} mutants each"
    )
    client = Contree(ContreeConfig(operation_poll_secs_max=1.0, transport_timeout=30.0))
    top = SpendGuard(SpendLimits(ceiling_usd=GLOBAL_CEILING_USD), ledger=LEDGER)
    print(
        f"global ceiling ${GLOBAL_CEILING_USD:.2f} (already ${top.prior_usd:.4f}); per instance "
        f"${INSTANCE_CEILING_USD:.2f}"
    )
    upload = Uploader(client)
    sem = asyncio.Semaphore(PARALLEL_INSTANCES)
    entries: dict[str, dict] = {}
    status = 0

    async def guarded(row):
        async with sem:
            entries[row["instance_id"]] = await run_one(client, top, upload, row, n)

    try:
        await asyncio.gather(*(guarded(r) for r in rows))
    except SpendCeilingExceeded as exc:
        print(f"STOPPED by the global ${GLOBAL_CEILING_USD:.2f} ceiling (not raised): {exc}")
        status = 2
    excl = OUT / "exclusions.json"
    if only and excl.exists():  # merge, keeping each instance's earlier attempt as history
        old = json.loads(excl.read_text())["instances"]
        for iid, prev in old.items():
            if iid in entries:
                history = prev.pop("previous_attempts", [])
                entries[iid]["previous_attempts"] = [*history, prev]
            else:
                entries[iid] = prev
    for r in all_rows:  # never silently dropped
        entries.setdefault(
            r["instance_id"],
            {
                "instance_id": r["instance_id"],
                "repo": r["repo"],
                "included": False,
                "reason": "not run: the global ceiling stopped the run",
                "detail": "",
            },
        )
    excl.write_text(
        json.dumps({"mutants_per_instance": n, "instances": entries}, indent=2, default=str) + "\n"
    )
    s = top.summary()
    print(f"spend: ${s['spent_usd']:.4f} of ${s['ceiling_usd']:.2f} ({s['runs']} sandbox runs)")
    return status


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--mutants", type=int, default=50)
    ap.add_argument("--only", nargs="*", help="re-run these instances; merge into exclusions.json")
    args = ap.parse_args()
    load_dotenv(ROOT / ".env")
    return asyncio.run(main_async(args.mutants, args.only))


if __name__ == "__main__":
    sys.exit(main())
