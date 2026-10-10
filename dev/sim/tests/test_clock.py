"""Tests for the virtual clock (each runs in its own interpreter)."""

from __future__ import annotations

from conftest import run_isolated

PRELUDE = """
import asyncio, time, datetime
from roommind_sim import clock as c
START = 1_768_176_000.0
clk = c.install(START, mode=MODE)
"""


def _run(body: str, mode: str = "turbo", timeout: float = 30.0):
    code = PRELUDE.replace("MODE", repr(mode)) + body
    res = run_isolated(code, timeout=timeout)
    assert res.returncode == 0, res.stderr
    return res.stdout.strip()


def test_turbo_jumps_over_sleep():
    out = _run(
        """
r0 = c._real_monotonic()
async def main():
    await asyncio.sleep(3600)
asyncio.run(main(), loop_factory=asyncio.EventLoop)
print(round(time.time() - START, 1), round(c._real_monotonic() - r0, 2))
"""
    )
    virt, real = out.split()
    assert float(virt) == 3600.0
    assert float(real) < 1.0


def test_time_sources_agree():
    out = _run(
        """
async def main():
    await asyncio.sleep(90)
asyncio.run(main(), loop_factory=asyncio.EventLoop)
now = datetime.datetime.now(datetime.UTC).timestamp()
print(round(now - time.time(), 3), round(time.monotonic() - clk.mono(), 3), round(time.time() - START, 1))
print(datetime.datetime.now().year, datetime.date.today().year, time.localtime().tm_year)
"""
    )
    first, second = out.splitlines()
    assert first.split() == ["0.0", "0.0", "90.0"]
    assert second.split() == ["2026", "2026", "2026"]


def test_scaled_runs_faster_than_real_time():
    out = _run(
        """
clk.set_mode("scaled", 60.0)
r0 = c._real_monotonic(); v0 = time.time()
async def main():
    await asyncio.sleep(30)
asyncio.run(main(), loop_factory=asyncio.EventLoop)
print(round(time.time() - v0, 1), round(c._real_monotonic() - r0, 2))
"""
    )
    virt, real = map(float, out.split())
    assert 29.5 <= virt <= 32
    assert 0.4 <= real <= 1.0


def test_paused_keeps_time_but_runs_callbacks():
    out = _run(
        """
async def main():
    t0 = time.time()
    loop = asyncio.get_running_loop()
    fut = loop.create_future()
    loop.call_soon(fut.set_result, 1)
    await fut
    await asyncio.sleep(0)
    print(time.time() - t0)
asyncio.run(main(), loop_factory=asyncio.EventLoop)
""",
        mode="paused",
    )
    assert out == "0.0"


def test_run_until_switches_mode():
    out = _run(
        """
clk.run_until(600.0, ("scaled", 1.0))
async def main():
    await asyncio.sleep(601)
r0 = c._real_monotonic()
asyncio.run(main(), loop_factory=asyncio.EventLoop)
print(clk.mode, round(c._real_monotonic() - r0, 1))
"""
    )
    mode, real = out.split()
    assert mode == "scaled"
    assert 0.9 <= float(real) <= 1.6


def test_executor_job_blocks_jump_until_done():
    out = _run(
        """
import time as t
real_sleep = t.sleep
async def main():
    loop = asyncio.get_running_loop()
    job = loop.run_in_executor(None, real_sleep, 0.3)
    sleeper = asyncio.ensure_future(asyncio.sleep(10))
    await job
    print(round(time.time() - START, 1))
    await sleeper
asyncio.run(main(), loop_factory=asyncio.EventLoop)
"""
    )
    assert out == "0.0"


def test_stalled_executor_aborts():
    code = """
import asyncio, time
from roommind_sim import clock as c
clk = c.install(0.0, stall_warn_s=0.2, stall_abort_s=0.6)
real_sleep = time.sleep
async def main():
    loop = asyncio.get_running_loop()
    asyncio.ensure_future(asyncio.sleep(5))
    await loop.run_in_executor(None, real_sleep, 30)
asyncio.run(main(), loop_factory=asyncio.EventLoop)
"""
    res = run_isolated(code, timeout=20)
    assert res.returncode == 3
    assert "ClockStallError" in res.stderr


def test_state_roundtrip():
    out = _run(
        """
clk.advance(123.0)
st = clk.state()
other = c.Clock(epoch_start=0.0)
other.restore(st)
print(other.wall() - START, other.mode)
"""
    )
    assert out == "123.0 turbo"


def test_install_after_homeassistant_import_fails():
    res = run_isolated(
        """
import sys, types
sys.modules["homeassistant"] = types.ModuleType("homeassistant")
from roommind_sim import clock as c
try:
    c.install(0.0)
except c.ClockError as err:
    print("refused", err)
"""
    )
    assert res.stdout.startswith("refused")


def test_isinstance_works_with_real_and_patched_objects():
    out = _run(
        """
import datetime as d
real = c._real_datetime(2020, 1, 1)
print(isinstance(d.datetime.now().date(), d.date), isinstance(real, d.datetime), isinstance(d.datetime.min, d.datetime),
      isinstance(d.datetime.now(), d.date), issubclass(c._real_datetime, d.datetime), d.datetime.__name__)
"""
    )
    assert out == "True True True True True datetime"
