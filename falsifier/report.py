"""Verdict plus surviving mutants; JSON and one small HTML view.

The HTML page is what gets filmed: dark text on white, large type, no horizontal scrolling at
1920x1080. Each surviving mutant's diff and rationale sit side by side with the test that failed to
catch it, under the witness check that proves the mutant differs from the patch.
"""

from __future__ import annotations

import html
import json
from pathlib import Path

from falsifier.evidence import (
    CAUGHT_BY_P2P,
    EQUIVALENT,
    KILLED,
    MUTANT_ERROR,
    NOT_RUN,
    SURVIVED,
    MutantResult,
    Verdict,
    canary_live,
    classify_test_run,
    pytest_summary,
)
from falsifier.instance import Instance
from falsifier.verify import describe_witness

CSS = """
:root { --ink:#111; --muted:#444; --line:#c9c9c9; --bg:#fff; --soft:#f3f3f1;
        --red:#a3141b; --green:#0b6b2f; --amber:#7a4b00; }
* { box-sizing: border-box; }
html { font-size: 22px; }
body { margin: 0; background: var(--bg); color: var(--ink);
       font: 1rem/1.45 system-ui, -apple-system, "Segoe UI", sans-serif; overflow-x: hidden; }
main { max-width: 1840px; margin: 0 auto; padding: 1.4rem 2rem 3rem; }
h1 { font-size: 1.9rem; margin: 0 0 .3rem; }
h2 { font-size: 1.4rem; margin: 2rem 0 .6rem; border-bottom: 2px solid var(--line); }
h3 { font-size: 1.15rem; margin: 1rem 0 .4rem; }
p, li { max-width: 80ch; }
.muted { color: var(--muted); }
.verdict { display: inline-block; font-size: 2.6rem; font-weight: 800; letter-spacing: .02em;
           padding: .15rem .9rem; border: 4px solid currentColor; border-radius: .4rem; margin: .4rem 0; }
.EARNED { color: var(--green); } .UNEARNED, .BROKEN, .UNFIXED, .REGRESSED { color: var(--red); }
.UNPINNED { color: var(--amber); } .caught-by-p2p { color: var(--amber); }
.INCONCLUSIVE { color: var(--amber); }
.reason { font-size: 1.05rem; max-width: 110ch; }
pre { white-space: pre-wrap; overflow-wrap: anywhere; word-break: break-word; margin: 0;
      font: .8rem/1.4 ui-monospace, "SFMono-Regular", Menlo, Consolas, monospace;
      background: var(--soft); border: 1px solid var(--line); border-radius: .3rem; padding: .6rem .7rem; }
.line { display: block; } .add { background: #d9f2df; } .del { background: #f8dcdc; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(17rem, 1fr)); gap: .7rem; }
.card { border: 2px solid var(--line); border-radius: .4rem; padding: .6rem .8rem; min-width: 0; }
.card b { font-size: 1.05rem; }
.status { font-weight: 800; text-transform: uppercase; letter-spacing: .03em; }
.killed { color: var(--green); } .survived { color: var(--red); } .equivalent, .not-run { color: var(--muted); }
.error { color: var(--amber); }
.pair { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 1rem; }
.box { border: 2px solid var(--line); border-radius: .4rem; padding: .7rem .9rem; min-width: 0; }
.witness { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: .8rem; margin-top: .6rem; }
table { border-collapse: collapse; width: 100%; table-layout: fixed; font-size: .85rem; }
td, th { border-bottom: 1px solid var(--line); padding: .3rem .4rem; text-align: left;
         vertical-align: top; overflow-wrap: anywhere; }
th { color: var(--muted); font-weight: 600; }
details { margin: .4rem 0; } summary { cursor: pointer; color: var(--muted); }
.ok { color: var(--green); font-weight: 700; } .bad { color: var(--red); font-weight: 700; }
@media (max-width: 1100px) { .pair, .witness { grid-template-columns: minmax(0, 1fr); } }
"""

STATUS_TEXT = {
    KILLED: "killed",
    SURVIVED: "survived FAIL_TO_PASS and PASS_TO_PASS",
    CAUGHT_BY_P2P: "survived FAIL_TO_PASS, caught by PASS_TO_PASS",
    EQUIVALENT: "equivalent, discarded",
    MUTANT_ERROR: "did not run cleanly",
    NOT_RUN: "not run",
}


def e(s: object) -> str:
    return html.escape(str(s), quote=True)


def diff_html(diff: str) -> str:
    """One block per line, joined without newlines (a block plus a newline doubles the gap)."""
    rows = []
    for ln in diff.splitlines():
        cls = "line"
        if ln.startswith("+") and not ln.startswith("+++"):
            cls = "line add"
        elif ln.startswith("-") and not ln.startswith("---"):
            cls = "line del"
        rows.append(f'<span class="{cls}">{e(ln) or "&nbsp;"}</span>')
    return "<pre>" + "".join(rows) + "</pre>"


def run_line(rec: dict | None) -> str:
    if not rec:
        return '<span class="muted">not run</span>'
    outcome, why = classify_test_run(rec)
    cost = rec.get("cost_usd")
    return (
        f"<b>{e(outcome)}</b>: {e(why)} · {rec.get('cpu_s') or 0:.3f} CPU-s · "
        f"{(rec.get('run_wall_s') or 0):.2f} s · ${(cost if cost is not None else 0):.5f}"
    )


def fork_table(records: list[dict]) -> str:
    rows = "".join(
        f"<tr><td>{e(r['label'])}<br><span class='muted'>@{e(r.get('image_in'))}</span></td>"
        f"<td>{e(r.get('exit_code'))}{' (timed out)' if r.get('timed_out') else ''}</td>"
        f"<td>{e(pytest_summary(r.get('stdout', '')) or (r.get('error') or ''))}</td>"
        f"<td>{(r.get('cpu_s') or 0):.3f}</td><td>{(r.get('run_wall_s') or 0):.2f}</td>"
        f"<td>${(r.get('cost_usd') or 0):.5f}</td><td>{e(r.get('timeout_s'))} s</td></tr>"
        for r in records
    )
    return (
        "<table><colgroup><col style='width:34%'><col style='width:6%'><col style='width:26%'>"
        "<col style='width:8%'><col style='width:8%'><col style='width:9%'><col style='width:9%'>"
        "</colgroup><tr><th>branch</th><th>exit</th><th>pytest</th><th>CPU-s</th><th>wall s</th>"
        f"<th>cost</th><th>timeout</th></tr>{rows}</table>"
    )


def log_details(rec: dict | None, title: str) -> str:
    if not rec:
        return ""
    cmd = rec.get("command", "")
    return (
        f"<details><summary>{e(title)}: command and captured output "
        f"(truncate_output_at={e(rec.get('truncate_output_at'))} bytes)</summary>"
        f"<pre>$ {e(cmd)}</pre><pre>{e(rec.get('stdout', '')[-6000:])}</pre>"
        f"<pre>{e(rec.get('stderr', '')[-3000:])}</pre></details>"
    )


def p2p_line(m: MutantResult) -> str:
    if not m.p2p:
        return "not run"
    head = f"exit {e(m.p2p.get('exit_code'))} · {e(pytest_summary(m.p2p.get('stdout', '')) or '')}"
    if not m.p2p_missing:
        return head + " · every PASS_TO_PASS test PASSED: the mutant clears the full criterion"
    return head + e(f" · {len(m.p2p_missing)} not PASSED, e.g. {', '.join(m.p2p_missing[:3])}")


def survivor_html(m: MutantResult, test_src: str) -> str:
    a, b = m.witness_results
    wp, wm = m.witness_patched or {}, m.witness_mutant or {}
    return f"""
<section class="box" style="margin-top:1rem">
  <h3>Mutant {e(m.id)} · {e(STATUS_TEXT[m.status])} · {e(m.kind)}</h3>
  <div class="pair">
    <div><p><b>Rationale.</b> {e(m.rationale)}</p>{diff_html(m.diff)}</div>
    <div><p><b>The test that did not catch it</b> · {run_line(m.test)}</p><pre>{e(test_src)}</pre></div>
  </div>
  <p style="margin-top:.8rem"><b>Witness check.</b> The mutant counts only because it provably
  differs from the patch on its own witness:</p>
  <pre>{e(m.witness)}</pre>
  <div class="witness">
    <div class="box"><b>Patch</b>: {e(describe_witness(a))}<br>
      <span class="muted">exit {e(wp.get("exit_code"))} · {e(wp.get("label"))}</span></div>
    <div class="box"><b>Mutant</b>: {e(describe_witness(b))}<br>
      <span class="muted">exit {e(wm.get("exit_code"))} · {e(wm.get("label"))}</span></div>
  </div>
  <p style="margin-top:.8rem"><b>PASS_TO_PASS on the mutant</b>: {p2p_line(m)}</p>
  {log_details(m.test, "mutant + test")}{log_details(m.witness_patched, "witness on the patch")}
  {log_details(m.witness_mutant, "witness on the mutant")}{log_details(m.p2p, "PASS_TO_PASS on the mutant")}
</section>"""


def issue_html(issue: str, limit: int = 200) -> str:
    """The first 200 characters only, so the verdict stays above the fold at 1080p."""
    flat = " ".join(issue.split())
    if len(flat) <= limit:
        return f'<p class="muted">{e(flat)}</p>'
    return (
        f'<p class="muted">{e(flat[:limit].rsplit(" ", 1)[0])} …</p>'
        f"<details><summary>Full issue</summary><pre>{e(issue)}</pre></details>"
    )


def canary_line(v: Verdict) -> str:
    rec = v.forks.get("canary")
    live, why = canary_live(rec)
    mark = (
        '<span class="ok">live</span>'
        if live
        else '<span class="bad">NOT LIVE: mutant results void</span>'
    )
    exit_code = rec.get("exit_code") if rec else "n/a"
    return f"Negative control (canary): exit {e(exit_code)} · {mark} · {e(why)}"


def official_line(official: dict | None) -> str:
    if not official:
        return ""
    n = len(official["fail_to_pass"])
    return (
        f"<p>SWE-bench says <b>{e(official['label'])}</b> · benchmark oracle: the repository's "
        f"own FAIL_TO_PASS tests ({n})</p>"
    )


def page(v: Verdict, inst: Instance, official: dict | None = None) -> str:
    test_src = "\n".join(inst.test.values())
    expected = (
        f"<p>Expected <b>{e(v.expected_verdict)}</b> · "
        + (
            '<span class="ok">agrees</span>'
            if v.expected_verdict == v.verdict
            else '<span class="bad">DISAGREES</span>'
        )
        + "</p>"
        if v.expected_verdict
        else ""
    )
    cards = "".join(
        f'<div class="card"><b>{e(m.id)}</b> · {e(m.kind)}<br>'
        f'<span class="status {e(m.status)}">{e(STATUS_TEXT[m.status])}</span>'
        + (
            f' <span class="muted">(expected {e(m.expected_status)})</span>'
            if m.expected_status and m.expected_status != m.status
            else ""
        )
        + f'<br><span class="muted">{e(m.rationale)}</span></div>'
        for m in v.mutants
    )
    survivors = "".join(
        survivor_html(m, test_src) for m in v.mutants if m.status in (SURVIVED, CAUGHT_BY_P2P)
    )
    others = "".join(
        f"<details><summary>{e(m.id)} · {e(STATUS_TEXT[m.status])}: {e(m.note or m.test_why)}</summary>"
        f"<p>{e(m.rationale)}</p>{diff_html(m.diff)}<pre>{e(m.witness)}</pre>"
        f"{log_details(m.test, 'mutant + test')}{log_details(m.witness_patched, 'witness on the patch')}"
        f"{log_details(m.witness_mutant, 'witness on the mutant')}</details>"
        for m in v.mutants
        if m.status not in (SURVIVED, CAUGHT_BY_P2P, NOT_RUN)
    )
    records = v.all_records()
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Falsifier · {e(v.instance_id)}</title><style>{CSS}</style></head><body><main>
<h1>{e(v.instance_id)}</h1>
{issue_html(inst.issue)}
{f'<p class="muted">Input domain: {e(inst.domain)}</p>' if inst.domain else ""}
<div class="verdict {e(v.verdict)}">{e(v.verdict)}</div>
{expected}
{official_line(official)}
<p><b>{canary_line(v)}</b></p>
<p class="reason">{e(v.reason)}</p>
<p class="muted">Configuration {e(v.configuration)} · checkpoint {e(v.checkpoint)} ·
{len(records)} forks · {v.cpu_s:.2f} CPU-s · ${v.cost_usd:.4f} · {e(v.created)}</p>
<h2>Mutant grid</h2><div class="grid">{cards}</div>
{("<h2>Survivors</h2>" + survivors) if survivors else ""}
<h2>Baseline forks</h2>
<p>original + test: {run_line(v.forks.get("original+test"))}<br>
patched + test: {run_line(v.forks.get("patched+test"))}<br>
patched + PASS_TO_PASS: {run_line(v.forks.get("patched+p2p")) if v.forks.get("patched+p2p") else '<span class="muted">not run</span>'}<br>
canary + test: {run_line(v.forks.get("canary"))}</p>
{("<details><summary>The canary mutant</summary>" + diff_html(inst.canary.diff) + "</details>") if inst.canary else ""}
<div class="pair"><div><h3>The patch</h3>{diff_html(inst.gold_diff)}</div>
<div><h3>The test</h3><pre>{e(test_src)}</pre></div></div>
{"".join(log_details(r, k) for k, r in v.forks.items())}
{("<h2>Other mutants</h2>" + others) if others else ""}
<h2>Every fork</h2>{fork_table(records)}
</main></body></html>"""


def write(
    v: Verdict, inst: Instance, out_dir: Path, official: dict | None = None
) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    j, h = out_dir / f"{v.instance_id}.json", out_dir / f"{v.instance_id}.html"
    data = v.to_dict() | ({"official": official} if official else {})
    j.write_text(json.dumps(data, indent=2, default=str) + "\n")
    h.write_text(page(v, inst, official))
    return j, h


def index(verdicts: list[Verdict], out_dir: Path, title: str, extra: str = "") -> Path:
    rows = "".join(
        f"<tr><td><a href='{e(v.instance_id)}.html'>{e(v.instance_id)}</a></td>"
        f"<td>{e(v.expected_verdict or '')}</td><td class='{e(v.verdict)}'><b>{e(v.verdict)}</b></td>"
        f"<td>{'<span class=ok>agrees</span>' if v.expected_verdict == v.verdict else '<span class=bad>DISAGREES</span>' if v.expected_verdict else ''}</td>"
        f"<td>{len(v.all_records())}</td><td>{v.cpu_s:.2f}</td><td>${v.cost_usd:.4f}</td></tr>"
        for v in verdicts
    )
    total = sum(v.cost_usd for v in verdicts)
    path = out_dir / "index.html"
    path.write_text(f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>{e(title)}</title>
<style>{CSS}</style></head><body><main><h1>{e(title)}</h1>{extra}
<table><colgroup><col style="width:30%"><col style="width:14%"><col style="width:16%">
<col style="width:12%"><col style="width:8%"><col style="width:9%"><col style="width:11%"></colgroup>
<tr><th>instance</th><th>expected</th><th>verdict</th><th></th><th>forks</th><th>CPU-s</th><th>cost</th></tr>
{rows}</table><p class="muted">Total ${total:.4f} across {len(verdicts)} instances.</p>
</main></body></html>""")
    return path


SCOPE = (
    "Scope: five SWE-bench Verified instances across three repositories (pallets/flask, "
    "psf/requests, pytest-dev/pytest). Configuration A: mutants of the gold patch, held to "
    "SWE-bench's full resolution criterion (FAIL_TO_PASS passes and PASS_TO_PASS does not "
    "regress). No claim is made about the rest of the benchmark."
)


def comparison_rows(verdicts: list[Verdict], officials: dict[str, dict]) -> list[dict]:
    rows = []
    for v in verdicts:
        o = officials[v.instance_id]
        killed = sum(m.status == KILLED for m in v.mutants)
        both = sum(m.status == SURVIVED for m in v.mutants)
        caught = sum(m.status == CAUGHT_BY_P2P for m in v.mutants)
        rows.append(
            {
                "instance": v.instance_id,
                "oracle": f"FAIL_TO_PASS, {len(o['fail_to_pass'])} test(s)",
                "swebench": o["label"],
                "falsifier": v.verdict,
                "killed": killed,
                "distinguishable": killed + both + caught,
                "survived_f2p": both + caught,
                "survived_both": both,
                "equivalent": sum(m.status == EQUIVALENT for m in v.mutants),
                "canary_exit": (v.forks.get("canary") or {}).get("exit_code"),
                "cost_usd": v.cost_usd,
            }
        )
    return rows


def comparison(
    verdicts: list[Verdict],
    officials: dict[str, dict],
    out_dir: Path,
    missing: dict[str, str] | None = None,
) -> Path:
    rows = comparison_rows(verdicts, officials)
    body = "".join(
        f"<tr><td><a href='{e(r['instance'])}.html'>{e(r['instance'])}</a></td>"
        f"<td>{e(r['oracle'])}</td><td>{e(r['swebench'])}</td>"
        f"<td class='{e(r['falsifier'])}'><b>{e(r['falsifier'])}</b></td>"
        f"<td>{r['distinguishable']}</td><td>{r['equivalent']}</td>"
        f"<td>{r['survived_f2p']}</td><td><b>{r['survived_both']}</b></td>"
        f"<td>{e(r['canary_exit'])}</td><td>${r['cost_usd']:.4f}</td></tr>"
        for r in rows
    ) + "".join(
        f"<tr><td>{e(iid)}</td><td colspan='9' class='muted'>not completed: {e(why)}</td></tr>"
        for iid, why in (missing or {}).items()
    )
    path = out_dir / "index.html"
    path.write_text(f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Falsifier results</title>
<style>{CSS}</style></head><body><main><h1>Falsifier: benchmark oracle against execution</h1>
<p><b>{e(SCOPE)}</b></p>
<table><colgroup><col style="width:18%"><col style="width:13%"><col style="width:9%">
<col style="width:11%"><col style="width:10%"><col style="width:9%"><col style="width:9%">
<col style="width:9%"><col style="width:6%"><col style="width:6%"></colgroup>
<tr><th>instance</th><th>benchmark oracle</th><th>SWE-bench says</th><th>Falsifier says</th>
<th>distinguishable mutants</th><th>equivalent discarded</th><th>survived FAIL_TO_PASS</th>
<th>survived both lists</th><th>canary exit</th><th>cost</th></tr>
{body}</table>
<p class="muted">"Benchmark oracle" means the repository's own FAIL_TO_PASS tests, not a reproduction
of SWE-bench's harness. Each instance links to its full evidence: every fork's branch id, command,
exit code, captured output, CPU-seconds and cost.</p></main></body></html>""")
    return path
