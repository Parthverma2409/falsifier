"""Fork-timing and cost probe (build plan step 1, the gate).

Imports python:3.12-slim, builds a non-empty checkpoint, forks it N times for N in 1, 5, 10, 25,
50 with disposable runs, then runs duration-controlled forks to see whether the SDK-reported
cost scales with runtime. Writes docs/probe.md and docs/probe_raw.json.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv

from falsifier.config import SpendLimits
from falsifier.sandbox import SpendCeilingExceeded, SpendGuard, guarded_run

ROOT = Path(__file__).resolve().parent.parent
PROBE_MD = ROOT / "docs" / "probe.md"
PROBE_JSON = ROOT / "docs" / "probe_raw.json"

BASE_IMAGE = "python:3.12-slim"
FORK_NS = (1, 5, 10, 25, 50)
FORK_CMD = 'python -c "print(1)"'
PREP_CMD = (
    "pip install --no-cache-dir --quiet --disable-pip-version-check six==1.17.0"
    " && mkdir -p /opt/probe"
    " && python -c 'import six; print(six.__version__)' > /opt/probe/marker.txt"
    " && cat /opt/probe/marker.txt"
)
# Explicit per-run timeouts (never the SDK's 1000 s default). With the default $3 ceiling, 50
# fan-out forks at 5 s each reserve $2.58 worst case, so N=50 still runs fully in parallel.
CHECKPOINT_TIMEOUT_S = 120
FORK_TIMEOUT_S = 5
DEFAULT_CEILING_USD = 3.0
# Idle sleeps vs. a CPU-busy loop, to tell wall-time billing from CPU-time billing.
DURATION_CMDS = {  # label: (command, timeout_s)
    "sleep_1s": ("sleep 1", 15),
    "sleep_60s": ("sleep 60", 75),
    "busy_10s": (
        'python -c "import time; t=time.time(); '
        '[0 for _ in iter(lambda: time.time() - t < 10, False)]"',
        20,
    ),
}


async def timed_run(
    sem: asyncio.Semaphore, guard: SpendGuard, image, label: str, cmd: str, **kw
) -> dict:
    """guarded_run under the concurrency cap, flattened to the probe's record shape."""
    submitted = time.monotonic()
    async with sem:
        started = time.monotonic()
        r = await guarded_run(guard, image, label=label, shell=cmd, **kw)
    rec = {"label": label, "cmd": cmd, "queue_s": started - submitted, "wall_s": r.client_wall_s}
    if r.error or r.cost_usd is None:
        return rec | {
            "error": r.error or "no cost reported",
            "cost_upper_bound": r.cost_upper_bound_usd,
        }
    return rec | {
        "exit_code": r.exit_code,
        "stdout": r.stdout.strip()[-200:],
        "cost": r.cost_usd,
        "server_elapsed_s": r.cpu_s,
        "resources": r.resources,
        "result_uuid": r.result_image,
        "timeout_s": r.timeout_s,
    }


def summarize(recs: list[dict]) -> dict:
    ok = [r for r in recs if "error" not in r]
    walls = [r["wall_s"] for r in ok]
    return {
        "n": len(recs),
        "ok": sum(1 for r in ok if r["exit_code"] == 0),
        "errors": [r["error"] for r in recs if "error" in r],
        "wall_min": min(walls) if walls else None,
        "wall_median": statistics.median(walls) if walls else None,
        "wall_max": max(walls) if walls else None,
        "cost_sum": sum(r["cost"] for r in ok),
        "cost_mean": statistics.mean(r["cost"] for r in ok) if ok else None,
    }


async def probe() -> dict:
    from contree_sdk import Contree
    from contree_sdk.config import ContreeConfig

    # Cap polling at 1 s so measured wall clock reflects the run, not the SDK's 10 s max backoff.
    client = Contree(ContreeConfig(operation_poll_secs_max=1.0))
    info = await client.get_token_info()
    cap = info.limits.get("instance_max_concurrency", 50)
    busy = info.operations_stat.get("running_instances", 0)
    slots = max(1, cap - busy)
    sem = asyncio.Semaphore(slots)
    guard = SpendGuard(SpendLimits.from_env(DEFAULT_CEILING_USD))
    out: dict = {
        "date": datetime.now(UTC).isoformat(timespec="seconds"),
        "limits": info.limits,
        "running_instances_at_start": busy,
        "semaphore": slots,
        "poll_secs_max": 1.0,
        "spend_ceiling_usd": guard.limits.ceiling_usd,
    }
    print(f"cap={cap} running={busy} semaphore={slots} ceiling=${guard.limits.ceiling_usd}")
    try:
        await _probe_runs(client, sem, guard, out)
    except SpendCeilingExceeded as exc:
        out["aborted"] = str(exc)
        print(f"ABORTED: {exc}")
    out["spend"] = guard.summary()
    return out


async def _probe_runs(client, sem, guard, out: dict) -> None:

    t = time.monotonic()
    base = await client.images.oci(BASE_IMAGE)
    out["import"] = {"image": BASE_IMAGE, "uuid": str(base.uuid), "wall_s": time.monotonic() - t}
    print(f"import {BASE_IMAGE}: {out['import']['wall_s']:.1f}s uuid={base.uuid}")

    ckpt_rec = await timed_run(
        sem, guard, base, "checkpoint", PREP_CMD, disposable=False, timeout_s=CHECKPOINT_TIMEOUT_S
    )
    out["checkpoint"] = ckpt_rec
    if "error" in ckpt_rec or ckpt_rec["exit_code"] != 0:
        print(f"checkpoint failed: {ckpt_rec}")
        return
    ckpt = await client.images.use(ckpt_rec["result_uuid"], strict=True)
    print(f"checkpoint: {ckpt_rec['wall_s']:.1f}s uuid={ckpt.uuid} cost={ckpt_rec['cost']}")

    out["fanout"] = []
    for n in FORK_NS:
        t = time.monotonic()
        recs = await asyncio.gather(
            *(
                timed_run(sem, guard, ckpt, f"N{n}-{i}", FORK_CMD, timeout_s=FORK_TIMEOUT_S)
                for i in range(n)
            )
        )
        total = time.monotonic() - t
        s = summarize(recs) | {"total_wall_s": total}
        out["fanout"].append({"N": n, "summary": s, "runs": recs})
        print(
            f"N={n:>2}: total {total:5.1f}s  per-fork median {s['wall_median']:.1f}s "
            f"max {s['wall_max']:.1f}s  ok {s['ok']}/{n}  cost sum {s['cost_sum']:.6g}"
        )

    t = time.monotonic()
    recs = await asyncio.gather(
        *(
            timed_run(sem, guard, ckpt, label, cmd, timeout_s=timeout_s)
            for label, (cmd, timeout_s) in DURATION_CMDS.items()
        )
    )
    out["duration"] = {"total_wall_s": time.monotonic() - t, "runs": recs}
    for r in recs:
        print(f"{r['label']}: wall {r['wall_s']:.1f}s cost {r.get('cost')} {r.get('error', '')}")


def cpu_s(r: dict) -> float:
    return r["resources"]["user_cpu_time"] + r["resources"]["system_cpu_time"]


def ols(pts: list[tuple[float, float]]) -> tuple[float, float, float]:
    """Least squares y = a + b*x; returns (a, b, r_squared)."""
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    mx, my = statistics.mean(xs), statistics.mean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    b = sum((x - mx) * (y - my) for x, y in pts) / sxx if sxx else 0.0
    a = my - b * mx
    ss_tot = sum((y - my) ** 2 for y in ys)
    ss_res = sum((y - (a + b * x)) ** 2 for x, y in pts)
    return a, b, (1 - ss_res / ss_tot) if ss_tot else 1.0


def all_runs(out: dict) -> list[dict]:
    runs = [out["checkpoint"], *out["duration"]["runs"]]
    runs += [r for f in out["fanout"] for r in f["runs"]]
    return [r for r in runs if "error" not in r and r.get("resources")]


def cost_model(out: dict) -> dict:
    """Fit cost against CPU seconds and against run wall time, over every successful run.

    resources.elapsed_time (the SDK's `.elapsed`) equals user+sys CPU time; the run's real
    duration is resources.monotonic_time. Fitting both tells us which one cost follows.
    """
    runs = all_runs(out)
    a_cpu, b_cpu, r2_cpu = ols([(cpu_s(r), r["cost"]) for r in runs])
    a_wall, b_wall, r2_wall = ols([(r["resources"]["monotonic_time"], r["cost"]) for r in runs])
    by_label = {r["label"]: r for r in runs}
    s1, s60 = by_label.get("sleep_1s"), by_label.get("sleep_60s")
    return {
        "n_runs": len(runs),
        "cpu": {"fixed": a_cpu, "per_cpu_s": b_cpu, "r2": r2_cpu},
        "wall": {"fixed": a_wall, "per_wall_s": b_wall, "r2": r2_wall},
        "sleep_60_vs_1_cost_ratio": s60["cost"] / s1["cost"] if s1 and s60 else None,
        "total_cost": sum(r["cost"] for r in runs),
    }


# Corrected per-instance model: one build (paid once, becomes the warm checkpoint), one
# regression fork running PASS_TO_PASS against the patch, and twelve forks running a single test
# function (original + test, patch + test, 10 mutants + test). PASS_TO_PASS never runs against
# a mutant: a mutant is never a candidate for acceptance.
SINGLE_TEST_FORKS = 12
REGRESSION_FORKS = 1
# (name, build CPU-s, single-test CPU-s, PASS_TO_PASS CPU-s); hypothetical until measured.
SCENARIOS = [
    ("light: build 10, test 1, P2P 5", 10, 1, 5),
    ("medium: build 30, test 3, P2P 30", 30, 3, 30),
    ("heavy: build 120, test 10, P2P 300", 120, 10, 300),
]


def instance_cost(c: dict, build: float, single: float, p2p: float) -> float:
    runs = 1 + REGRESSION_FORKS + SINGLE_TEST_FORKS
    cpu = build + REGRESSION_FORKS * p2p + SINGLE_TEST_FORKS * single
    return runs * c["fixed"] + c["per_cpu_s"] * cpu


def fmt(v, spec=".6g") -> str:
    return "n/a" if v is None else format(v, spec)


def write_md(out: dict) -> None:
    date = out["date"][:10]
    ck = out["checkpoint"]
    lines = [
        f"# Step 1 probe: fork latency and cost ({date})",
        "",
        "Produced by `scripts/probe.py`; raw per-run records are in `docs/probe_raw.json`.",
        "",
        "## Setup",
        "",
        f"- Run at {out['date']} against `https://api.tokenfactory.nebius.com/sandboxes/`, "
        "contree-sdk 0.3.6, async `Contree` client.",
        f"- Account limits (`whoami`): `{out['limits']}`; running instances at start: "
        f"{out['running_instances_at_start']}; semaphore {out['semaphore']}.",
        f"- SDK polling capped at {out['poll_secs_max']} s (default max 10 s), so wall clock "
        "includes up to ~1 s of polling granularity per run.",
        f"- Base image: `{out['import']['image']}` imported or resolved in "
        f"{out['import']['wall_s']:.1f} s (uuid `{out['import']['uuid']}`).",
        f"- Checkpoint (`disposable=False`): `{PREP_CMD}`",
        "",
    ]
    if "error" in ck or ck.get("exit_code") != 0:
        lines += ["**Checkpoint failed:**", "", "```", json.dumps(ck, indent=2), "```", ""]
        PROBE_MD.write_text("\n".join(lines))
        return
    lines += [
        "## Checkpoint",
        "",
        f"- Wall clock {ck['wall_s']:.2f} s, server elapsed {ck['server_elapsed_s']:.2f} s, "
        f"exit {ck['exit_code']}, stdout `{ck['stdout']}`",
        f"- Reported cost: `{ck['cost']}`",
        f"- Checkpoint image uuid: `{ck['result_uuid']}` (persisted; cannot be deleted)",
        "",
        '## Fan-out: `python -c "print(1)"`, `disposable=True`',
        "",
        "| N | ok | total wall s | per-fork min / median / max s | cost sum | cost per fork |",
        "|---:|---:|---:|---|---:|---:|",
    ]
    for f in out["fanout"]:
        s = f["summary"]
        lines.append(
            f"| {f['N']} | {s['ok']}/{s['n']} | {s['total_wall_s']:.2f} | "
            f"{fmt(s['wall_min'], '.2f')} / {fmt(s['wall_median'], '.2f')} / "
            f"{fmt(s['wall_max'], '.2f')} | {fmt(s['cost_sum'])} | {fmt(s['cost_mean'])} |"
        )
        if s["errors"]:
            lines.append(f"|  | errors: {'; '.join(sorted(set(s['errors'])))} | | | | |")
    lines += [
        "",
        "Client wall clock is measured from submit to result, including SDK polling. The "
        "sequential equivalent at N=50 is about 50 × the N=1 time.",
        "",
        "## Cost vs. runtime",
        "",
        "| Fork | client wall s | run wall s (`monotonic_time`) | CPU s (user+sys) | cost |",
        "|---|---:|---:|---:|---:|",
    ]
    for r in [out["checkpoint"], *out["duration"]["runs"]]:
        if "error" in r:
            lines.append(f"| `{r['label']}` | error: {r['error']} | | | |")
            continue
        lines.append(
            f"| `{r['label']}` | {r['wall_s']:.2f} | {r['resources']['monotonic_time']:.2f} | "
            f"{cpu_s(r):.4f} | {fmt(r['cost'])} |"
        )
    m = out.get("cost_model") or {}
    if m:
        c, w = m["cpu"], m["wall"]
        lines += [
            "",
            f"Least-squares fits over all {m['n_runs']} successful runs:",
            "",
            f"- cost = {fmt(c['fixed'], '.3g')} + {fmt(c['per_cpu_s'], '.5g')} × CPU_s, "
            f"R² = {c['r2']:.5f}",
            f"- cost = {fmt(w['fixed'], '.3g')} + {fmt(w['per_wall_s'], '.5g')} × wall_s, "
            f"R² = {w['r2']:.5f}",
            "",
            f"`sleep 60` cost {fmt(m['sleep_60_vs_1_cost_ratio'], '.2f')}× what `sleep 1` cost. "
            "**Cost follows CPU time, not wall time.** An idle process costs almost nothing "
            "however long it runs, and a CPU-bound process costs about "
            f"{fmt(c['per_cpu_s'], '.4g')} per CPU-second. Parallel test workers burn "
            "CPU-seconds faster than wall-seconds, so parallelism saves time but not money.",
            "",
            "The SDK's `.elapsed` (`resources.elapsed_time`) equals user+sys CPU time, "
            "not wall time. Real run duration is `resources.monotonic_time`.",
            "",
            f"Total reported cost of this probe: **{fmt(m['total_cost'], '.6g')}** "
            "(the unit is not documented).",
            "",
            "## Extrapolation (reported cost units; USD per the reconciliation below)",
            "",
            "**Corrected model (2026-10-25).** An earlier version of this section priced 13 "
            "forks at equal cost. That was wrong. PASS_TO_PASS never runs against a mutant, "
            "because a mutant is never a candidate for acceptance. Per instance:",
            "",
            "- 1 build, paid once; its result is the warm checkpoint;",
            "- 1 regression fork: patched code + PASS_TO_PASS;",
            "- 12 single-test forks: original + test, patch + test, 10 mutants + test, "
            "each running one test function.",
            "",
            "cost(instance) = 14 × per-run fee + rate × (build + P2P + 12 × single-test) CPU-s.",
            "",
            "The scenarios below are hypothetical. **Measured values for three real SWE-bench "
            "Verified instances are in `docs/probe_instances.md`.**",
            "",
            "| Scenario (CPU-s) | CPU s per instance | 1 instance | 5 instances |",
            "|---|---:|---:|---:|",
        ]
        for name, build, single, p2p in SCENARIOS:
            cpu = build + REGRESSION_FORKS * p2p + SINGLE_TEST_FORKS * single
            one = instance_cost(c, build, single, p2p)
            lines.append(f"| {name} | {cpu:,.0f} | ${one:.3f} | ${5 * one:.2f} |")
        lines += ["", "## Billing reconciliation", ""]
        if out.get("billing_delta"):
            lines += [
                f"Token Factory console billing rose by **{out['billing_delta']}** across the "
                f"probe run, against an SDK-reported total of {fmt(m['total_cost'], '.6g')}. "
                "**The SDK's `cost` field is USD**, so Sandboxes are billed: about "
                f"${m['cpu']['per_cpu_s']:.4f} per CPU-second "
                f"(${m['cpu']['per_cpu_s'] * 3600:.2f} per CPU-hour) plus "
                f"${m['cpu']['fixed']:.1e} per run. The figure was read by hand from one "
                "before/after pair at the console's display precision.",
            ]
        else:
            lines.append(
                "_Pending: compare the console billing delta across the probe run against "
                f"the total of {fmt(m['total_cost'], '.6g')}._"
            )
    PROBE_MD.write_text("\n".join(lines) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--from-json", type=Path, help="re-render docs/probe.md from saved raw JSON; no runs"
    )
    parser.add_argument(
        "--billing-delta",
        help="console billing change across the run, as read by hand (e.g. '0.13 USD')",
    )
    args = parser.parse_args()
    if args.from_json:
        out = json.loads(args.from_json.read_text())
        out["cost_model"] = cost_model(out)
        if args.billing_delta:
            out["billing_delta"] = args.billing_delta
        args.from_json.write_text(json.dumps(out, indent=2, default=str) + "\n")
        write_md(out)
        print(f"Re-rendered {PROBE_MD.relative_to(ROOT)} from {args.from_json}")
        return 0
    load_dotenv(ROOT / ".env")
    out = asyncio.run(probe())
    if "duration" in out:
        out["cost_model"] = cost_model(out)
    PROBE_JSON.write_text(json.dumps(out, indent=2, default=str) + "\n")
    write_md(out)
    print(f"Wrote {PROBE_MD.relative_to(ROOT)} and {PROBE_JSON.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
