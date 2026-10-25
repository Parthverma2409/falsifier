"""The five verdicts, by forking and executing.

Configuration A: mutate the GOLD patch and audit the benchmark's own FAIL_TO_PASS tests. From one
warm checkpoint (the original code):

  original + test       expect FAIL, else BROKEN
  patched + test        expect PASS, else UNFIXED
  patched + P2P         expect every PASS_TO_PASS id PASSED, else REGRESSED   (the only P2P fork)
  each mutant + test    expect FAIL                                           (targeted test only)

The three baseline forks run in parallel. BROKEN, UNFIXED and REGRESSED short-circuit: no mutant
forks are spent. Mutant forks are disposable and run in parallel; idle time is free and cost is
CPU-seconds, so parallelism costs nothing.

UNEARNED is conjunctive: the test passed on a mutant AND that mutant provably differs from the
patch on the witness its rationale names. The witness runs in a fork of the patch and a fork of
the mutant; only a different result counts. A survivor its own witness cannot distinguish is an
equivalent mutant: it is discarded, counted separately and never reported as UNEARNED.

Every decision here is read off exit codes and logs. No model is consulted.
"""

from __future__ import annotations

import asyncio
import shlex
from collections.abc import Awaitable, Callable

from falsifier.evidence import (
    BROKEN,
    EARNED,
    EQUIVALENT,
    ERROR,
    FAIL,
    INCONCLUSIVE,
    KILLED,
    MUTANT_ERROR,
    NOT_RUN,
    PASS,
    REGRESSED,
    SURVIVED,
    UNEARNED,
    UNFIXED,
    WITNESS_TAG,
    MutantResult,
    RunRecord,
    Verdict,
    canary_live,
    classify_test_run,
    passed_ids,
    pytest_summary,
)
from falsifier.instance import Instance

Fork = Callable[[str, dict[str, str], str, int], Awaitable[RunRecord]]
"""fork(branch, overlay, command, timeout_s) -> RunRecord; see sandbox.SandboxForker."""

RUNNER_PATH = "/tmp/falsifier/witness_runner.py"
SNIPPET_PATH = "/tmp/falsifier/witness.py"
WITNESS_RUNNER = f'''\
"""Run a witness: execute it, evaluate its final expression if it has one, and report the value
or the exception plus everything it printed, as one JSON line."""
import ast, contextlib, io, json, re, sys

def norm(s):
    return re.sub(r"0x[0-9a-fA-F]+", "0x?", s)  # object addresses differ run to run

sys.path.insert(0, ".")
src = open(sys.argv[1]).read()
printed = io.StringIO()
try:
    tree = ast.parse(src)
    last = tree.body.pop() if tree.body and isinstance(tree.body[-1], ast.Expr) else None
    scope = {{"__name__": "__witness__"}}
    with contextlib.redirect_stdout(printed):
        exec(compile(tree, "<witness>", "exec"), scope)
        value = None
        if last:
            value = eval(compile(ast.Expression(last.value), "<witness>", "eval"), scope)
    out = {{"outcome": "value", "repr": norm(repr(value))}}
except BaseException as e:
    out = {{"outcome": "raised", "type": type(e).__name__, "message": norm(str(e))}}
out["stdout"] = norm(printed.getvalue())
print({WITNESS_TAG!r} + json.dumps(out, sort_keys=True))
'''


def pytest_command(inst: Instance, args: list[str]) -> str:
    quoted = " ".join(shlex.quote(a) for a in args)
    return f"{inst.env} && cd {inst.workdir} && python -m pytest -rA -p no:cacheprovider {quoted}"


def witness_command(inst: Instance) -> str:
    # PYTHONHASHSEED pins set and dict-of-str ordering, the one nondeterminism that could make a
    # witness differ between two identical programs and so fake an UNEARNED.
    return (
        f"{inst.env} && export PYTHONHASHSEED=0 && cd {inst.workdir} && "
        f"python {RUNNER_PATH} {SNIPPET_PATH}"
    )


def describe_witness(result: dict | None) -> str:
    if result is None:
        return "no witness output"
    if result["outcome"] == "value":
        text = f"returns {result['repr']}"
    else:
        text = f"raises {result['type']}({result['message']!r})"
    if result.get("stdout"):
        text += f", prints {result['stdout'].strip()[:300]!r}"
    return text


async def verify(inst: Instance, fork: Fork) -> Verdict:
    t = inst.timeouts
    patched_and_test = {**inst.patched, **inst.test}
    test_cmd = pytest_command(inst, inst.f2p)

    jobs = [
        fork("original+test", dict(inst.test), test_cmd, t.test),
        fork("patched+test", patched_and_test, test_cmd, t.test),
        fork("patched+p2p", patched_and_test, pytest_command(inst, inst.p2p_files), t.regression),
    ]
    if inst.canary is not None:  # the negative control, through the same path as any mutant
        canary_overlay = {**inst.patched, **inst.canary.overlay, **inst.test}
        jobs.append(fork("canary+test", canary_overlay, test_cmd, t.test))
    orig_r, pat_r, reg_r, *canary_r = await asyncio.gather(*jobs)
    # Every fork that was paid for is evidence, including the P2P fork on a short-circuited verdict.
    forks = {
        "original+test": orig_r.to_dict(),
        "patched+test": pat_r.to_dict(),
        "patched+p2p": reg_r.to_dict(),
    }
    if canary_r:
        forks["canary"] = canary_r[0].to_dict()
    live, canary_why = canary_live(forks.get("canary"))
    orig, orig_why = classify_test_run(orig_r)
    pat, pat_why = classify_test_run(pat_r)
    not_run = [_mutant(m, NOT_RUN) for m in inst.mutants]

    def done(verdict: str, reason: str, mutants: list[MutantResult], **counts) -> Verdict:
        if verdict != INCONCLUSIVE:
            reason += f". Negative control: {canary_why}"
        counts["canary_exit"] = forks.get("canary", {}).get("exit_code")
        return Verdict(
            instance_id=inst.id,
            verdict=verdict,
            reason=reason,
            forks=forks,
            mutants=mutants,
            checkpoint=str(orig_r.image_in),
            counts=counts,
            expected_verdict=inst.expected_verdict,
        )

    if not live:
        return done(
            INCONCLUSIVE,
            f"negative control failed: {canary_why}. Every mutant result for this instance would "
            "be void, so none is reported",
            not_run,
        )
    if orig == ERROR:
        return done(INCONCLUSIVE, f"original + test did not run cleanly: {orig_why}", not_run)
    if orig == PASS:
        return done(
            BROKEN,
            f"the test passed on the original code ({orig_why}), so it never reproduced the bug; "
            "no mutant forks were spent",
            not_run,
        )
    if pat == ERROR:
        return done(INCONCLUSIVE, f"patched + test did not run cleanly: {pat_why}", not_run)
    if pat == FAIL:
        return done(
            UNFIXED,
            f"the test fails on the patch ({pat_why}); on the original: {orig_why}",
            not_run,
        )

    if reg_r.error or reg_r.exit_code not in (0, 1):
        return done(
            INCONCLUSIVE,
            f"PASS_TO_PASS run did not complete: exit {reg_r.exit_code} {reg_r.error or ''}",
            not_run,
        )
    seen = passed_ids(reg_r.stdout, normalize_options=inst.log_parser == "parse_log_requests")
    missing = [i for i in inst.p2p if i not in seen]
    if missing:
        return done(
            REGRESSED,
            f"{len(missing)} of {len(inst.p2p)} PASS_TO_PASS tests not PASSED on the patch "
            f"(exit {reg_r.exit_code}, {pytest_summary(reg_r.stdout)}): {', '.join(missing[:5])}",
            not_run,
            p2p_missing=len(missing),
        )

    results = await _run_mutants(inst, fork, test_cmd)
    survivors = [m for m in results if m.status == SURVIVED]
    n = {s: sum(m.status == s for m in results) for s in (KILLED, SURVIVED, EQUIVALENT)}
    n["error"] = sum(m.status == MUTANT_ERROR for m in results)
    base = (
        f"the test fails on the original ({orig_why}) and passes on the patch ({pat_why}); "
        f"all {len(inst.p2p)} PASS_TO_PASS tests PASSED"
    )
    if survivors:
        cites = "; ".join(_survivor_cite(m) for m in survivors)
        return done(UNEARNED, f"{base}. Surviving mutants: {cites}", results, **n)
    if n["error"]:
        return done(
            INCONCLUSIVE,
            f"{base}, but {n['error']} mutant fork(s) did not run cleanly",
            results,
            **n,
        )
    if not n[KILLED]:
        return done(
            INCONCLUSIVE,
            f"{base}, but no mutant could be distinguished from the patch "
            f"({n[EQUIVALENT]} equivalent discarded)",
            results,
            **n,
        )
    return done(
        EARNED,
        f"{base}; the test killed {n[KILLED]} of {n[KILLED]} distinguishable mutants"
        f" ({n[EQUIVALENT]} equivalent discarded)",
        results,
        **n,
    )


def _mutant(m, status: str, **kw) -> MutantResult:
    return MutantResult(
        id=m.id,
        kind=m.kind,
        rationale=m.rationale,
        witness=m.witness,
        diff=m.diff,
        status=status,
        expected_status=m.expected_status,
        **kw,
    )


def _survivor_cite(m: MutantResult) -> str:
    a, b = m.witness_results
    return (
        f"{m.id} ({m.kind}) passes the test (exit {m.test['exit_code']}) and differs on its "
        f"witness: the patch {describe_witness(a)} (exit {m.witness_patched['exit_code']}), "
        f"the mutant {describe_witness(b)} (exit {m.witness_mutant['exit_code']})"
    )


async def _run_mutants(inst: Instance, fork: Fork, test_cmd: str) -> list[MutantResult]:
    t = inst.timeouts
    runs = await asyncio.gather(
        *(
            fork(
                f"mutant-{m.id}+test", {**inst.patched, **m.overlay, **inst.test}, test_cmd, t.test
            )
            for m in inst.mutants
        )
    )
    results: list[MutantResult] = []
    jobs = []
    for m, r in zip(inst.mutants, runs, strict=True):
        outcome, why = classify_test_run(r)
        status = {FAIL: KILLED, ERROR: MUTANT_ERROR}.get(outcome, SURVIVED)
        results.append(_mutant(m, status, test=r.to_dict(), test_why=why))
        if outcome == PASS:
            files = {RUNNER_PATH: WITNESS_RUNNER, SNIPPET_PATH: m.witness}
            cmd = witness_command(inst)
            jobs.append(
                (
                    results[-1],
                    fork(f"witness-patched-{m.id}", {**inst.patched, **files}, cmd, t.witness),
                    fork(
                        f"witness-mutant-{m.id}",
                        {**inst.patched, **m.overlay, **files},
                        cmd,
                        t.witness,
                    ),
                )
            )
    pairs = await asyncio.gather(*(asyncio.gather(a, b) for _, a, b in jobs))
    for (res, _, _), (wp, wm) in zip(jobs, pairs, strict=True):
        res.witness_patched, res.witness_mutant = wp.to_dict(), wm.to_dict()
        a, b = res.witness_results
        if a is not None and b is not None and a != b:
            res.status = SURVIVED
            res.note = f"witness: the patch {describe_witness(a)}, the mutant {describe_witness(b)}"
        else:
            res.status = EQUIVALENT
            res.note = (
                f"its own witness does not distinguish it (the patch {describe_witness(a)}, "
                f"the mutant {describe_witness(b)}); discarded, never UNEARNED"
            )
    return results
