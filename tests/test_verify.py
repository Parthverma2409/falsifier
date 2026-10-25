"""verify.py against its fixtures, run locally: same commands, real pytest, no sandbox, no spend.

The sandbox run is scripts/run_fixtures.py (and test_fixtures_in_sandboxes below, opt-in). This
local run checks the verdict logic itself. A failure here is a disagreement to report; the
fixtures' expected verdicts are never edited to make it pass.
"""

import asyncio
import os
import resource
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest

from falsifier.config import USD_PER_CPU_SECOND, USD_PER_RUN
from falsifier.evidence import (
    BROKEN,
    EARNED,
    INCONCLUSIVE,
    EvidenceError,
    MutantResult,
    RunRecord,
    Verdict,
    classify_test_run,
    passed_ids,
    pytest_counts,
)
from falsifier.instance import load_fixtures
from falsifier.verify import RUNNER_PATH, verify

FIXTURES = {f.id: f for f in load_fixtures()}


class LocalForker:
    """Runs a fork's command in a fresh temp copy of the fixture's original tree plus overlay."""

    def __init__(self, inst, root: Path):
        self.inst, self.root = inst, root
        self.calls: list[str] = []

    async def __call__(self, branch, overlay, command, timeout_s):
        self.calls.append(branch)
        work = self.root / branch.replace("/", "_")
        shutil.copytree(self.root / "_original", work)
        scratch = work / "_falsifier"
        scratch.mkdir()
        for path, text in overlay.items():
            dest = scratch / Path(path).name if path.startswith("/") else work / path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(text)
        local = (
            command.replace(f"{self.inst.env} && ", "")
            .replace(f"cd {self.inst.workdir}", f"cd {work}")
            .replace(str(Path(RUNNER_PATH).parent), str(scratch))
            .replace("python ", f"{sys.executable} ", 1)
        )
        before = resource.getrusage(resource.RUSAGE_CHILDREN)
        t = time.monotonic()
        p = subprocess.run(
            local,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        after = resource.getrusage(resource.RUSAGE_CHILDREN)
        cpu = (after.ru_utime - before.ru_utime) + (after.ru_stime - before.ru_stime)
        return RunRecord(
            label=f"{self.inst.id}/{branch}",
            command=command,
            image_in="local",
            timeout_s=timeout_s,
            disposable=True,
            cost_usd=USD_PER_RUN + USD_PER_CPU_SECOND * cpu,
            cost_upper_bound_usd=USD_PER_RUN + USD_PER_CPU_SECOND * timeout_s,
            started_at=datetime.now(UTC).isoformat(),
            exit_code=p.returncode,
            timed_out=False,
            stdout=p.stdout,
            stderr=p.stderr,
            cpu_s=cpu,
            run_wall_s=time.monotonic() - t,
            truncate_output_at=1 << 20,
        )


def run_local(inst, tmp_path):
    (tmp_path / "_original").mkdir()
    for path, text in inst.original.items():
        dest = tmp_path / "_original" / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text)
    fork = LocalForker(inst, tmp_path)
    return asyncio.run(verify(inst, fork)), fork


@pytest.mark.parametrize("fixture_id", sorted(FIXTURES))
def test_fixture_verdict_locally(fixture_id, tmp_path):
    inst = FIXTURES[fixture_id]
    verdict, fork = run_local(inst, tmp_path)
    statuses = {m.id: m.status for m in verdict.mutants}
    expected = {m.id: m.expected_status for m in inst.mutants}
    assert (verdict.verdict, statuses) == (inst.expected_verdict, expected), verdict.reason
    if verdict.verdict == BROKEN:
        assert not any(c.startswith("mutant-") for c in fork.calls)


def test_regression_suite_runs_in_exactly_one_fork(tmp_path):
    verdict, fork = run_local(FIXTURES["earned_last_n"], tmp_path)
    assert verdict.verdict == EARNED
    assert [c for c in fork.calls if "p2p" in c] == ["patched+p2p"]
    assert all(m.test["command"].count("test_existing") == 0 for m in verdict.mutants)


# --- evidence rules, no runs ------------------------------------------------------------------


def _rec(label, exit_code=0, stdout="==== 1 passed in 0.01s ====", **kw):
    base = dict(
        label=label,
        command="pytest",
        image_in="img",
        timeout_s=10,
        disposable=True,
        cost_usd=0.001,
        cost_upper_bound_usd=0.1,
        started_at="t",
        exit_code=exit_code,
        stdout=stdout,
        stderr="",
        cpu_s=0.1,
        run_wall_s=0.2,
        truncate_output_at=1 << 20,
    )
    return RunRecord(**(base | kw)).to_dict()


FAILED = "==== 1 failed in 0.01s ===="


def _canary():
    return _rec("c", 1, "E   AssertionError: canary\n" + FAILED)


def test_verdict_refuses_missing_evidence():
    forks = {
        "original+test": _rec("o", 1, FAILED),
        "patched+test": _rec("p", cost_usd=None),
        "canary": _canary(),
    }
    with pytest.raises(EvidenceError, match="lacks"):
        Verdict("x", "UNFIXED", "r", forks, [], "img")


def test_verdict_refuses_unsupported_claims():
    broken = {"original+test": _rec("o", 1, FAILED), "canary": _canary()}
    with pytest.raises(EvidenceError):
        Verdict("x", BROKEN, "r", broken, [], "img")
    forks = {
        "original+test": _rec("o", 1, FAILED),
        "patched+test": _rec("p"),
        "patched+p2p": _rec("r"),
        "canary": _canary(),
    }
    lone = MutantResult("m1", "k", "r", "w", "d", "survived", test=_rec("m"))
    with pytest.raises(EvidenceError, match="not distinguished"):
        Verdict("x", "UNEARNED", "r", forks, [lone], "img")


def test_inconclusive_needs_at_least_one_run():
    with pytest.raises(EvidenceError):
        Verdict("x", INCONCLUSIVE, "r", {}, [], "img")


@pytest.mark.parametrize(
    ("code", "stdout", "timed_out", "expected"),
    [
        (0, "== 2 passed in 0.1s ==", False, "PASS"),
        (1, "== 1 failed, 1 passed in 0.1s ==", False, "FAIL"),
        (2, "== 1 error in 0.1s ==", False, "FAIL"),
        (4, "ERROR: not found", False, "ERROR"),
        (5, "== no tests ran in 0.01s ==", False, "ERROR"),
        (0, "== no tests ran in 0.01s ==", False, "ERROR"),
        (-9, "", True, "FAIL"),
    ],
)
def test_classify_test_run(code, stdout, timed_out, expected):
    assert classify_test_run(_rec("t", code, stdout, timed_out=timed_out))[0] == expected


def test_pytest_counts_and_passed_ids():
    out = "PASSED tests/a.py::t1\nPASSED tests/a.py::t2[x y]\n== 1 failed, 2 passed in 0.3s =="
    assert pytest_counts(out) == {"failed": 1, "passed": 2}
    assert passed_ids(out) == {"tests/a.py::t1", "tests/a.py::t2[x"}


@pytest.mark.skipif(
    not os.environ.get("FALSIFIER_SANDBOX_TESTS"),
    reason="spends real money: set FALSIFIER_SANDBOX_TESTS=1 to run the fixtures in sandboxes",
)
def test_fixtures_in_sandboxes():
    """BUILD_PLAN step 7 acceptance, in real sandboxes (about $0.1-0.3 per run)."""
    root = Path(__file__).resolve().parent.parent
    p = subprocess.run([sys.executable, str(root / "scripts" / "run_fixtures.py")], cwd=root)
    assert p.returncode == 0, "fixture disagreements; see reports/fixtures/index.html"


def test_every_paid_fork_is_in_the_evidence(tmp_path):
    verdict, fork = run_local(FIXTURES["broken_clamp"], tmp_path)
    assert verdict.verdict == BROKEN
    assert sorted(r["label"].split("/", 1)[1] for r in verdict.forks.values()) == sorted(fork.calls)


def test_verdict_needs_a_live_negative_control():
    forks = {"original+test": _rec("o", 0), "canary": _rec("c", 0)}  # canary PASSED
    with pytest.raises(EvidenceError, match="negative control"):
        Verdict("x", BROKEN, "r", forks, [], "img")


class DropCanaryForker(LocalForker):
    """Simulates a mispathed patch: the canary's overlay never reaches the code under test."""

    async def __call__(self, branch, overlay, command, timeout_s):
        if branch == "canary+test":
            overlay = {p: t for p, t in overlay.items() if p not in self.inst.canary.overlay}
            overlay.update(self.inst.patched)
        return await super().__call__(branch, overlay, command, timeout_s)


@pytest.mark.parametrize("fixture_id", ["unearned_parse_port", "earned_last_n"])
def test_dead_overlays_void_the_instance(fixture_id, tmp_path):
    """If the canary passes, every mutant result would be void: no verdict, no mutant forks."""
    inst = FIXTURES[fixture_id]
    (tmp_path / "_original").mkdir()
    for path, text in inst.original.items():
        dest = tmp_path / "_original" / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text)
    fork = DropCanaryForker(inst, tmp_path)
    verdict = asyncio.run(verify(inst, fork))
    assert verdict.verdict == INCONCLUSIVE and "negative control" in verdict.reason
    assert not any(c.startswith("mutant-") for c in fork.calls)
    assert verdict.counts["canary_exit"] == 0


def test_every_fixture_has_a_canary():
    assert all(f.canary is not None for f in FIXTURES.values())


def test_requests_style_path_parameters_are_normalized_like_the_dataset():
    out = (
        "PASSED tests/test_utils.py::T::t[/testbed/tests/test_utils.py]\n"
        "PASSED tests/test_utils.py::T::t[//double]\nPASSED tests/test_utils.py::T::t[*.py]\n"
    )
    assert passed_ids(out, normalize_options=True) == {
        "tests/test_utils.py::T::t[/test_utils.py]",
        "tests/test_utils.py::T::t[//double]",
        "tests/test_utils.py::T::t[*.py]",
    }
    assert "tests/test_utils.py::T::t[/testbed/tests/test_utils.py]" in passed_ids(out)


def test_unpinned_and_unearned_need_their_pass_to_pass_evidence():
    forks = {
        "original+test": _rec("o", 1, FAILED),
        "patched+test": _rec("p"),
        "patched+p2p": _rec("r"),
        "canary": _canary(),
    }
    w_patch = _rec("wp", stdout='FALSIFIER_WITNESS {"outcome": "value", "repr": "1"}')
    w_mut = _rec("wm", stdout='FALSIFIER_WITNESS {"outcome": "value", "repr": "2"}')

    def mutant(status, p2p_missing):
        return MutantResult(
            "m1",
            "k",
            "r",
            "w",
            "d",
            status,
            test=_rec("m"),
            witness_patched=w_patch,
            witness_mutant=w_mut,
            p2p=_rec("mp", 1 if p2p_missing else 0),
            p2p_missing=p2p_missing,
        )

    Verdict("x", "UNEARNED", "r", forks, [mutant("survived", [])], "img")
    Verdict("x", "UNPINNED", "r", forks, [mutant("caught-by-p2p", ["t::a"])], "img")
    with pytest.raises(EvidenceError, match="contradicts"):
        Verdict("x", "UNEARNED", "r", forks, [mutant("survived", ["t::a"])], "img")
    with pytest.raises(EvidenceError, match="UNEARNED needs"):
        Verdict("x", "UNEARNED", "r", forks, [mutant("caught-by-p2p", ["t::a"])], "img")
    no_p2p = mutant("survived", [])
    no_p2p.p2p = None
    with pytest.raises(EvidenceError, match="PASS_TO_PASS"):
        Verdict("x", "UNEARNED", "r", forks, [no_p2p], "img")


def test_pytest4_summary_with_seconds_is_recognised():
    old = "========================== 1 passed in 0.12 seconds ==========================="
    assert pytest_counts(old) == {"passed": 1}
    rec = _rec("t", 0, old)
    assert classify_test_run(rec)[0] == "PASS"
