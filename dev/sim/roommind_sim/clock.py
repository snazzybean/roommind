"""Virtual clock for a simulated Home Assistant process.

``install()`` must run before ``homeassistant`` is imported: HA binds
``from time import monotonic`` and ``partial(datetime.now, UTC)`` at import time,
so only a patch that is already in place reaches every caller.
"""

from __future__ import annotations

import asyncio
import datetime as _dt
import os
import sys
import threading
import time as _time
import traceback
from dataclasses import dataclass, field

_real_monotonic = _time.monotonic
_real_time = _time.time
_real_localtime = _time.localtime
_real_gmtime = _time.gmtime
_real_strftime = _time.strftime
_real_ctime = _time.ctime

TURBO = "turbo"
SCALED = "scaled"
PAUSED = "paused"
MODES = (TURBO, SCALED, PAUSED)

# Real wait while executor jobs are pending in turbo mode; their completion wakes the
# selector through the loop's self-pipe, so this only bounds the stall check interval.
_EXECUTOR_POLL_S = 0.05
_IDLE_POLL_S = 0.05
_PAUSED_POLL_S = 1.0


class ClockError(RuntimeError):
    """Raised for invalid clock operations."""


@dataclass
class Clock:
    """Virtual monotonic + wall clock with turbo, scaled and paused modes."""

    epoch_start: float
    mode: str = TURBO
    factor: float = 1.0
    stall_warn_s: float = 30.0
    stall_abort_s: float = 120.0
    _v: float = 0.0
    _r: float = field(default_factory=_real_monotonic)
    target: float | None = None
    then_mode: tuple[str, float] = (SCALED, 1.0)
    pending_exec: int = 0
    jumps: int = 0
    _stall_since: float | None = None
    _stall_warned: bool = False

    def mono(self) -> float:
        if self.mode == SCALED:
            return self._v + (_real_monotonic() - self._r) * self.factor
        return self._v

    def wall(self) -> float:
        return self.epoch_start + self.mono()

    def set_mode(self, mode: str, factor: float = 1.0) -> None:
        if mode not in MODES:
            raise ClockError(f"unknown clock mode {mode!r}")
        if mode == SCALED and factor <= 0:
            raise ClockError("scaled mode needs a factor > 0")
        self._v = self.mono()
        self._r = _real_monotonic()
        self.mode = mode
        self.factor = factor if mode == SCALED else 1.0

    def run_until(self, target_mono: float, then: tuple[str, float] = (SCALED, 1.0)) -> None:
        """Turbo until ``target_mono``, then switch to ``then``."""
        self.target = target_mono
        self.then_mode = then
        self.set_mode(TURBO)

    def advance(self, dt: float) -> None:
        if dt > 0:
            self._v += dt
            self.jumps += 1

    def state(self) -> dict:
        return {
            "epoch_start": self.epoch_start,
            "mono": self.mono(),
            "mode": self.mode,
            "factor": self.factor,
            "target": self.target,
            "then_mode": list(self.then_mode),
        }

    def restore(self, state: dict) -> None:
        self.epoch_start = float(state["epoch_start"])
        self._v = float(state["mono"])
        self._r = _real_monotonic()
        self.mode = state.get("mode", TURBO)
        self.factor = float(state.get("factor", 1.0))
        self.target = state.get("target")
        then = state.get("then_mode") or [SCALED, 1.0]
        self.then_mode = (then[0], float(then[1]))

    # --- selector integration -------------------------------------------------

    def _select(self, inner, timeout: float | None):  # noqa: ANN001
        if self.mode == SCALED:
            return inner.select(None if timeout is None else timeout / self.factor)
        if self.mode == PAUSED:
            return inner.select(_PAUSED_POLL_S if timeout is None or timeout > 0 else 0)

        events = inner.select(0)
        if events or timeout == 0:
            self._stall_since = None
            return events
        if self.pending_exec > 0:
            self._check_stall()
            return inner.select(_EXECUTOR_POLL_S)
        self._stall_since = None
        if timeout is None:
            return inner.select(_IDLE_POLL_S)
        if self.target is not None and self.mono() + timeout >= self.target:
            self.advance(self.target - self.mono())
            self.target = None
            self.set_mode(*self.then_mode)
            return []
        self.advance(timeout)
        return []

    def _check_stall(self) -> None:
        now = _real_monotonic()
        if self._stall_since is None:
            self._stall_since = now
            self._stall_warned = False
            return
        waited = now - self._stall_since
        if waited >= self.stall_abort_s:
            _dump_threads(f"clock: executor job blocked turbo for {waited:.0f}s real, aborting")
            os._exit(3)
        if waited >= self.stall_warn_s and not self._stall_warned:
            self._stall_warned = True
            _dump_threads(f"clock: executor job blocks turbo for {waited:.0f}s real")


def _dump_threads(message: str) -> None:
    lines = [f"ClockStallError: {message}"]
    frames = sys._current_frames()
    for thread in threading.enumerate():
        frame = frames.get(thread.ident) if thread.ident is not None else None
        if frame is None or thread is threading.main_thread():
            continue
        lines.append(f"--- thread {thread.name}")
        lines.extend(line.rstrip() for line in traceback.format_stack(frame))
    print("\n".join(lines), file=sys.stderr, flush=True)


CLOCK: Clock | None = None


def _clock() -> Clock:
    if CLOCK is None:
        raise ClockError("virtual clock not installed")
    return CLOCK


class VDatetime(_dt.datetime):
    @classmethod
    def now(cls, tz: _dt.tzinfo | None = None) -> VDatetime:  # type: ignore[override]
        return cls.fromtimestamp(_clock().wall(), tz)

    @classmethod
    def utcnow(cls) -> VDatetime:  # type: ignore[override]
        return cls.fromtimestamp(_clock().wall(), _dt.UTC).replace(tzinfo=None)

    @classmethod
    def today(cls) -> VDatetime:  # type: ignore[override]
        return cls.fromtimestamp(_clock().wall())


class VDate(_dt.date):
    @classmethod
    def today(cls) -> VDate:  # type: ignore[override]
        return cls.fromtimestamp(_clock().wall())


def install(
    epoch_start: float,
    mode: str = TURBO,
    factor: float = 1.0,
    *,
    stall_warn_s: float = 30.0,
    stall_abort_s: float = 120.0,
) -> Clock:
    """Patch time sources and the asyncio loop class; returns the clock."""
    global CLOCK  # noqa: PLW0603
    if "homeassistant" in sys.modules:
        raise ClockError("install() must run before homeassistant is imported")
    if CLOCK is not None:
        raise ClockError("virtual clock already installed")
    clock = Clock(epoch_start=epoch_start, stall_warn_s=stall_warn_s, stall_abort_s=stall_abort_s)
    clock.set_mode(mode, factor)
    CLOCK = clock

    _time.monotonic = clock.mono
    _time.monotonic_ns = lambda: int(clock.mono() * 1e9)
    _time.time = clock.wall
    _time.time_ns = lambda: int(clock.wall() * 1e9)
    _time.localtime = lambda secs=None: _real_localtime(clock.wall() if secs is None else secs)
    _time.gmtime = lambda secs=None: _real_gmtime(clock.wall() if secs is None else secs)
    _time.strftime = lambda fmt, t=None: _real_strftime(fmt, _real_localtime(clock.wall()) if t is None else t)
    _time.ctime = lambda secs=None: _real_ctime(clock.wall() if secs is None else secs)
    _dt.datetime = VDatetime  # type: ignore[misc]
    _dt.date = VDate  # type: ignore[misc]

    base = asyncio.EventLoop

    class _Selector:
        def __init__(self, inner) -> None:  # noqa: ANN001
            self._inner = inner

        def __getattr__(self, name: str):  # noqa: ANN204
            return getattr(self._inner, name)

        def select(self, timeout: float | None = None):  # noqa: ANN201
            return clock._select(self._inner, timeout)

    class SimEventLoop(base):  # type: ignore[valid-type,misc]
        def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
            super().__init__(*args, **kwargs)
            self._selector = _Selector(self._selector)

        def run_in_executor(self, executor, func, *args):  # noqa: ANN001, ANN002, ANN201
            fut = super().run_in_executor(executor, func, *args)
            clock.pending_exec += 1
            fut.add_done_callback(_executor_done)
            return fut

    def _executor_done(_fut: asyncio.Future) -> None:
        clock.pending_exec -= 1

    asyncio.EventLoop = SimEventLoop  # type: ignore[misc]
    return clock
