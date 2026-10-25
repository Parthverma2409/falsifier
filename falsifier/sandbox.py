"""Nebius client: create, checkpoint, fork, exec, collect.

So far this holds only the guarded run that every sandbox command must go through:

- an explicit timeout on every run, never the SDK default of 1000 s;
- every command pinned to one CPU (`taskset -c 0`), so a runaway costs at most timeout * rate;
- a spend ceiling checked before each launch: a run is reserved at its worst-case cost
  (timeout * cores * rate), waits while in-flight reservations leave no room, and aborts the
  whole run with SpendCeilingExceeded once completed spend leaves no room at all;
- a cost on every RunRecord.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import shlex
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

from falsifier.config import USD_PER_CPU_SECOND, USD_PER_RUN, SpendLimits
from falsifier.evidence import RunRecord

DEFAULT_TRUNCATE_OUTPUT_AT = 1 << 20  # the SDK default is 64 KiB, too small for pytest logs


class SpendCeilingExceeded(RuntimeError):
    """Raised before launch when a run's worst-case cost no longer fits under the ceiling."""


class SpendGuard:
    def __init__(self, limits: SpendLimits, ledger: Path | None = None):
        """With a ledger, spend is global: the guard starts from every cost already recorded there
        and appends each run it settles, so the ceiling holds across processes."""
        self.limits = limits
        self.ledger = ledger
        self.prior_usd = self._ledger_total() if ledger else 0.0
        self.spent_usd = self.prior_usd
        self.reserved_usd = 0.0
        self.records: list[RunRecord] = []
        self._cond = asyncio.Condition()

    def _ledger_total(self) -> float:
        if not self.ledger or not self.ledger.exists():
            return 0.0
        return sum(
            json.loads(ln)["charged_usd"] for ln in self.ledger.read_text().splitlines() if ln
        )

    def worst_case_usd(self, timeout_s: int) -> float:
        return USD_PER_RUN + USD_PER_CPU_SECOND * timeout_s * self.limits.billable_cores

    def check_timeout(self, timeout_s: int) -> None:
        if not isinstance(timeout_s, int) or isinstance(timeout_s, bool):
            raise TypeError(f"timeout_s must be an int number of seconds, got {timeout_s!r}")
        if not 0 < timeout_s <= self.limits.max_timeout_s:
            raise ValueError(f"timeout_s={timeout_s} outside (0, {self.limits.max_timeout_s}]")

    def _no_room(self, label: str, worst: float) -> SpendCeilingExceeded:
        return SpendCeilingExceeded(
            f"refusing to launch {label!r}: spent ${self.spent_usd:.4f} + worst case "
            f"${worst:.4f} exceeds ceiling ${self.limits.ceiling_usd:.4f}"
        )

    async def reserve(self, label: str, timeout_s: int) -> float:
        self.check_timeout(timeout_s)
        worst = self.worst_case_usd(timeout_s)
        ceiling = self.limits.ceiling_usd
        async with self._cond:
            while self.spent_usd + self.reserved_usd + worst > ceiling:
                if self.spent_usd + worst > ceiling:
                    raise self._no_room(label, worst)
                await self._cond.wait()
            self.reserved_usd += worst
        return worst

    async def settle(self, worst: float, record: RunRecord) -> None:
        async with self._cond:
            self.reserved_usd -= worst
            self.spent_usd += record.cost_for_accounting
            self.records.append(record)
            if self.ledger:
                self.ledger.parent.mkdir(parents=True, exist_ok=True)
                with self.ledger.open("a") as f:
                    f.write(
                        json.dumps(
                            {
                                "at": record.started_at,
                                "label": record.label,
                                "cost_usd": record.cost_usd,
                                "charged_usd": record.cost_for_accounting,
                            }
                        )
                        + "\n"
                    )
            self._cond.notify_all()

    def require_room(self, label: str, usd: float) -> None:
        """Raise before spending `usd` outside a sandbox run (model calls) if it cannot fit."""
        if self.spent_usd + self.reserved_usd + usd > self.limits.ceiling_usd:
            raise self._no_room(label, usd)

    async def charge(self, label: str, usd: float) -> None:
        """Record spend made outside a sandbox run (model calls) against the same ceiling."""
        async with self._cond:
            self.spent_usd += usd
            if self.ledger:
                self.ledger.parent.mkdir(parents=True, exist_ok=True)
                with self.ledger.open("a") as f:
                    f.write(
                        json.dumps(
                            {
                                "at": datetime.now(UTC).isoformat(timespec="seconds"),
                                "label": label,
                                "cost_usd": usd,
                                "charged_usd": usd,
                            }
                        )
                        + "\n"
                    )
            self._cond.notify_all()

    def summary(self) -> dict:
        return {
            "ceiling_usd": self.limits.ceiling_usd,
            "billable_cores": self.limits.billable_cores,
            "pinned_to_one_cpu": self.limits.pin_one_cpu,
            "spent_usd": self.spent_usd,
            "spent_this_process_usd": self.spent_usd - self.prior_usd,
            "runs": len(self.records),
            "unreported_cost_runs": sum(1 for r in self.records if r.cost_usd is None),
        }


def pin(limits: SpendLimits, shell: str) -> str:
    """The command as executed: pinned to CPU 0 when the limits say so. POSIX sh, not bash."""
    return f"taskset -c 0 sh -c {shlex.quote(shell)}" if limits.pin_one_cpu else shell


def _fill_from_result(rec: RunRecord, done) -> None:
    """Copy outputs, exit state and resources off an executed contree-sdk image."""
    rec.exit_code = done.exit_code
    rec.stdout = str(done.stdout or "")
    rec.stderr = str(done.stderr or "")
    rec.cost_usd = done.result.cost
    rec.output_truncated = done.result.truncated
    rec.result_image = str(done.uuid) if done.uuid else None
    raw = done.result._raw.result if done.result._raw else None
    if raw is not None:
        res = raw.resources
        rec.cpu_s = res.user_cpu_time + res.system_cpu_time
        rec.run_wall_s = res.monotonic_time
        rec.timed_out = raw.state.timed_out
        rec.resources = {k: getattr(res, k) for k in vars(res)}


async def guarded_run(
    guard: SpendGuard,
    image,
    *,
    label: str,
    shell: str,
    timeout_s: int,
    disposable: bool = True,
    files: dict | None = None,
    truncate_output_at: int = DEFAULT_TRUNCATE_OUTPUT_AT,
) -> RunRecord:
    """Run one shell command in a fork of `image` under the guard. Never raises for a failed
    run (the error lands on the record); raises SpendCeilingExceeded before launching."""
    worst = await guard.reserve(label, timeout_s)
    executed = pin(guard.limits, shell)
    rec = RunRecord(
        label=label,
        command=executed,
        image_in=str(image.uuid or image.tag),
        timeout_s=timeout_s,
        disposable=disposable,
        cost_usd=None,
        cost_upper_bound_usd=worst,
        started_at=datetime.now(UTC).isoformat(timespec="seconds"),
        truncate_output_at=truncate_output_at,
    )
    t = time.monotonic()
    try:
        done = await image.run(
            shell=executed,
            timeout=timeout_s,
            disposable=disposable,
            files=files,
            truncate_output_at=truncate_output_at,
        )
        _fill_from_result(rec, done)
    except asyncio.CancelledError:
        rec.error = "cancelled"
        raise
    except Exception as exc:  # the record is the evidence; keep the failure on it
        rec.error = f"{type(exc).__name__}: {exc}"
    finally:
        rec.client_wall_s = time.monotonic() - t
        await guard.settle(worst, rec)
    return rec


class Uploader:
    """Uploads file contents once each (content-addressed), outside any guarded run and with
    retries, so an upload stall can never consume spend budget (attempt 2, 2026-10-25)."""

    def __init__(self, client, attempts: int = 3):
        self.client, self.attempts, self.cache = client, attempts, {}

    async def __call__(self, data: str | bytes):
        raw = data.encode() if isinstance(data, str) else data
        key = hashlib.sha256(raw).hexdigest()
        if key in self.cache:
            return self.cache[key]
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(raw)
        try:
            for attempt in range(1, self.attempts + 1):
                try:
                    self.cache[key] = await self.client.files.upload(f.name)
                    break
                except Exception:
                    if attempt == self.attempts:
                        raise
                    await asyncio.sleep(2 * attempt)
        finally:
            Path(f.name).unlink(missing_ok=True)
        return self.cache[key]


class SandboxForker:
    """Forks of one warm checkpoint: upload an overlay of files, run one command under the guard.
    `overlay` keys are paths relative to `workdir`, or absolute paths starting with "/"."""

    def __init__(
        self,
        checkpoint,
        guard: SpendGuard,
        upload: Uploader,
        workdir: str,
        instance_id: str,
        concurrency: int = 50,
    ):
        self.checkpoint, self.guard, self.upload = checkpoint, guard, upload
        self.workdir, self.instance_id = workdir, instance_id
        self.sem = asyncio.Semaphore(concurrency)

    async def __call__(
        self, branch: str, overlay: dict[str, str], command: str, timeout_s: int
    ) -> RunRecord:
        files = {}
        for path, content in overlay.items():
            dest = path if path.startswith("/") else f"{self.workdir}/{path}"
            files[dest] = await self.upload(content)
        async with self.sem:
            return await guarded_run(
                self.guard,
                self.checkpoint,
                label=f"{self.instance_id}/{branch}",
                shell=command,
                timeout_s=timeout_s,
                disposable=True,
                files=files,
            )
