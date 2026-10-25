"""Spend and timeout limits for sandbox runs. Every value here is a safety rail.

Rates come from the step 1 probe (docs/probe.md, 2026-10-25): the SDK's `cost` field is USD and
fits cost = USD_PER_RUN + USD_PER_CPU_SECOND * cpu_seconds, with idle wall time free.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

USD_PER_CPU_SECOND = 0.010326
USD_PER_RUN = 4.2e-05


@dataclass(frozen=True)
class SpendLimits:
    ceiling_usd: float
    """Hard ceiling on SDK-reported spend for one guard. No run launches that could cross it."""
    max_timeout_s: int = 600
    """Largest per-run timeout accepted. The SDK default (1000 s) is never used."""
    cores: int = 4
    """vCPUs per sandbox (nproc = 4, no cgroup cap, measured 2026-10-25)."""
    pin_one_cpu: bool = True
    """Wrap every command in `taskset -c 0`, so CPU-seconds cannot exceed wall-seconds and the
    worst case is timeout * rate rather than timeout * cores * rate."""

    @property
    def billable_cores(self) -> int:
        return 1 if self.pin_one_cpu else self.cores

    def __post_init__(self) -> None:
        if self.ceiling_usd <= 0:
            raise ValueError("ceiling_usd must be positive")
        if self.cores < 1:
            raise ValueError("cores must be >= 1")

    @classmethod
    def from_env(cls, default_ceiling_usd: float) -> SpendLimits:
        """FALSIFIER_SPEND_CEILING_USD overrides the default ceiling."""
        return cls(
            ceiling_usd=float(os.environ.get("FALSIFIER_SPEND_CEILING_USD", default_ceiling_usd))
        )
