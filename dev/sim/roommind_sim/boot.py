"""Process entry for a simulated HA: install the clock, run hass, handle restarts.

Usage: python -m roommind_sim.boot --instance-dir DIR [--until end|catch-up|none|<s>]
                                    [--then realtime|stop|pause] [--mode M --factor F]
"""

from __future__ import annotations

import argparse
import json
import os
import random
import signal
import sys
from pathlib import Path

from . import clock as clockmod

RESTART_EXIT_CODE = 100
# Virtual downtime of an in-run restart in turbo. The shutdown itself runs in real time,
# so a fixed value keeps the restart point (and everything after it) reproducible.
RESTART_DOWNTIME_S = 5.0
STATE_FILE = "clock.json"
_THEN = {
    "realtime": (clockmod.SCALED, 1.0),
    "pause": (clockmod.PAUSED, 1.0),
    # Shutdown waits on real timeouts; scaled(1) keeps it from jumping hours ahead.
    "stop": (clockmod.SCALED, 1.0),
}


def _parse(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="roommind_sim.boot")
    p.add_argument("--instance-dir", required=True, type=Path)
    p.add_argument("--until", default="none", help="end | catch-up | none | <seconds since start>")
    p.add_argument("--then", default="realtime", choices=sorted(_THEN))
    p.add_argument("--mode", default=None, choices=list(clockmod.MODES))
    p.add_argument("--factor", type=float, default=1.0)
    p.add_argument("--ttl", type=int, default=0, help="stop HA after this many real seconds (live instances)")
    p.add_argument("--resumed", action="store_true", help=argparse.SUPPRESS)
    return p.parse_args(argv)


def _loop_from_policy() -> bool:
    """HA before 2026.10 makes its event loop through the asyncio policy (no runner.create_event_loop)."""
    from importlib.metadata import version

    from .paths import ha_release

    release = ha_release(version("homeassistant"))
    return release is not None and release < (2026, 10)


def main(argv: list[str] | None = None) -> int:
    args = _parse(sys.argv[1:] if argv is None else argv)
    inst_dir: Path = args.instance_dir.resolve()
    scenario = json.loads((inst_dir / "scenario.json").read_text())
    state_file = inst_dir / "state" / STATE_FILE

    clk = clockmod.install(float(scenario["start"]), mode=clockmod.PAUSED, policy_loops=_loop_from_policy())
    seed_randint(int(scenario.get("seed", 1)))
    if state_file.is_file():
        clk.restore(json.loads(state_file.read_text()))
    if not args.resumed:
        apply_start_args(clk, args.until, args.then, args.mode, args.factor, float(scenario["duration"]))
    clk.on_target = lambda: _on_target(clk)
    if clk.then_action == "stop-now":
        return 0

    _arm_ttl(args.ttl, inst_dir, fresh=not args.resumed)
    os.environ["ROOMMIND_SIM_INSTANCE_DIR"] = str(inst_dir)
    import homeassistant.__main__ as ha_main

    sys.argv = [
        "hass",
        "-c",
        str(inst_dir / "config"),
        "--log-file",
        str(inst_dir / "logs" / "home-assistant.log"),
        "--log-rotate-days",
        "1",
    ]
    exit_code = ha_main.main()
    state = clk.state()
    plan_file = state_file.with_name("clock_plan.json")
    if plan_file.is_file():
        # simhome switched to real time for the shutdown; continue with the plan it saved.
        plan = json.loads(_read_raw(plan_file))
        for key in ("mode", "factor", "target", "then_mode", "then_action"):
            state[key] = plan.get(key)
        if plan.get("mode") == clockmod.TURBO:
            state["mono"] = turbo_resume_mono(float(plan["mono"]), float(state["mono"]))
        os.unlink(plan_file)
    _write_raw(state_file, json.dumps(state))
    if exit_code == RESTART_EXIT_CODE:
        os.execv(
            sys.executable,
            [sys.executable, "-m", "roommind_sim.boot", "--instance-dir", str(inst_dir), "--resumed"],
        )
    return exit_code


def turbo_resume_mono(stopped_at: float, after_shutdown: float) -> float:
    """Virtual time to resume at after a restart that was requested in turbo."""
    resume = stopped_at + RESTART_DOWNTIME_S
    if after_shutdown > resume:
        print(
            f"clock: shutdown took {after_shutdown - stopped_at:.1f}s, more than the fixed "
            f"{RESTART_DOWNTIME_S:.0f}s restart downtime; this restart is not reproducible",
            file=sys.stderr,
            flush=True,
        )
        return after_shutdown
    return resume


def seed_randint(seed: int) -> None:
    """Make HA's timer jitter a function of the scenario seed.

    DataUpdateCoordinator, time-change trackers and config entry retries stagger
    themselves with ``random.randint`` (urandom-seeded), which shifts RoomMind's update
    phase against the physics by up to 0.45 s per run. They bind ``from random import
    randint`` at import time, so this must run before ``homeassistant`` is imported.
    One generator per calling module keeps the draws independent of how imports and
    executor jobs interleave.
    """
    if "homeassistant" in sys.modules:
        raise RuntimeError("seed_randint() must run before homeassistant is imported")
    rngs: dict[str, random.Random] = {}

    def randint(a: int, b: int) -> int:
        module = sys._getframe(1).f_globals.get("__name__", "?")
        rng = rngs.get(module)
        if rng is None:
            rng = rngs[module] = random.Random(f"{seed}:randint:{module}")
        return rng.randint(a, b)

    random.randint = randint


def apply_start_args(
    clk: clockmod.Clock, until: str, then: str, mode: str | None, factor: float, duration: float
) -> None:
    """Set the initial clock plan for this start (not applied on in-run restarts)."""
    if until == "end":
        target: float | None = duration
    elif until == "catch-up":
        target = max(clk.mono(), clockmod._real_time() - clk.epoch_start)
    elif until == "none":
        target = None
    else:
        target = float(until)
    clk.then_action = "stop" if then == "stop" else None
    if target is not None and target > clk.mono():
        clk.run_until(target, _THEN[then])
    elif mode:
        clk.set_mode(mode, factor)
    else:
        clk.set_mode(*_THEN[then])
        if then == "stop" and target is not None:
            clk.on_target = None
            clk.then_action = "stop-now"


def _arm_ttl(ttl_s: int, inst_dir: Path, fresh: bool) -> None:
    """Real-time auto-stop that works without systemd; in-run restarts keep the deadline."""
    deadline_file = inst_dir / "state" / "ttl_deadline"
    real_now = clockmod._real_time()
    if fresh:
        if ttl_s <= 0:
            if deadline_file.is_file():
                os.unlink(deadline_file)
            return
        _write_raw(deadline_file, str(real_now + ttl_s))
    elif not deadline_file.is_file():
        return
    deadline = float(_read_raw(deadline_file))
    # SIGALRM counts real seconds; the handler turns it into a graceful HA stop.
    signal.signal(signal.SIGALRM, lambda *_: os.kill(os.getpid(), signal.SIGTERM))
    signal.alarm(max(1, int(deadline - real_now)))


def _read_raw(path: Path) -> str:
    fd = os.open(path, os.O_RDONLY)
    try:
        return os.read(fd, 1 << 20).decode()
    finally:
        os.close(fd)


def _write_raw(path: Path, text: str) -> None:
    # HA's blocking-I/O detector still wraps open()/Path.write_text after shutdown.
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    try:
        os.write(fd, text.encode())
    finally:
        os.close(fd)


def _on_target(clk: clockmod.Clock) -> None:
    if clk.then_action == "stop":
        clk.then_action = "stopped"
        os.kill(os.getpid(), signal.SIGTERM)


if __name__ == "__main__":
    sys.exit(main())
