"""Every claim carries branch id, exit code, captured log, and what it cost."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class RunRecord:
    """One sandbox run, as executed. Built only by falsifier.sandbox.guarded_run."""

    label: str
    command: str
    image_in: str | None
    """Image uuid or tag the run started from (the branch it forked)."""
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

    @property
    def cost_for_accounting(self) -> float:
        """Reported cost, or the reserved worst case when no cost was reported."""
        return self.cost_usd if self.cost_usd is not None else self.cost_upper_bound_usd

    def to_dict(self) -> dict:
        return asdict(self)
