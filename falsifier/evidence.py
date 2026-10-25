"""Every claim carries branch id, exit code, captured log, and what it cost.

A Verdict cannot be constructed without its evidence: __post_init__ checks that every fork it
cites is complete (branch id, command, exit code, stdout and stderr captured with an explicit
truncate_output_at, duration, CPU-seconds, cost) and that the forks actually support the verdict.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime


@dataclass
class RunRecord:
    """One sandbox run, as executed. Built only by falsifier.sandbox.guarded_run."""

    label: str
    """The branch id: `<instance>/<branch>`. With image_in it names the fork exactly."""
    command: str
    image_in: str | None
    """Image uuid or tag the run started from (the checkpoint it forked)."""
    timeout_s: int
    disposable: bool
    cost_usd: float | None
    """SDK-reported cost in USD. None only when the run failed before reporting one."""
    cost_upper_bound_usd: float
    """Worst case reserved against the spend ceiling: timeout * cores * rate + per-run fee."""
    started_at: str
    client_wall_s: float = 0.0
    exit_code: int | None = None
    timed_out: bool | None = None
    stdout: str = ""
    stderr: str = ""
    output_truncated: bool = False
    cpu_s: float | None = None
    """user + sys CPU seconds; the SDK's `.elapsed` reports this, not wall time."""
    run_wall_s: float | None = None
    """Real duration of the process inside the sandbox (resources.monotonic_time)."""
    result_image: str | None = None
    """Checkpoint uuid when disposable=False, else None."""
    error: str | None = None
    resources: dict = field(default_factory=dict)
    truncate_output_at: int | None = None
    """Byte limit passed explicitly to the SDK for stdout and stderr (its default is 64 KiB)."""

    @property
    def cost_for_accounting(self) -> float:
        """Reported cost, or the reserved worst case when no cost was reported."""
        return self.cost_usd if self.cost_usd is not None else self.cost_upper_bound_usd

    @property
    def branch_id(self) -> str:
        return f"{self.label}@{self.image_in}"

    def to_dict(self) -> dict:
        return asdict(self) | {"branch_id": self.branch_id}


# ---------------------------------------------------------------------------------------------
# Reading pytest and witness output. Classification only; no judgement about the code.

PASS, FAIL, ERROR = "PASS", "FAIL", "ERROR"
_SUMMARY = re.compile(r"^=+ (.*\bin [\d.]+s.*?) =+\s*$", re.M)
_COUNT = re.compile(
    r"(\d+) (passed|failed|errors?|skipped|xfailed|xpassed|deselected|warnings?|no tests ran)"
)


def pytest_summary(stdout: str) -> str | None:
    found = _SUMMARY.findall(stdout or "")
    return found[-1] if found else None


def pytest_counts(stdout: str) -> dict[str, int]:
    summary = pytest_summary(stdout) or ""
    counts: dict[str, int] = {}
    for n, kind in _COUNT.findall(summary):
        kind = {"error": "errors", "warning": "warnings"}.get(kind, kind)
        counts[kind] = counts.get(kind, 0) + int(n)
    return counts


_OPTION = re.compile(r"(.*?)\[(.*)\]")


def _normalize_option(test_id: str) -> str:
    """SWE-bench's parse_log_pytest_options (used for psf/requests) reduces an absolute-path
    parameter to its basename: `t[/testbed/tests/test_utils.py]` -> `t[/test_utils.py]`. The
    dataset's PASS_TO_PASS ids were produced that way, so ours must be too (requests-6028)."""
    m = _OPTION.search(test_id)
    if not m:
        return test_id
    main, option = m.groups()
    if option.startswith("/") and not option.startswith("//") and "*" not in option:
        option = "/" + option.split("/")[-1]
    return f"{main}[{option}]"


def passed_ids(stdout: str, normalize_options: bool = False) -> set[str]:
    """Ids reported PASSED in a `pytest -rA` short summary, truncated at the first space as
    SWE-bench's log parser truncates them, so they compare directly with PASS_TO_PASS. With
    normalize_options, path parameters are reduced as parse_log_pytest_options does."""
    ids = {ln.split(" ", 2)[1] for ln in (stdout or "").splitlines() if ln.startswith("PASSED ")}
    return {_normalize_option(i) for i in ids} if normalize_options else ids


def classify_test_run(rec: RunRecord | dict) -> tuple[str, str]:
    """PASS, FAIL or ERROR for a run of targeted tests, with the reason.

    PASS needs exit 0 and at least one passed test with none failed. Exit 1 (tests failed) and
    exit 2 (collection error or interrupted, e.g. the test imports a name the code lacks) are
    FAIL: the test did not pass. A timeout is FAIL. Exits 3, 4 and 5 (internal error, usage error,
    nothing collected) and platform errors are ERROR: the run says nothing about the code."""
    r = rec if isinstance(rec, dict) else rec.to_dict()
    if r.get("error") or r.get("exit_code") is None:
        return ERROR, f"no result: {r.get('error') or 'no exit code'}"
    if r.get("timed_out"):
        return FAIL, f"timed out after {r['timeout_s']} s"
    code, counts = r["exit_code"], pytest_counts(r.get("stdout", ""))
    summary = pytest_summary(r.get("stdout", "")) or "no pytest summary"
    if code == 0:
        if counts.get("passed", 0) >= 1 and not counts.get("failed") and not counts.get("errors"):
            return PASS, f"exit 0, {summary}"
        return ERROR, f"exit 0 but {summary}"
    if code in (1, 2):
        return FAIL, f"exit {code}, {summary}"
    return ERROR, f"exit {code}, {summary}"


CANARY_MARKER = "AssertionError: canary"


def canary_live(rec: RunRecord | dict | None) -> tuple[bool, str]:
    """Did the negative control prove that overlays reach the code under test? The targeted test
    must not pass, and either it failed normally (exit 1 or 2) or the log shows the canary's own
    AssertionError (e.g. the canary broke a pytest hook and pytest exited 3 with INTERNALERROR).
    A pass, a platform error, or a crash without the canary's trace proves nothing."""
    if rec is None:
        return False, "no canary could be built"
    r = rec if isinstance(rec, dict) else rec.to_dict()
    outcome, why = classify_test_run(r)
    marker = CANARY_MARKER in (r.get("stdout") or "") + (r.get("stderr") or "")
    if outcome == PASS:
        return False, f"the canary PASSED the test ({why}): overlays are not live"
    if outcome == FAIL or marker:
        trace = "the canary's AssertionError is in the log" if marker else "no canary trace"
        return True, f"the canary failed the test ({why}; {trace})"
    return False, f"the canary run did not fail cleanly ({why}) and shows no canary trace"


WITNESS_TAG = "FALSIFIER_WITNESS "


def witness_result(rec: RunRecord | dict | None) -> dict | None:
    """The witness runner's JSON line, or None if the run produced none."""
    if rec is None:
        return None
    r = rec if isinstance(rec, dict) else rec.to_dict()
    for ln in reversed((r.get("stdout") or "").splitlines()):
        if ln.startswith(WITNESS_TAG):
            try:
                return json.loads(ln[len(WITNESS_TAG) :])
            except json.JSONDecodeError:
                return None
    return None


# ---------------------------------------------------------------------------------------------
# Verdicts

EARNED, BROKEN, UNFIXED, REGRESSED, UNEARNED, UNPINNED = (
    "EARNED",
    "BROKEN",
    "UNFIXED",
    "REGRESSED",
    "UNEARNED",
    "UNPINNED",
)
"""UNEARNED: a distinguishable mutant clears SWE-bench's full resolution criterion, FAIL_TO_PASS
and PASS_TO_PASS. UNPINNED: a distinguishable mutant passes FAIL_TO_PASS but PASS_TO_PASS catches
it; the designated test does not pin the bug, and the suite catches the mutant incidentally."""
INCONCLUSIVE = "INCONCLUSIVE"
"""Not a verdict: a run failed to produce the evidence a verdict needs."""
VERDICTS = (EARNED, BROKEN, UNFIXED, REGRESSED, UNEARNED, UNPINNED, INCONCLUSIVE)

KILLED, SURVIVED, CAUGHT_BY_P2P, EQUIVALENT, MUTANT_ERROR, NOT_RUN = (
    "killed",
    "survived",
    "caught-by-p2p",
    "equivalent",
    "error",
    "not-run",
)
"""killed: FAIL_TO_PASS fails on the mutant. survived: distinguishable, and passes FAIL_TO_PASS
and PASS_TO_PASS. caught-by-p2p: distinguishable, passes FAIL_TO_PASS, fails PASS_TO_PASS.
equivalent: passes FAIL_TO_PASS but its own witness cannot tell it from the patch."""

REQUIRED_FIELDS = (
    "label",
    "image_in",
    "command",
    "exit_code",
    "stdout",
    "stderr",
    "truncate_output_at",
    "run_wall_s",
    "cpu_s",
    "cost_usd",
)


class EvidenceError(ValueError):
    """A verdict was about to be returned without the evidence that supports it."""


def missing_evidence(rec: dict) -> list[str]:
    return [k for k in REQUIRED_FIELDS if rec.get(k) is None]


@dataclass
class MutantResult:
    id: str
    kind: str
    rationale: str
    witness: str
    diff: str
    status: str
    expected_status: str | None = None
    test: dict | None = None
    test_why: str = ""
    witness_patched: dict | None = None
    witness_mutant: dict | None = None
    p2p: dict | None = None
    """PASS_TO_PASS on the mutant: run for every distinguishable survivor of FAIL_TO_PASS."""
    p2p_missing: list[str] | None = None
    note: str = ""

    @property
    def witness_results(self) -> tuple[dict | None, dict | None]:
        return witness_result(self.witness_patched), witness_result(self.witness_mutant)


@dataclass
class Verdict:
    instance_id: str
    verdict: str
    reason: str
    forks: dict[str, dict]
    """Baseline forks by name: original+test, patched+test, patched+p2p."""
    mutants: list[MutantResult]
    checkpoint: str
    configuration: str = "A: mutate the gold patch, audit the benchmark's FAIL_TO_PASS tests"
    counts: dict = field(default_factory=dict)
    expected_verdict: str | None = None
    created: str = field(default_factory=lambda: datetime.now(UTC).isoformat(timespec="seconds"))

    def __post_init__(self) -> None:
        if self.verdict not in VERDICTS:
            raise EvidenceError(f"unknown verdict {self.verdict!r}")
        records = self.all_records()
        if not records:
            raise EvidenceError(f"{self.verdict} without a single run behind it")
        if self.verdict == INCONCLUSIVE:
            return
        live, why = canary_live(self.forks.get("canary"))
        if not live:
            raise EvidenceError(f"{self.verdict} without a live negative control: {why}")
        for rec in records:
            if gaps := missing_evidence(rec):
                raise EvidenceError(f"{self.verdict}: {rec.get('label')} lacks {gaps}")
        self._check_support()

    def all_records(self) -> list[dict]:
        out = list(self.forks.values())
        for m in self.mutants:
            out += [r for r in (m.test, m.witness_patched, m.witness_mutant, m.p2p) if r]
        return out

    def _need(self, name: str, outcome: str | None = None) -> dict:
        rec = self.forks.get(name)
        if rec is None:
            raise EvidenceError(f"{self.verdict} needs the {name} fork")
        if outcome and classify_test_run(rec)[0] != outcome:
            raise EvidenceError(f"{self.verdict} needs {name} to be {outcome}")
        return rec

    def _check_support(self) -> None:
        if self.verdict == BROKEN:
            self._need("original+test", PASS)
            if any(m.test for m in self.mutants):
                raise EvidenceError("BROKEN must not spend forks on mutants")
            return
        self._need("original+test", FAIL)
        if self.verdict == UNFIXED:
            self._need("patched+test", FAIL)
            return
        self._need("patched+test", PASS)
        self._need("patched+p2p")
        if self.verdict == REGRESSED:
            return
        survivors = [m for m in self.mutants if m.status == SURVIVED]
        caught = [m for m in self.mutants if m.status == CAUGHT_BY_P2P]
        for m in survivors + caught:
            if m.test is None or classify_test_run(m.test)[0] != PASS:
                raise EvidenceError(f"survivor {m.id} has no passing test run")
            a, b = m.witness_results
            if a is None or b is None or a == b:
                raise EvidenceError(f"survivor {m.id} is not distinguished by its witness")
            if m.p2p is None or m.p2p.get("exit_code") not in (0, 1) or m.p2p_missing is None:
                raise EvidenceError(f"survivor {m.id} has no completed PASS_TO_PASS run")
            if (m.status == SURVIVED) == bool(m.p2p_missing):
                raise EvidenceError(f"survivor {m.id}: status contradicts its PASS_TO_PASS run")
        if self.verdict == UNEARNED and not survivors:
            raise EvidenceError("UNEARNED needs a survivor of FAIL_TO_PASS and PASS_TO_PASS")
        if self.verdict == UNPINNED and (survivors or not caught):
            raise EvidenceError("UNPINNED needs a survivor caught only by PASS_TO_PASS")
        if self.verdict == EARNED:
            if survivors or caught:
                raise EvidenceError("EARNED with a distinguished survivor")
            if not any(m.status == KILLED for m in self.mutants):
                raise EvidenceError("EARNED needs at least one killed mutant")
            if any(m.status == MUTANT_ERROR for m in self.mutants):
                raise EvidenceError("EARNED with mutants that did not run cleanly")

    @property
    def cost_usd(self) -> float:
        return sum(
            r.get("cost_usd") or r.get("cost_upper_bound_usd") or 0 for r in self.all_records()
        )

    @property
    def cpu_s(self) -> float:
        return sum(r.get("cpu_s") or 0 for r in self.all_records())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["cost_usd"], d["cpu_s"] = self.cost_usd, self.cpu_s
        return d
