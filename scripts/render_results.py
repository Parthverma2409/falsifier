"""Render the phase 3 comparison from saved evidence only: reports/instances/<id>.json. No runs.

Writes reports/instances/index.html and docs/results.md. Instances without saved evidence are
listed as not completed, with the reason given on the command line.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import fields
from pathlib import Path

from falsifier.config import ROOT
from falsifier.evidence import (
    CAUGHT_BY_P2P,
    SURVIVED,
    MutantResult,
    Verdict,
    pytest_summary,
    witness_result,
)
from falsifier.instance import load_swebench
from falsifier.official import load_rows
from falsifier.report import SCOPE, comparison, comparison_rows, write
from falsifier.verify import describe_witness

OUT = ROOT / "reports" / "instances"
INSTANCES = [
    "pallets__flask-5014",
    "psf__requests-5414",
    "psf__requests-6028",
    "pytest-dev__pytest-7432",
    "pytest-dev__pytest-7571",
]


def load(iid: str, out=OUT) -> tuple[Verdict, dict, dict] | None:
    path = out / f"{iid}.json"
    if not path.exists():
        return None
    d = json.loads(path.read_text())
    keep = {f.name for f in fields(MutantResult)}
    mutants = [MutantResult(**{k: v for k, v in m.items() if k in keep}) for m in d["mutants"]]
    vkeep = {f.name for f in fields(Verdict)} - {"mutants"}
    v = Verdict(mutants=mutants, **{k: d[k] for k in vkeep if k in d})  # re-validates evidence
    gen = out / f"{iid}.generation.json"
    return v, d["official"], json.loads(gen.read_text()) if gen.exists() else {}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--missing-reason", default="not run")
    ap.add_argument("--dir", default=str(OUT), help="evidence directory (e.g. escalation-30)")
    ap.add_argument("--md", default=str(ROOT / "docs" / "results.md"))
    args = ap.parse_args()
    out = ROOT / args.dir if not args.dir.startswith("/") else Path(args.dir)
    excl_path = out / "exclusions.json"
    exclusions = json.loads(excl_path.read_text())["instances"] if excl_path.exists() else None
    ids = sorted(exclusions) if exclusions else INSTANCES
    loaded = {
        iid: load(iid, out) if not exclusions or exclusions[iid].get("included") else None
        for iid in ids
    }
    done = {iid: x for iid, x in loaded.items() if x}
    missing = {
        iid: (
            f"{exclusions[iid]['reason']}: {exclusions[iid].get('detail', '')}"[:300]
            if exclusions
            else args.missing_reason
        )
        for iid, x in loaded.items()
        if not x
    }
    verdicts = [x[0] for x in done.values()]
    officials = {iid: x[1] for iid, x in done.items()}
    comparison(verdicts, officials, out, missing)
    rows_by_id = load_rows(list(done))
    for iid, (v, official_d, _) in done.items():  # re-render each page from saved evidence
        write(v, load_swebench(rows_by_id[iid]), out, official_d)
    rows = comparison_rows(verdicts, officials)
    L = [
        "# Results",
        "",
        f"**{SCOPE}**",
        "",
        "| Instance | Benchmark oracle | SWE-bench says | Falsifier says | Distinguishable mutants"
        " | Equivalent discarded | Survived FAIL_TO_PASS | **Survived both lists** | Canary exit"
        " | Mutants generated |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        gen = done[r["instance"]][2]
        L.append(
            f"| `{r['instance']}` | {r['oracle']} | {r['swebench']} | **{r['falsifier']}** | "
            f"{r['distinguishable']} | {r['equivalent']} | {r['survived_f2p']} | "
            f"**{r['survived_both']}** | {r['canary_exit']} | "
            f"{gen.get('returned', '?')} of {gen.get('asked', '?')} |"
        )
    if exclusions:
        L += [
            "",
            f"**{len(ids)} instances enumerated, {len(done)} included.** Why each of the "
            f"{len(missing)} others is out:",
            "",
        ]
        L += [f"- `{iid}`: {why}" for iid, why in missing.items()]
    else:
        L += [f"| `{iid}` | not completed: {why} | | | | | | | | |" for iid, why in missing.items()]
    headline = sum(r["survived_both"] for r in rows)
    L += [
        "",
        f"**Headline: {headline} mutant(s) cleared both FAIL_TO_PASS and PASS_TO_PASS** across "
        f"{len(rows)} instance(s), i.e. SWE-bench's full resolution criterion, while provably "
        "behaving differently from the gold patch on their own witness.",
    ]
    L += [
        "",
        '"Benchmark oracle" means the repository\'s own FAIL_TO_PASS tests, not a reproduction of '
        "SWE-bench's harness. Every distinguishable survivor of FAIL_TO_PASS is also run "
        "against PASS_TO_PASS: UNEARNED means a mutant cleared both lists; UNPINNED means "
        "PASS_TO_PASS caught every such mutant. Full evidence: "
        "`reports/instances/<instance>.html` and `.json`.",
        "",
        "## Survivors of FAIL_TO_PASS",
        "",
    ]
    for iid, (v, _, _) in done.items():
        for m in v.mutants:
            if m.status not in (SURVIVED, CAUGHT_BY_P2P):
                continue
            a, b = witness_result(m.witness_patched), witness_result(m.witness_mutant)
            L += [
                f"### `{iid}` {m.id} ({m.kind}): "
                + (
                    "cleared FAIL_TO_PASS and PASS_TO_PASS"
                    if m.status == SURVIVED
                    else "caught by PASS_TO_PASS"
                ),
                "",
                f"Rationale (the model's words): {m.rationale}",
                "",
                "```diff",
                m.diff.rstrip("\n"),
                "```",
                "",
                f"The test that missed it: `{' '.join(done[iid][1]['fail_to_pass'])}`, "
                f"exit {m.test['exit_code']} on the mutant ({m.test_why}).",
                "",
                "Witness:",
                "",
                "```python",
                m.witness.rstrip("\n"),
                "```",
                "",
                f"- Patch (exit {m.witness_patched['exit_code']}): {describe_witness(a)}",
                f"- Mutant (exit {m.witness_mutant['exit_code']}): {describe_witness(b)}",
                f"- PASS_TO_PASS on the mutant (exit {m.p2p['exit_code']}, "
                f"{pytest_summary(m.p2p['stdout'])}): "
                + (
                    "every PASS_TO_PASS test PASSED"
                    if not m.p2p_missing
                    else f"{len(m.p2p_missing)} not PASSED, e.g. {', '.join(m.p2p_missing[:3])}"
                ),
                "",
            ]
    Path(args.md).write_text("\n".join(L))
    for r in rows:
        print(
            f"{r['instance']}: distinguishable {r['distinguishable']}; equivalent discarded "
            f"{r['equivalent']}; survived FAIL_TO_PASS {r['survived_f2p']}; of those also "
            f"survived PASS_TO_PASS {r['survived_both']}; verdict {r['falsifier']}; canary exit "
            f"{r['canary_exit']}"
        )
    print(f"headline: {headline} mutant(s) cleared both lists")
    for iid, why in missing.items():
        print(f"{iid}: not completed ({why})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
