"""The benchmark's own verdict, for comparison. Thin by decision (BUILD_PLAN §6, 2026-10-25).

This reports the dataset's published label and its FAIL_TO_PASS / PASS_TO_PASS lists. It does
NOT reproduce SWE-bench's harness resolution logic, and it runs nothing.

Under Configuration A the patch under audit is the gold patch. SWE-bench Verified publishes no
per-patch label field, but the gold patch is RESOLVED by construction: FAIL_TO_PASS is defined
as the tests that fail before it and pass after it, and PASS_TO_PASS as the tests that pass both
before and after. That construction is the published label. "Benchmark oracle" in this
project means the repository's own FAIL_TO_PASS tests, never a reproduction of the harness.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass

DATASET = "SWE-bench/SWE-bench_Verified"
GOLD_LABEL = "RESOLVED"
GOLD_BASIS = (
    "gold patch of SWE-bench Verified: FAIL_TO_PASS and PASS_TO_PASS were derived from it, so it "
    "resolves the instance by construction (dataset label, not a harness reproduction)"
)


@dataclass(frozen=True)
class Official:
    instance_id: str
    dataset: str
    label: str
    basis: str
    fail_to_pass: list[str]
    pass_to_pass: list[str]
    repo: str
    version: str
    image: str

    def to_dict(self) -> dict:
        return asdict(self)


def _as_list(v) -> list[str]:
    return json.loads(v) if isinstance(v, str) else list(v)


def official(row: dict) -> Official:
    """The published verdict for an instance's gold patch, straight from the dataset row."""
    return Official(
        instance_id=row["instance_id"],
        dataset=DATASET,
        label=GOLD_LABEL,
        basis=GOLD_BASIS,
        fail_to_pass=_as_list(row["FAIL_TO_PASS"]),
        pass_to_pass=_as_list(row["PASS_TO_PASS"]),
        repo=row["repo"],
        version=row["version"],
        image=row["image"],
    )


def load_rows(instance_ids: list[str]) -> dict[str, dict]:
    from datasets import load_dataset

    wanted = set(instance_ids)
    rows = {
        r["instance_id"]: dict(r)
        for r in load_dataset(DATASET, split="test")
        if r["instance_id"] in wanted
    }
    if missing := wanted - set(rows):
        raise KeyError(f"not in {DATASET}: {sorted(missing)}")
    return rows
