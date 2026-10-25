"""Configuration: the generation endpoint and model, and the sandbox spend rails.

Sandbox rates come from the step 1 probe (docs/probe.md, 2026-10-25): the SDK's `cost` field is
USD and fits cost = USD_PER_RUN + USD_PER_CPU_SECOND * cpu_seconds, with idle wall time free.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

USD_PER_CPU_SECOND = 0.010326
USD_PER_RUN = 4.2e-05


@dataclass(frozen=True)
class GenerationConfig:
    """Token Factory endpoint and model for generate.py. The base_url is from the Token Factory
    quickstart (docs/plan_deviations.md, step 0); prices are from GET /v1/models?verbose=true
    (docs/models.md), in USD per million tokens."""

    base_url: str = "https://api.tokenfactory.nebius.com/v1/"
    model: str = "nvidia/Nemotron-3_5-Lightning"
    usd_per_m_input: float = 0.06
    usd_per_m_output: float = 0.24
    cache_dir: Path = field(default_factory=lambda: ROOT / ".cache" / "generate")
    api_key_env: str = "NEBIUS_API_KEY"
    request_timeout_s: float = 120.0
    """Per-request timeout. The openai SDK default is 600 s, which hung a smoke run."""
    max_retries: int = 2

    @classmethod
    def from_env(cls) -> GenerationConfig:
        """FALSIFIER_BASE_URL, FALSIFIER_MODEL, FALSIFIER_USD_PER_M_INPUT/OUTPUT and
        FALSIFIER_GENERATE_CACHE override the defaults."""
        d = cls()
        env = os.environ.get
        return cls(
            base_url=env("FALSIFIER_BASE_URL", d.base_url),
            model=env("FALSIFIER_MODEL", d.model),
            usd_per_m_input=float(env("FALSIFIER_USD_PER_M_INPUT", d.usd_per_m_input)),
            usd_per_m_output=float(env("FALSIFIER_USD_PER_M_OUTPUT", d.usd_per_m_output)),
            cache_dir=Path(env("FALSIFIER_GENERATE_CACHE", d.cache_dir)),
        )

    def cost_usd(self, tokens_in: int, tokens_out: int) -> float:
        return (tokens_in * self.usd_per_m_input + tokens_out * self.usd_per_m_output) / 1e6


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
