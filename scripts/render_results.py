"""Render the phase 3 comparison from saved evidence only: reports/instances/<id>.json. No runs.

Writes reports/instances/index.html and docs/results.md. Instances without saved evidence are
listed as not completed, with the reason given on the command line.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import fields

from falsifier.config import ROOT
from falsifier.evidence import SURVIVED, MutantResult, Verdict, witness_result
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


def load(iid: str) -> tuple[Verdict, dict, dict] | None:
    path = OUT / f"{iid}.json"
    if not path.exists():
        return None
    d = json.loads(path.read_text())
    keep = {f.name for f in fields(MutantResult)}
    mutants = [MutantResult(**{k: v for k, v in m.items() if k in keep}) for m in d["mutants"]]
    vkeep = {f.name for f in fields(Verdict)} - {"mutants"}
    v = Verdict(mutants=mutants, **{k: d[k] for k in vkeep if k in d})  # re-validates evidence
    gen = OUT / f"{iid}.generation.json"
    return v, d["official"], json.loads(gen.read_text()) if gen.exists() else {}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--missing-reason", default="not run")
    args = ap.parse_args()
    loaded = {iid: load(iid) for iid in INSTANCES}
    done = {iid: x for iid, x in loaded.items() if x}
    missing = {iid: args.missing_reason for iid, x in loaded.items() if not x}
    verdicts = [x[0] for x in done.values()]
    officials = {iid: x[1] for iid, x in done.items()}
    comparison(verdicts, officials, OUT, missing)
    rows_by_id = load_rows(list(done))
    for iid, (v, official_d, _) in done.items():  # re-render each page from saved evidence
        write(v, load_swebench(rows_by_id[iid]), OUT, official_d)
    rows = comparison_rows(verdicts, officials)
    L = [
        "# Results",
        "",
        f"**{SCOPE}**",
        "",
        "| Instance | Benchmark oracle | SWE-bench says | Falsifier says | Killed / distinguishable"
        " | Equivalent discarded | Canary exit | Mutants generated |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        gen = done[r["instance"]][2]
        L.append(
            f"| `{r['instance']}` | {r['oracle']} | {r['swebench']} | **{r['falsifier']}** | "
            f"{r['killed']} / {r['distinguishable']} | {r['equivalent']} | {r['canary_exit']} | "
            f"{gen.get('returned', '?')} of {gen.get('asked', '?')} |"
        )
    L += [f"| `{iid}` | not completed: {why} | | | | | | |" for iid, why in missing.items()]
    L += [
        "",
        '"Benchmark oracle" means the repository\'s own FAIL_TO_PASS tests, not a reproduction of '
        "SWE-bench's harness. Under Configuration A mutants never run against PASS_TO_PASS, so "
        "UNEARNED means the FAIL_TO_PASS tests do not pin the behaviour, not that nothing in the "
        "repository would. Full evidence: `reports/instances/<instance>.html` and `.json`.",
        "",
        "## Survivors",
        "",
    ]
    for iid, (v, _, _) in done.items():
        for m in v.mutants:
            if m.status != SURVIVED:
                continue
            a, b = witness_result(m.witness_patched), witness_result(m.witness_mutant)
            L += [
                f"### `{iid}` {m.id} ({m.kind})",
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
                "",
            ]
    (ROOT / "docs" / "results.md").write_text("\n".join(L))
    for r in rows:
        print(
            f"{r['instance']}: oracle {r['oracle']}; SWE-bench {r['swebench']}; Falsifier "
            f"{r['falsifier']}; killed {r['killed']} of {r['distinguishable']}; equivalent "
            f"{r['equivalent']}; canary exit {r['canary_exit']}"
        )
    for iid, why in missing.items():
        print(f"{iid}: not completed ({why})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
