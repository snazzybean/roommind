"""Process entry for a simulated HA: install the clock, run hass, handle restarts.

Usage: python -m roommind_sim.boot --instance-dir DIR [--until end|catch-up|none|<s>]
                                    [--then realtime|stop|pause] [--mode M --factor F]
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
from pathlib import Path

from . import clock as clockmod

RESTART_EXIT_CODE = 100
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
    p.add_argument("--resumed", action="store_true", help=argparse.SUPPRESS)
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse(sys.argv[1:] if argv is None else argv)
    inst_dir: Path = args.instance_dir.resolve()
    scenario = json.loads((inst_dir / "scenario.json").read_text())
    state_file = inst_dir / "state" / STATE_FILE

    clk = clockmod.install(float(scenario["start"]), mode=clockmod.PAUSED)
    if state_file.is_file():
        clk.restore(json.loads(state_file.read_text()))
    if not args.resumed:
        apply_start_args(clk, args.until, args.then, args.mode, args.factor, float(scenario["duration"]))
    clk.on_target = lambda: _on_target(clk)
    if clk.then_action == "stop-now":
        return 0

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
    _write_raw(state_file, json.dumps(clk.state()))
    if exit_code == RESTART_EXIT_CODE:
        os.execv(
            sys.executable,
            [sys.executable, "-m", "roommind_sim.boot", "--instance-dir", str(inst_dir), "--resumed"],
        )
    return exit_code


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
