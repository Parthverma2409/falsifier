"""Safety rails: explicit timeouts, spend ceiling checked before launch, cost on every record."""

import ast
import asyncio
import shlex
from pathlib import Path
from types import SimpleNamespace

import pytest

from falsifier.config import USD_PER_CPU_SECOND, USD_PER_RUN, SpendLimits
from falsifier.sandbox import SpendCeilingExceeded, SpendGuard, guarded_run

ROOT = Path(__file__).resolve().parent.parent


class FakeImage:
    """Stands in for a contree-sdk image: run() returns an awaitable that yields a result."""

    def __init__(self, cost=0.001, delay=0.0):
        self.uuid, self.tag = "fake-uuid", None
        self.cost, self.delay = cost, delay
        self.launched = 0
        self.kwargs = []

    def run(self, **kwargs):
        self.launched += 1
        self.kwargs.append(kwargs)
        return self._done()

    in_flight = peak = 0

    async def _done(self):
        self.in_flight += 1
        self.peak = max(self.peak, self.in_flight)
        await asyncio.sleep(self.delay)
        self.in_flight -= 1
        res = SimpleNamespace(user_cpu_time=0.1, system_cpu_time=0.0, monotonic_time=0.2)
        raw = SimpleNamespace(resources=res, state=SimpleNamespace(timed_out=False))
        result = SimpleNamespace(cost=self.cost, truncated=False, _raw=SimpleNamespace(result=raw))
        return SimpleNamespace(exit_code=0, stdout="ok", stderr="", uuid=None, result=result)


def guard(ceiling=1.0, cores=1, max_timeout_s=600, pin=True):
    return SpendGuard(
        SpendLimits(ceiling_usd=ceiling, cores=cores, max_timeout_s=max_timeout_s, pin_one_cpu=pin)
    )


async def test_record_carries_cost_and_passes_explicit_timeout():
    g, img = guard(), FakeImage(cost=0.0042)
    rec = await guarded_run(g, img, label="t", shell="true", timeout_s=7)
    assert rec.cost_usd == 0.0042
    assert rec.cpu_s == pytest.approx(0.1)
    assert img.kwargs[0]["timeout"] == 7
    assert g.spent_usd == pytest.approx(0.0042) and g.reserved_usd == pytest.approx(0)


@pytest.mark.parametrize("bad", [None, 0, -1, 601, 1.5, True])
async def test_timeout_must_be_explicit_and_bounded(bad):
    g, img = guard(), FakeImage()
    with pytest.raises((TypeError, ValueError)):
        await guarded_run(g, img, label="t", shell="true", timeout_s=bad)
    assert img.launched == 0


async def test_timeout_is_required():
    with pytest.raises(TypeError):
        await guarded_run(guard(), FakeImage(), label="t", shell="true")


async def test_ceiling_aborts_before_launch():
    g, img = guard(ceiling=0.05), FakeImage()
    # worst case for 60 s on one core is about $0.62, far over $0.05
    with pytest.raises(SpendCeilingExceeded):
        await guarded_run(g, img, label="loop", shell="true", timeout_s=60)
    assert img.launched == 0


async def test_ceiling_counts_completed_spend():
    worst_2s = USD_PER_RUN + USD_PER_CPU_SECOND * 2
    g, img = guard(ceiling=worst_2s * 1.5), FakeImage(cost=worst_2s)
    await guarded_run(g, img, label="first", shell="true", timeout_s=2)
    with pytest.raises(SpendCeilingExceeded):
        await guarded_run(g, img, label="second", shell="true", timeout_s=2)
    assert img.launched == 1


async def test_worst_case_scales_with_cores_unless_pinned():
    unpinned = guard(cores=4, pin=False).worst_case_usd(10)
    assert unpinned == pytest.approx(USD_PER_RUN + USD_PER_CPU_SECOND * 40)
    pinned = guard(cores=4, pin=True).worst_case_usd(10)
    assert pinned == pytest.approx(USD_PER_RUN + USD_PER_CPU_SECOND * 10)


async def test_commands_are_pinned_to_one_cpu():
    img = FakeImage()
    rec = await guarded_run(guard(cores=4), img, label="t", shell="echo 'a b' && true", timeout_s=3)
    sent = img.kwargs[0]["shell"]
    assert sent.startswith("taskset -c 0 sh -c ")
    assert shlex.split(sent)[-1] == "echo 'a b' && true"
    assert rec.command == sent


async def test_inflight_reservations_throttle_instead_of_overspending():
    worst = USD_PER_RUN + USD_PER_CPU_SECOND * 1
    g = guard(ceiling=worst * 2.5)  # room for two in flight at a time
    img = FakeImage(cost=0.0, delay=0.05)
    recs = await asyncio.gather(
        *(guarded_run(g, img, label=f"f{i}", shell="true", timeout_s=1) for i in range(6))
    )
    assert len(recs) == 6 and all(r.cost_usd == 0.0 for r in recs)
    assert img.peak == 2
    assert g.reserved_usd == pytest.approx(0)


async def test_failed_run_is_accounted_at_worst_case():
    class Boom(FakeImage):
        async def _done(self):
            raise RuntimeError("platform failure")

    g = guard()
    rec = await guarded_run(g, Boom(), label="x", shell="true", timeout_s=3)
    assert rec.error and rec.cost_usd is None
    assert g.spent_usd == pytest.approx(rec.cost_upper_bound_usd)


def _run_calls_without_timeout(path: Path) -> list[str]:
    bad = []
    for node in ast.walk(ast.parse(path.read_text())):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        if node.func.attr != "run":
            continue
        owner = node.func.value
        if isinstance(owner, ast.Name) and owner.id in {"asyncio", "subprocess"}:
            continue
        if not any(k.arg == "timeout" for k in node.keywords):
            bad.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    return bad


def test_every_sandbox_run_call_passes_a_timeout():
    files = [*ROOT.glob("falsifier/**/*.py"), *ROOT.glob("scripts/*.py")]
    bad = [loc for f in files for loc in _run_calls_without_timeout(f)]
    assert not bad, f".run() without timeout= at: {bad}"


async def test_per_instance_guard_nested_in_global():
    worst_1s = USD_PER_RUN + USD_PER_CPU_SECOND * 1
    top = SpendGuard(SpendLimits(ceiling_usd=10.0, cores=1))
    inst = SpendGuard(SpendLimits(ceiling_usd=worst_1s * 1.5, cores=1), parent=top, name="inst")
    img = FakeImage(cost=worst_1s)
    await guarded_run(inst, img, label="a", shell="true", timeout_s=1)
    assert top.spent_usd == pytest.approx(worst_1s) == pytest.approx(inst.spent_usd)
    with pytest.raises(SpendCeilingExceeded) as exc:
        await guarded_run(inst, img, label="b", shell="true", timeout_s=1)
    assert exc.value.scope == "inst" and img.launched == 1
    assert top.reserved_usd == pytest.approx(0) and inst.reserved_usd == pytest.approx(0)


async def test_global_guard_refusal_releases_the_child_reservation():
    worst_1s = USD_PER_RUN + USD_PER_CPU_SECOND * 1
    top = SpendGuard(SpendLimits(ceiling_usd=worst_1s * 0.5, cores=1))
    inst = SpendGuard(SpendLimits(ceiling_usd=10.0, cores=1), parent=top, name="inst")
    with pytest.raises(SpendCeilingExceeded) as exc:
        await guarded_run(inst, FakeImage(), label="a", shell="true", timeout_s=1)
    assert exc.value.scope == "global" and inst.reserved_usd == pytest.approx(0)
