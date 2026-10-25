"""Step 1 gate, cost half: measure real SWE-bench Verified instances under the spend rails.

For each instance: import the official harness image, build the warm checkpoint (the eval
script's install step), then measure in disposable forks of it: bare interpreter start, an empty
test in the target test directory, one targeted FAIL_TO_PASS test function, the full
PASS_TO_PASS list, and PASS_TO_PASS trimmed to the module holding the targeted test.

Every run goes through falsifier.sandbox.guarded_run: explicit timeout, one pinned CPU, and a
spend ceiling checked before launch.
Writes docs/probe_instances.md and docs/probe_instances_raw.json.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import shlex
import statistics
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv

from falsifier.config import USD_PER_CPU_SECOND, USD_PER_RUN, SpendLimits
from falsifier.sandbox import SpendCeilingExceeded, SpendGuard, guarded_run

ROOT = Path(__file__).resolve().parent.parent
OUT_MD = ROOT / "docs" / "probe_instances.md"
OUT_JSON = ROOT / "docs" / "probe_instances_raw.json"

DATASET = "SWE-bench/SWE-bench_Verified"
INSTANCES = ("pallets__flask-5014", "psf__requests-5414", "pytest-dev__pytest-7432")
CANDIDATE_REPOS = ("pallets/flask", "psf/requests", "pytest-dev/pytest")
PACKAGE = {"pallets/flask": "flask", "psf/requests": "requests", "pytest-dev/pytest": "pytest"}
CEILING_USD = 0.85  # $1 minus $0.127 already reported today (cores check, attempts 1-3)
TRANSPORT_TIMEOUT_S = 30.0  # SDK default 10 s; attempt 2 lost two runs to upload read timeouts
UPLOAD_ATTEMPTS = 3
IMPORT_TIMEOUT_S = 900
TIMEOUT_S = {"conda": 20, "build": 60, "interp": 10, "empty": 20, "targeted": 30, "p2p": 40}
REPEATS = {"empty": 2, "targeted": 2}
SINGLE_TEST_FORKS = 12

# Sandboxes run with no $HOME, so git config --global fails; set it. The harness uses
# `conda activate testbed`; we put the env on PATH instead, and measure the
# activation overhead once to show what that saves per fork.
ENV = "export HOME=/root PATH=/opt/miniconda3/envs/testbed/bin:$PATH && cd /testbed"
CONDA_ENV = (
    "export HOME=/root && . /opt/miniconda3/bin/activate && conda activate testbed && cd /testbed"
)
SUMMARY_RE = re.compile(r"=+ (.*\b(?:passed|failed|error|errors|skipped|deselected)\b.*) =+\s*$")


def as_list(v) -> list[str]:
    return json.loads(v) if isinstance(v, str) else list(v)


def install_steps(eval_script: str) -> list[str]:
    """The install lines the harness runs: after the second `conda activate testbed`, up to the
    first `git checkout`."""
    lines = eval_script.splitlines()
    acts = [i for i, ln in enumerate(lines) if ln.strip() == "conda activate testbed"]
    out = []
    for ln in lines[acts[1] + 1 :]:
        if ln.startswith("git checkout") or ln.startswith("git apply"):
            break
        if ln.strip():
            out.append(ln.strip())
    return out


def module_of(test_id: str) -> str:
    return test_id.split("::")[0]


def test_patch_files(test_patch: str) -> list[str]:
    return [
        ln[len("diff --git a/") :].split(" ")[0]
        for ln in test_patch.splitlines()
        if ln.startswith("diff --git a/")
    ]


def passed_in_log(stdout: str) -> set[str]:
    """Ids reported PASSED in a `pytest -rA` short summary, truncated at the first space the same
    way SWE-bench's log parser truncates them, so they compare directly with PASS_TO_PASS."""
    return {ln.split(" ", 2)[1] for ln in stdout.splitlines() if ln.startswith("PASSED ")}


def load_instances(ids, repos) -> tuple[dict, list[dict]]:
    from datasets import load_dataset

    ds = load_dataset(DATASET, split="test")
    pool = [dict(r) for r in ds if r["repo"] in repos]
    for r in pool:
        r["F2P"], r["P2P"] = as_list(r["FAIL_TO_PASS"]), as_list(r["PASS_TO_PASS"])
    by_id = {r["instance_id"]: r for r in pool}
    return {i: by_id[i] for i in ids}, pool


def pytest_summary(stdout: str) -> str | None:
    for line in reversed(stdout.strip().splitlines()):
        m = SUMMARY_RE.search(line)
        if m:
            return m.group(1)
    return None


def slim(rec) -> dict:
    d = rec.to_dict()
    d["stdout_tail"] = d.pop("stdout")[-3000:]
    d["stderr_tail"] = d.pop("stderr")[-2000:]
    d["pytest_summary"] = pytest_summary(rec.stdout)
    return d


async def upload(client, cache: dict, data: bytes):
    """Upload outside the guarded run, with retries, so an upload stall cannot consume budget."""
    key = hashlib.sha256(data).hexdigest()
    if key in cache:
        return cache[key]
    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(data)
    for attempt in range(1, UPLOAD_ATTEMPTS + 1):
        try:
            cache[key] = await client.files.upload(f.name)
            break
        except Exception as exc:
            print(f"  upload attempt {attempt} failed: {type(exc).__name__}")
            if attempt == UPLOAD_ATTEMPTS:
                raise
            await asyncio.sleep(2 * attempt)
    Path(f.name).unlink()
    return cache[key]


async def measure(
    client, guard: SpendGuard, rows: dict, out: dict, reuse: dict | None, reuse_forks: bool
) -> None:
    patches = "/tmp/falsifier"
    uploaded: dict = {}
    t = time.monotonic()
    imported = await asyncio.gather(
        *(client.images.oci(r["image"], timeout=IMPORT_TIMEOUT_S) for r in rows.values())
    )
    for (iid, r), img in zip(rows.items(), imported, strict=True):
        out["instances"][iid]["import"] = {"image": r["image"], "uuid": str(img.uuid)}
    out["import_wall_s"] = time.monotonic() - t
    print(f"imported {len(rows)} images in {out['import_wall_s']:.0f}s")
    bases = dict(zip(rows, imported, strict=True))

    async def run(iid, label, image, shell, kind, **kw):
        rec = await guarded_run(
            guard, image, label=f"{iid}:{label}", shell=shell, timeout_s=TIMEOUT_S[kind], **kw
        )
        out["instances"][iid].setdefault("runs", {}).setdefault(label, []).append(slim(rec))
        print(
            f"  {iid:<26} {label:<12} exit={rec.exit_code} cpu={rec.cpu_s} "
            f"wall={rec.run_wall_s} ${rec.cost_usd} {rec.error or ''} "
            f"[{pytest_summary(rec.stdout) or ''}] spent=${guard.spent_usd:.4f}"
        )
        return rec

    ckpts = {}
    if reuse:  # build records and warm checkpoints from an earlier run of this script
        for iid in rows:
            prev = reuse["instances"].get(iid, {}).get("runs", {})
            for label in ("conda", "build"):
                if label in prev:
                    out["instances"][iid].setdefault("runs", {})[label] = prev[label]
            if reuse_forks:
                for label in ("interp", "empty", "targeted"):
                    if label in prev:
                        out["instances"][iid]["runs"][label] = prev[label]
            ok = [b for b in prev.get("build", []) if b["exit_code"] == 0 and b["result_image"]]
            if ok:
                ckpts[iid] = await client.images.use(ok[-1]["result_image"], strict=True)
                print(f"  {iid:<26} reusing checkpoint {ok[-1]['result_image']}")
        out["reused_builds_from"] = reuse.get("date")
        out["reused_forks"] = reuse_forks

    first = next(iter(rows))
    if not reuse:
        await run(first, "conda", bases[first], f"{CONDA_ENV} && python -c pass", "conda")

    for iid, r in rows.items():
        if iid in ckpts:
            continue
        pkg = PACKAGE[r["repo"]]
        build = (
            f"{ENV} && git config --global --add safe.directory /testbed && "
            + " && ".join(install_steps(r["eval_script"]))
            + f" && python -c 'import {pkg}; print(\"IMPORTED_FROM\", {pkg}.__file__)'"
        )
        rec = await run(iid, "build", bases[iid], build, "build", disposable=False)
        if rec.exit_code != 0 or not rec.result_image:
            print(f"  build failed for {iid}; skipping its forks")
            continue
        ckpts[iid] = await client.images.use(rec.result_image, strict=True)

    for iid, ckpt in ckpts.items() if not reuse_forks else ():
        r = rows[iid]
        target = r["F2P"][0]
        testdir = str(Path(module_of(target)).parent)
        files = {f"{patches}/test.patch": await upload(client, uploaded, r["test_patch"].encode())}
        await run(iid, "interp", ckpt, f"{ENV} && python -c pass", "interp")
        empty = (
            f"{ENV} && printf 'def test_falsifier_empty():\\n    pass\\n' "
            f"> {testdir}/test_falsifier_empty.py && pytest -rA {testdir}/test_falsifier_empty.py"
        )
        for _ in range(REPEATS["empty"]):
            await run(iid, "empty", ckpt, empty, "empty")
        targeted = f"{ENV} && git apply {patches}/test.patch && pytest -rA {shlex.quote(target)}"
        for _ in range(REPEATS["targeted"]):
            await run(iid, "targeted", ckpt, targeted, "targeted", files=files)

    # PASS_TO_PASS ids are log-parser keys, truncated at the first space, not runnable node ids
    # (attempt 3: pytest exit 4, "not found"). Like the harness, run the test files the test
    # patch touches and grade from the -rA log.
    for iid, ckpt in ckpts.items():
        r = rows[iid]
        target_mod = module_of(r["F2P"][0])
        full_files = test_patch_files(r["test_patch"])
        variants = [("p2p_full", full_files)]
        if set(full_files) != {target_mod}:
            variants.append(("p2p_trimmed", [target_mod]))
        else:
            out["instances"][iid]["p2p_trimmed_identical"] = True
        for label, test_files in variants:
            files = {
                f"{patches}/test.patch": await upload(client, uploaded, r["test_patch"].encode()),
                f"{patches}/gold.patch": await upload(client, uploaded, r["patch"].encode()),
            }
            cmd = (
                f"{ENV} && git apply {patches}/gold.patch && git apply {patches}/test.patch && "
                f"pytest -rA {' '.join(shlex.quote(f) for f in test_files)}"
            )
            rec = await run(iid, label, ckpt, cmd, "p2p", files=files)
            expected = [t for t in r["P2P"] if module_of(t) in test_files]
            seen = passed_in_log(rec.stdout)
            out["instances"][iid].setdefault("p2p_coverage", {})[label] = {
                "expected": len(expected),
                "passed_in_log": sum(1 for t in expected if t in seen),
                "missing": [t for t in expected if t not in seen][:20],
            }


def mean(xs):
    xs = [x for x in xs if x is not None]
    return statistics.mean(xs) if xs else None


def analyse(out: dict, pool: list[dict]) -> None:
    per_repo = {}
    for iid, d in out["instances"].items():
        runs = d.get("runs", {})

        def m(label, key, runs=runs):
            return mean(r[key] for r in runs.get(label, []) if not r.get("error"))

        a = {
            k: {"cpu": m(k, "cpu_s"), "usd": m(k, "cost_usd"), "wall": m(k, "run_wall_s")}
            for k in ("conda", "build", "interp", "empty", "targeted", "p2p_full", "p2p_trimmed")
        }
        if a["p2p_trimmed"]["usd"] is None and d.get("p2p_trimmed_identical"):
            a["p2p_trimmed"] = a["p2p_full"]
        if a["targeted"]["cpu"] and a["empty"]["cpu"] is not None:
            a["overhead_share"] = a["empty"]["cpu"] / a["targeted"]["cpu"]
            a["interp_share"] = (a["interp"]["cpu"] or 0) / a["targeted"]["cpu"]
        b, t = a["build"]["usd"], a["targeted"]["usd"]
        for variant in ("p2p_full", "p2p_trimmed"):
            p = a[variant]["usd"]
            if None not in (b, t, p):
                a[f"instance_usd_{variant}"] = b + p + SINGLE_TEST_FORKS * t
        d["analysis"] = a
        n_p2p = len(d["P2P"])
        if None not in (a["p2p_full"]["usd"], a["empty"]["usd"]) and n_p2p:
            per_test = max(0.0, (a["p2p_full"]["usd"] - a["empty"]["usd"]) / n_p2p)
            per_repo[d["repo"]] = {
                "build": b,
                "targeted": t,
                "empty": a["empty"]["usd"],
                "per_p2p_test": per_test,
                "from": iid,
            }
    out["per_repo"] = per_repo
    est = []
    for r in pool:
        k = per_repo.get(r["repo"])
        if not k or None in (k["build"], k["targeted"]):
            continue
        p2p = k["empty"] + k["per_p2p_test"] * len(r["P2P"])
        est.append(
            {
                "instance_id": r["instance_id"],
                "repo": r["repo"],
                "version": r["version"],
                "p2p_n": len(r["P2P"]),
                "f2p_n": len(r["F2P"]),
                "p2p_modules": len({module_of(t) for t in r["P2P"]}),
                "est_usd": k["build"] + p2p + SINGLE_TEST_FORKS * k["targeted"],
                "measured": r["instance_id"] in out["instances"],
            }
        )
    out["estimates"] = sorted(est, key=lambda e: e["est_usd"])


def ledger(paths: list[Path], out: dict) -> dict:
    """Distinct runs across this run and earlier attempts (reused records are copies, so dedupe
    on label + start time), with their SDK-reported cost."""
    seen, total, unreported = set(), 0.0, 0
    for doc in [*(json.loads(p.read_text()) for p in paths), out]:
        for d in doc["instances"].values():
            for recs in d.get("runs", {}).values():
                for r in recs:
                    key = (r["label"], r["started_at"])
                    if key in seen:
                        continue
                    seen.add(key)
                    if r["cost_usd"] is None:
                        unreported += 1
                    else:
                        total += r["cost_usd"]
    return {
        "files": [str(p) for p in paths],
        "distinct_runs": len(seen),
        "reported_usd": total,
        "runs_without_cost": unreported,
    }


def money(v, d=4) -> str:
    return "n/a" if v is None else f"${v:.{d}f}"


def num(v, d=2) -> str:
    return "n/a" if v is None else f"{v:.{d}f}"


def write_md(out: dict) -> None:
    L = [
        f"# Step 1 gate, cost half: real-instance measurements ({out['date'][:10]})",
        "",
        "Produced by `scripts/probe_instances.py`; raw records in "
        "`docs/probe_instances_raw.json`. The corrected cost model is in `docs/probe.md`.",
        "",
        "## Method",
        "",
        f"- Dataset `{DATASET}`. The images are the official harness images "
        "(`swebench/sweb.eval.x86_64.*`), imported with `images.oci()`, so the environment "
        "is exactly the one the official verdict uses.",
        "- **Build** is the eval script's install step (`pip install .` or `-e .`) run once "
        "with `disposable=False`. The result is the warm checkpoint, and every other run is a "
        "disposable fork of it.",
        "- **interp** is `python -c pass`. **empty** writes `def test_falsifier_empty(): pass` "
        "into the targeted test's directory, so the same conftest and plugins load, then runs "
        "`pytest -rA` on it. **targeted** applies the test patch and runs the first "
        "FAIL_TO_PASS id. **p2p_full** applies the gold and test patches and runs the "
        "harness command, `pytest -rA <files the test patch touches>`. The PASS_TO_PASS ids "
        "are log-parser keys truncated at the first space, not runnable node ids, so the "
        "harness never selects by id and neither do we. **p2p_trimmed** runs only the "
        "targeted test's module. Coverage counts the PASS_TO_PASS ids the -rA log "
        "reports PASSED.",
        f"- Rails: every run has an explicit timeout ({out['timeouts']}) and is pinned to "
        f"one CPU, under a spend ceiling of ${out['spend']['ceiling_usd']:.2f} checked "
        "before each launch at worst case.",
        f"- Sandbox: {out.get('nproc', '4')} vCPUs; pinned, so CPU-s ≤ wall-s.",
        "",
    ]
    if out.get("aborted"):
        L += [f"**Run aborted by the spend ceiling:** {out['aborted']}", ""]
    L += ["## Per instance", ""]
    for iid, d in out["instances"].items():
        a = d.get("analysis", {})
        L += [
            f"### `{iid}` ({d['repo']} {d['version']}; F2P {len(d['F2P'])}, "
            f"P2P {len(d['P2P'])} in {len({module_of(t) for t in d['P2P']})} module(s))",
            "",
            "| Run | n | CPU s | run wall s | USD | pytest summary |",
            "|---|---:|---:|---:|---:|---|",
        ]
        for label, recs in d.get("runs", {}).items():
            ok = [r for r in recs if not r.get("error")]
            errs = [r["error"] for r in recs if r.get("error")]
            summ = "; ".join(sorted({r["pytest_summary"] or "" for r in ok}))
            err_note = " " + "; ".join(errs) if errs else ""
            to = " (timed out)" if any(r.get("timed_out") for r in ok) else ""
            L.append(
                f"| {label}{to} | {len(recs)} | {num(mean(r['cpu_s'] for r in ok), 3)} | "
                f"{num(mean(r['run_wall_s'] for r in ok))} | "
                f"{money(mean(r['cost_usd'] for r in ok), 5)} | {summ}{err_note} |"
            )
        for label, c in d.get("p2p_coverage", {}).items():
            L.append(
                f"| {label} coverage | | | | | {c['passed_in_log']}/{c['expected']} "
                "PASS_TO_PASS ids PASSED in the log |"
            )
        if d.get("p2p_trimmed_identical"):
            L.append(
                "| p2p_trimmed | = p2p_full | | | | "
                "the test patch touches only the targeted module |"
            )
        imp = next(
            (r for r in d.get("runs", {}).get("build", []) if "IMPORTED_FROM" in r["stdout_tail"]),
            None,
        )
        if imp:
            where = imp["stdout_tail"].split("IMPORTED_FROM", 1)[1].split()[0]
            L += ["", f"Package imported from `{where}` after the build."]
        if "overhead_share" in a:
            L += [
                "",
                f"Overhead: the empty test uses **{a['overhead_share']:.0%}** of the targeted "
                f"test's CPU, and a bare interpreter start uses {a['interp_share']:.0%}. "
                "The test body itself is "
                f"{num(a['targeted']['cpu'] - a['empty']['cpu'], 3)} CPU-s.",
            ]
        if "instance_usd_p2p_full" in a:
            L += [
                "",
                "**Per-instance cost, corrected model** "
                f"(build + 1 P2P fork + {SINGLE_TEST_FORKS} single-test forks): "
                f"**{money(a['instance_usd_p2p_full'], 3)}** with full P2P, "
                f"{money(a.get('instance_usd_p2p_trimmed'), 3)} with trimmed P2P.",
            ]
        L.append("")
    est = out.get("estimates", [])
    if est:
        L += [
            "## Estimated cost for every instance in these three repos",
            "",
            "These are estimates, not measurements. Build, targeted and empty costs come from "
            "the measured instance in the same repo. "
            "P2P = empty + (measured per-test P2P cost × the "
            "instance's P2P count).",
            "",
            "| Instance | version | F2P | P2P | P2P modules | est. USD / instance | measured |",
            "|---|---|---:|---:|---:|---:|---|",
        ]
        for e in est:
            L.append(
                f"| `{e['instance_id']}` | {e['version']} | {e['f2p_n']} | {e['p2p_n']} | "
                f"{e['p2p_modules']} | {money(e['est_usd'], 3)} | "
                f"{'yes' if e['measured'] else ''} |"
            )
        L.append("")
    s = out["spend"]
    led = out.get("ledger")
    L += ["## What the measurement cost", ""]
    if led:
        L += [
            f"- **All attempts, SDK-reported: {money(led['reported_usd'])}** over "
            f"{led['distinct_runs']} distinct runs ({led['runs_without_cost']} runs failed "
            "before launch and reported no cost). Earlier attempts are kept locally in `runs/` "
            "(gitignored); "
            "see `docs/plan_deviations.md` for why each one stopped.",
        ]
    L += [
        f"- This run: {money(s['spent_usd'])} over {s['runs']} runs "
        f"(ceiling ${s['ceiling_usd']:.2f}; {s['unreported_cost_runs']} runs without a "
        "reported cost, charged at their worst case).",
        f"- Image imports: {len(out['instances'])} × ~1 GB in "
        f"{num(out.get('import_wall_s'), 0)} s. "
        "The SDK reports no cost for imports.",
        f"- Console billing delta: {out.get('billing_delta', '_pending_')}",
        "",
    ]
    OUT_MD.write_text("\n".join(L))


async def main_async(out: dict, rows: dict, reuse: dict | None, reuse_forks: bool) -> None:
    from contree_sdk import Contree
    from contree_sdk.config import ContreeConfig

    client = Contree(
        ContreeConfig(operation_poll_secs_max=1.0, transport_timeout=TRANSPORT_TIMEOUT_S)
    )
    info = await client.get_token_info()
    out["running_instances_at_start"] = info.operations_stat.get("running_instances")
    guard = SpendGuard(SpendLimits(ceiling_usd=CEILING_USD))
    try:
        await measure(client, guard, rows, out, reuse, reuse_forks)
    except SpendCeilingExceeded as exc:
        out["aborted"] = str(exc)
        print(f"ABORTED: {exc}")
    out["spend"] = guard.summary()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--from-json", type=Path, help="re-render from saved raw JSON; no runs")
    ap.add_argument("--billing-delta", help="console billing change across the run, read by hand")
    ap.add_argument(
        "--reuse-builds", type=Path, help="raw JSON of an earlier run: reuse its builds"
    )
    ap.add_argument(
        "--reuse-forks", action="store_true", help="also reuse its interp/empty/targeted runs"
    )
    ap.add_argument(
        "--prior-attempts", type=Path, nargs="*", default=[], help="raw JSON of earlier attempts"
    )
    args = ap.parse_args()
    rows, pool = load_instances(INSTANCES, CANDIDATE_REPOS)
    if args.from_json:
        out = json.loads(args.from_json.read_text())
    else:
        load_dotenv(ROOT / ".env")
        out = {
            "date": datetime.now(UTC).isoformat(timespec="seconds"),
            "timeouts": TIMEOUT_S,
            "rates": {"usd_per_cpu_s": USD_PER_CPU_SECOND, "usd_per_run": USD_PER_RUN},
            "instances": {
                iid: {k: r[k] for k in ("repo", "version", "image", "F2P", "P2P")}
                for iid, r in rows.items()
            },
        }
        reuse = json.loads(args.reuse_builds.read_text()) if args.reuse_builds else None
        asyncio.run(main_async(out, rows, reuse, args.reuse_forks))
    if args.billing_delta:
        out["billing_delta"] = args.billing_delta
    analyse(out, pool)
    if args.prior_attempts:
        out["ledger"] = ledger(args.prior_attempts, out)
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str) + "\n")
    write_md(out)
    print(f"Wrote {OUT_MD.relative_to(ROOT)}; spent ${out['spend']['spent_usd']:.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
