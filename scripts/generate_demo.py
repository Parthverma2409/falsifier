"""One live propose_mutants run on a SWE-bench Verified instance's gold patch.

Checks the repo out at the instance's base commit under .cache/repos (gitignored; files are read,
never executed), asks Nemotron for N mutants, and writes docs/generate_demo.md with the prompt,
per-round accept/reject counts, every mutant with its rationale, and the token cost. Responses are
cached, so reruns are free.
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv

from falsifier.config import ROOT
from falsifier.generate import LLM, MUTANT_PROMPT, propose_mutants

OUT_MD = ROOT / "docs" / "generate_demo.md"
FIXTURE = ROOT / "tests" / "fixtures" / "generate"


def checkout(repo: str, commit: str, dest: Path) -> Path:
    if not (dest / ".git").exists():
        dest.mkdir(parents=True, exist_ok=True)
        git = ["git", "-C", str(dest)]
        subprocess.run([*git, "init", "-q"], check=True)
        subprocess.run(
            [*git, "remote", "add", "origin", f"https://github.com/{repo}.git"], check=True
        )
        subprocess.run([*git, "fetch", "-q", "--depth", "1", "origin", commit], check=True)
        subprocess.run([*git, "checkout", "-q", "FETCH_HEAD"], check=True)
    head = subprocess.run(
        ["git", "-C", str(dest), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    if head != commit:
        raise RuntimeError(f"{dest} is at {head}, expected {commit}")
    return dest


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--instance", default="pallets__flask-5014")
    ap.add_argument("-n", type=int, default=10)
    ap.add_argument("--record-fixture", action="store_true", help="save round-0 text for tests")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    load_dotenv(ROOT / ".env")

    from datasets import load_dataset

    row = next(
        r
        for r in load_dataset("SWE-bench/SWE-bench_Verified", split="test")
        if r["instance_id"] == args.instance
    )
    repo_dir = checkout(row["repo"], row["base_commit"], ROOT / ".cache" / "repos" / args.instance)

    llm = LLM()
    mutants = propose_mutants(
        row["patch"], args.n, repo_dir=repo_dir, issue_text=row["problem_statement"], llm=llm
    )

    if args.record_fixture:
        first = json.loads((llm.config.cache_dir / f"{_round0_key(llm)}.json").read_text())
        (FIXTURE / f"{args.instance}_live_round0.txt").write_text(first["content"])

    generated = sum(c.generated_cost_usd for c in llm.calls)
    rounds = [e for e in llm.events if e["purpose"] == "mutants"]
    r0 = rounds[0]
    L = [
        f"# Live mutant run: `{args.instance}` ({datetime.now(UTC).date()})",
        "",
        f"Produced by `scripts/generate_demo.py`. Model `{llm.config.model}` at "
        f"`{llm.config.base_url}`, thinking off.",
        "",
        "## Result",
        "",
        f"- Asked for {args.n} mutants of the gold patch; returned **{len(mutants)}**.",
        f"- First round: {r0['parsed']} parsed. **{r0['strict_clean']} applied cleanly** with "
        f"plain `git apply --check`; {r0['applied'] - r0['strict_clean']} more needed "
        f"`--recount` (wrong hunk line counts); {r0['repaired']} more were re-anchored "
        "(blank-line or indentation slips in context lines); "
        f"{r0['parsed'] - r0['applied'] - r0['repaired']} could not be applied. "
        f"{r0['accepted']} passed every check.",
        f"- Re-ask rounds used: {len(rounds) - 1} of 2.",
        f"- Cost of this run when generated: **${generated:.5f}** "
        f"over {len(llm.calls)} call(s) (${llm.total_usd:.5f} spent on this render), "
        f"{sum(c.tokens_in for c in llm.calls)} tokens in and "
        f"{sum(c.tokens_out for c in llm.calls)} tokens out"
        + (" (all served from cache on this render)" if all(c.cached for c in llm.calls) else "")
        + ".",
        "",
        "| Round | asked | parsed | clean | --recount | re-anchored | accepted (cumulative) "
        "| rejected |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for e in rounds:
        L.append(
            f"| {e['round']} | {e['asked']} | {e['parsed']} | {e['strict_clean']} | "
            f"{e['applied'] - e['strict_clean']} | {e['repaired']} | {e['accepted']} | "
            f"{len(e['rejected'])} |"
        )
    rej = [(e["round"], r) for e in rounds for r in e["rejected"]]
    if rej:
        L += ["", "### Rejections", ""]
        L += [f"- round {rnd}, mutant {r['mutant']} ({r['kind']}): {r['reason']}" for rnd, r in rej]
    L += ["", "## Mutants", ""]
    for i, (diff, why) in enumerate(mutants, 1):
        L += [f"### {i}. {why}", "", "```diff", diff.rstrip("\n"), "```", ""]
    L += [
        "## Calls",
        "",
        "| purpose | cached | in | out | USD | running total |",
        "|---|---|---:|---:|---:|---:|",
    ]
    L += [
        f"| {c.purpose} | {c.cached} | {c.tokens_in} | {c.tokens_out} | ${c.cost_usd:.6f} | "
        f"${c.total_usd:.6f} |"
        for c in llm.calls
    ]
    L += ["", "## The mutant prompt", "", "```text", MUTANT_PROMPT.rstrip("\n"), "```", ""]
    OUT_MD.write_text("\n".join(L))
    print(f"{len(mutants)} mutants; ${generated:.5f} generated, ${llm.total_usd:.5f} spent now")
    return 0


def _round0_key(llm: LLM) -> str:
    first = next(c for c in llm.calls if c.purpose == "mutants[0]")
    return next(p.stem for p in llm.config.cache_dir.glob(f"{first.cache_key}*.json"))


if __name__ == "__main__":
    sys.exit(main())
