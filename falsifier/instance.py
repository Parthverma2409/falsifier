"""Load a bench instance, build the repo, take the warm checkpoint.

An Instance is everything verify.py needs, as file overlays relative to the work directory:
`patched` holds the full contents of the files the gold patch changes, `test` the test under
audit, and each mutant's `overlay` the files it changes on top of the patch. Overlays are uploaded
into a fork of the warm checkpoint, so no fork has to run `git apply`.
"""

from __future__ import annotations

import hashlib
import json
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from falsifier.config import FIXTURE_TIMEOUTS, ROOT, Timeouts
from falsifier.generate import make_diff
from falsifier.sandbox import SpendGuard, Uploader, guarded_run

FIXTURES_DIR = ROOT / "falsifier" / "fixtures"
CHECKPOINTS = ROOT / "runs" / "checkpoints.json"
"""Persisted images cannot be deleted, so warm checkpoints are reused by content hash."""

FIXTURE_BASE_IMAGE = "python:3.12-slim"
FIXTURE_SETUP = (
    "pip install --no-cache-dir --quiet --disable-pip-version-check pytest==8.3.5"
    " && python -m pytest --version"
)
FIXTURE_ENV = "export HOME=/root"
FIXTURE_WORKDIR = "/work"


@dataclass
class Mutant:
    id: str
    kind: str
    rationale: str
    witness: str
    overlay: dict[str, str]
    """Full contents, after the mutant, of the files it changes."""
    diff: str
    """Against the patched tree, written by git."""
    expected_status: str | None = None


@dataclass
class Instance:
    id: str
    workdir: str
    env: str
    """Shell prefix for every command, e.g. `export HOME=/root`."""
    issue: str
    f2p: list[str]
    p2p: list[str]
    p2p_files: list[str]
    patched: dict[str, str]
    test: dict[str, str]
    gold_diff: str
    test_diff: str
    mutants: list[Mutant]
    timeouts: Timeouts = field(default_factory=Timeouts)
    original: dict[str, str] = field(default_factory=dict)
    """The original tree, for fixtures whose checkpoint is built from local files."""
    expected_verdict: str | None = None
    fixture_class: str | None = None
    domain: str | None = None
    """The inputs the code under audit accepts. Equivalence is only sound within it."""


def _read_tree(root: Path) -> dict[str, str]:
    return {str(p.relative_to(root)): p.read_text() for p in sorted(root.rglob("*")) if p.is_file()}


def load_fixture(d: Path) -> Instance:
    spec = tomllib.loads((d / "fixture.toml").read_text())
    original, patched, test = (_read_tree(d / sub) for sub in ("original", "patched", "test"))
    mutants = []
    for m in spec["mutants"]:
        base = patched[m["file"]]
        if base.count(m["old"]) != 1:
            raise ValueError(f"{spec['id']}/{m['id']}: `old` must occur exactly once")
        after = {m["file"]: base.replace(m["old"], m["new"])}
        mutants.append(
            Mutant(
                id=m["id"],
                kind=m["kind"],
                rationale=m["rationale"],
                witness=m["witness"],
                overlay=after,
                diff=make_diff({m["file"]: base}, after),
                expected_status=m.get("expected_status"),
            )
        )
    return Instance(
        id=spec["id"],
        workdir=FIXTURE_WORKDIR,
        env=FIXTURE_ENV,
        issue=spec["issue"],
        f2p=spec["f2p"],
        p2p=spec["p2p"],
        p2p_files=spec["p2p_files"],
        patched=patched,
        test=test,
        gold_diff=make_diff({p: original[p] for p in patched}, patched),
        test_diff=make_diff({p: original.get(p, "") for p in test}, test),
        mutants=mutants,
        timeouts=FIXTURE_TIMEOUTS,
        original=original,
        expected_verdict=spec["expected_verdict"],
        fixture_class=spec["class"],
        domain=spec.get("domain"),
    )


def load_fixtures(root: Path = FIXTURES_DIR) -> list[Instance]:
    return [load_fixture(d) for d in sorted(root.iterdir()) if (d / "fixture.toml").exists()]


# ---------------------------------------------------------------------------------------------
# Checkpoints


def _digest(*parts: object) -> str:
    return hashlib.sha256(json.dumps(parts, sort_keys=True).encode()).hexdigest()[:24]


def _known() -> dict:
    return json.loads(CHECKPOINTS.read_text()) if CHECKPOINTS.exists() else {}


def _remember(key: str, value: dict) -> None:
    known = _known() | {key: value}
    CHECKPOINTS.parent.mkdir(parents=True, exist_ok=True)
    CHECKPOINTS.write_text(json.dumps(known, indent=2) + "\n")


async def _checkpoint(client, guard, key, label, image, shell, timeout_s, files=None):
    """Run `shell` once with disposable=False and remember the resulting image by `key`.
    Returns (checkpoint image, build record dict or None when reused)."""
    if (hit := _known().get(key)) is not None:
        return await client.images.use(hit["uuid"], strict=True), None
    rec = await guarded_run(
        guard, image, label=label, shell=shell, timeout_s=timeout_s, disposable=False, files=files
    )
    if rec.exit_code != 0 or not rec.result_image:
        raise RuntimeError(f"{label} failed: exit {rec.exit_code} {rec.error or rec.stderr[-500:]}")
    _remember(key, {"uuid": rec.result_image, "label": label, "record": rec.to_dict()})
    return await client.images.use(rec.result_image, strict=True), rec.to_dict()


async def build_fixture_base(client, guard: SpendGuard, timeouts: Timeouts = FIXTURE_TIMEOUTS):
    base = await client.images.oci(FIXTURE_BASE_IMAGE)
    key = "fixture-base:" + _digest(FIXTURE_BASE_IMAGE, FIXTURE_SETUP)
    return await _checkpoint(
        client,
        guard,
        key,
        "fixtures/base-build",
        base,
        f"{FIXTURE_ENV} && {FIXTURE_SETUP}",
        timeouts.build,
    )


async def build_fixture(client, guard: SpendGuard, upload: Uploader, base, inst: Instance):
    """Warm checkpoint for one fixture: the base image plus its original tree at /work."""
    key = f"fixture:{inst.id}:" + _digest(str(base.uuid), inst.original)
    files = {f"{inst.workdir}/{p}": await upload(text) for p, text in inst.original.items()}
    return await _checkpoint(
        client,
        guard,
        key,
        f"{inst.id}/build",
        base,
        f"{inst.env} && ls -R {inst.workdir}",
        inst.timeouts.files,
        files=files,
    )
