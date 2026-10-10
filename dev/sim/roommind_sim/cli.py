"""``sim`` command line. Run ``dev/sim/bin/sim --help``."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from . import instance as inst_mod
from .haconfig import write_ha_config
from .instance import Instance
from .paths import DEFAULT_HA_VERSION, REPO_ROOT, SIM_ROOT, roommind_src, simhome_src, source_info, venv_python
from .scenario import Scenario, ScenarioError, load_scenario
from .scenario.timespec import format_offset, parse_duration

READY_TIMEOUT_S = 180


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 2
    try:
        return int(args.func(args) or 0)
    except ScenarioError as err:
        print(f"scenario error: {err}", file=sys.stderr)
        return 2
    except (RuntimeError, ValueError, OSError) as err:
        print(f"error: {err}", file=sys.stderr)
        return 1


# --- helpers ------------------------------------------------------------------------------


def _overrides(pairs: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for pair in pairs or []:
        key, _, value = pair.partition("=")
        if not key or not _:
            raise ValueError(f"--set expects key=value, got {pair!r}")
        out[key] = yaml.safe_load(value)
    return out


def _scenario_json(scn: Scenario) -> dict[str, Any]:
    data = dict(scn.raw)
    data["name"] = scn.name
    data["start"] = scn.start
    data["duration"] = scn.duration
    weather = dict(data.get("weather") or {})
    if weather.get("csv") and scn.source_path:
        weather["csv"] = str((scn.source_path.parent / weather["csv"]).resolve())
        data["weather"] = weather
    return data


def _prepare(inst: Instance, scn: Scenario, port: int, recorder: bool, rm_src: Path | None = None) -> None:
    inst.create_dirs()
    inst.scenario_path.write_text(json.dumps(_scenario_json(scn), indent=2, default=str))
    cidrs = ["127.0.0.1/32", "::1/128"]
    if cidr := inst_mod.lan_cidr():
        cidrs.append(cidr)
    write_ha_config(
        inst.config_dir,
        scn,
        instance=inst.name,
        port=port,
        roommind_src=rm_src or roommind_src(),
        simhome_src=simhome_src(),
        trusted_cidrs=cidrs,
        recorder=recorder,
    )
    _apply_seed(inst, scn)


def _apply_seed(inst: Instance, scn: Scenario) -> None:
    """Imported setups: pre-load RoomMind's EKF state and history before the first start."""
    seed = scn.raw.get("seed_data") or {}
    storage = inst.config_dir / ".storage"
    target = storage / "roommind"
    if seed.get("thermal_data") and not target.exists():
        thermal = json.loads(Path(seed["thermal_data"]).read_text())
        payload = {
            "version": 1,
            "minor_version": 1,
            "key": "roommind",
            "data": {"rooms": {}, "settings": {}, "thermal_data": thermal},
        }
        target.write_text(json.dumps(payload))
    if seed.get("history_dir"):
        dest = storage / "roommind_history"
        dest.mkdir(parents=True, exist_ok=True)
        for csv_file in Path(seed["history_dir"]).glob("*.csv"):
            if not (dest / csv_file.name).exists():
                (dest / csv_file.name).write_bytes(csv_file.read_bytes())


def _python(version: str) -> Path:
    py = venv_python(version)
    if not py.exists():
        raise RuntimeError(f"HA venv {version} missing, run: sim venv add {version}")
    return py


def _check_frontend() -> None:
    bundle = roommind_src() / "frontend" / "roommind-panel.js"
    src = REPO_ROOT / "frontend" / "src"
    newest = max((p.stat().st_mtime for p in src.rglob("*") if p.is_file()), default=0)
    if not bundle.exists() or bundle.stat().st_mtime < newest:
        print("building frontend (bundle older than frontend/src) ...", flush=True)
        subprocess.run(["npm", "run", "build", "--silent"], cwd=REPO_ROOT / "frontend", check=True)


def _wait_ready(inst: Instance, timeout: float = READY_TIMEOUT_S) -> bool:
    port = inst.meta()["port"]
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not inst.is_running():
            return False
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/manifest.json", timeout=2) as resp:
                if resp.status == 200 and inst.token_path.exists():
                    _ws(inst, "simhome/status")
                    return True
        except Exception:  # noqa: BLE001 - still starting (HTTP up before simhome, or token from a copied run)
            pass
        time.sleep(1)
    return False


def _live(name: str) -> Instance:
    inst = Instance.live(name)
    if not inst.meta_path.exists():
        raise RuntimeError(f"no instance {name!r} (sim ps lists them)")
    return inst


def _ws(inst: Instance, msg_type: str, payload: dict[str, Any] | None = None) -> Any:
    from .wsclient import call

    if not inst.token_path.exists():
        raise RuntimeError("instance has no token yet (still starting?)")
    return call(f"http://127.0.0.1:{inst.meta()['port']}", inst.token_path.read_text().strip(), msg_type, payload)


def _fmt_time(epoch: float, tz: str | None = None) -> str:
    return datetime.fromtimestamp(epoch).strftime("%Y-%m-%d %H:%M:%S")


def _kv(pairs: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for pair in pairs:
        key, sep, value = pair.partition("=")
        if not sep:
            raise ValueError(f"expected key=value, got {pair!r}")
        out[key] = yaml.safe_load(value)
    return out


# --- commands -------------------------------------------------------------------------------


def cmd_run(args: argparse.Namespace) -> int:
    scn = load_scenario(args.scenario, _overrides(args.set))
    if args.until:
        scn.duration = parse_duration(args.until)
    _check_frontend() if args.ui else None
    inst = Instance.run(scn.name)
    port = inst_mod.allocate_port(inst.name, batch=True)
    rm_src = roommind_src(override=args.roommind_src)
    _prepare(inst, scn, port, args.recorder, rm_src)
    src = source_info(rm_src)
    inst.write_meta(
        name=inst.name,
        kind="run",
        port=port,
        ha_version=args.ha,
        source=src,
        scenario=scn.name,
        created=time.time(),
    )
    py = _python(args.ha)
    print(f"run {inst.dir.name}: {scn.name}, {format_offset(scn.duration)} simulated", flush=True)
    print(f"  RoomMind {src.get('git', '?')} ({src['path']})", flush=True)
    t0 = time.time()
    with (inst.logs_dir / "boot.log").open("ab") as log:
        proc = subprocess.Popen(
            inst_mod.boot_command(inst, py, ["--until", "end", "--then", "stop"]),
            env=inst_mod.boot_env(),
            cwd=SIM_ROOT,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        inst.write_meta(pid=proc.pid, launcher="foreground")
        last = ""
        last_change = time.time()
        while proc.poll() is None:
            time.sleep(1)
            progress = _progress(inst, scn)
            if progress != last:
                last, last_change = progress, time.time()
                if progress and not args.quiet:
                    print(f"\r  {progress}", end="", flush=True)
            elif time.time() - last_change > args.stall_timeout:
                print(f"\nno progress for {args.stall_timeout:.0f}s real, killing the run", file=sys.stderr)
                proc.terminate()
                try:
                    proc.wait(30)
                except subprocess.TimeoutExpired:
                    proc.kill()
                break
    print()
    inst_mod.release_port(inst.name)
    real = time.time() - t0
    code = proc.returncode
    inst.write_meta(finished=time.time(), exit_code=code, real_seconds=round(real, 1))
    if code != 0:
        print(f"HA exited with {code}; see {inst.logs_dir}/boot.log and home-assistant.log", file=sys.stderr)
    from .analysis import evaluate_run

    summary = evaluate_run(inst.dir)
    _print_summary(summary, real)
    if not args.keep:
        _shrink_run(inst)
    print(f"report: {inst.dir / 'report.html'}")
    if code != 0:
        return 3
    return 0 if summary.get("passed", True) else 1


def _progress(inst: Instance, scn: Scenario) -> str:
    clock_file = inst.state_dir / "clock.json"
    if not clock_file.exists():
        return "starting HA ..."
    try:
        mono = json.loads(clock_file.read_text())["mono"]
    except (ValueError, KeyError):
        return ""
    pct = min(100.0, 100 * mono / scn.duration) if scn.duration else 100
    return f"{format_offset(mono)} / {format_offset(scn.duration)} ({pct:.0f}%)"


def _print_summary(summary: dict[str, Any], real: float) -> None:
    print(f"simulated {format_offset(summary.get('simulated_s', 0))} in {real:.0f}s real")
    for line in summary.get("lines", []):
        print(f"  {line}")
    exp = summary.get("expectations", [])
    if exp:
        print("expectations:")
        for e in exp:
            mark = "PASS" if e["passed"] else ("XFAIL" if e.get("known_failure") else "FAIL")
            print(f"  [{mark}] {e['label']}: {e['detail']}")
    print("RESULT:", "PASS" if summary.get("passed", True) else "FAIL")


def _shrink_run(inst: Instance) -> None:
    """Compress timelines and drop HA caches of a finished run (disk is scarce)."""
    import gzip

    for name in ("deps", "tts", "blueprints"):
        path = inst.config_dir / name
        if path.is_dir():
            subprocess.run(["rm", "-rf", str(path)], check=False)
    for path in inst.timeline_dir.glob("*.jsonl"):
        path.with_suffix(".jsonl.gz").write_bytes(gzip.compress(path.read_bytes(), compresslevel=6))
        path.unlink()


def cmd_suite(args: argparse.Namespace) -> int:
    from concurrent.futures import ThreadPoolExecutor

    from .scenario.loader import SCENARIO_DIR

    names = []
    for path in sorted(SCENARIO_DIR.glob("*.yaml")):
        data = yaml.safe_load(path.read_text()) or {}
        tags = set(data.get("tags") or [])
        if args.tag and not set(args.tag) & tags:
            continue
        if args.skip_tag and set(args.skip_tag) & tags:
            continue
        if data.get("abstract"):
            continue
        names.append(path.stem)
    if not names:
        print("no scenarios match")
        return 2
    sim = SIM_ROOT / "bin" / "sim"
    extra = ["--roommind-src", args.roommind_src] if args.roommind_src else []

    def one(name: str) -> tuple[str, int, str, float]:
        t0 = time.time()
        res = subprocess.run([str(sim), "run", name, "-q", *extra], capture_output=True, text=True, check=False)
        run_dir = next((line.split()[1].rstrip(":") for line in res.stdout.splitlines() if line.startswith("run ")), "")
        return name, res.returncode, run_dir, time.time() - t0

    print(f"suite: {len(names)} scenario(s), {args.jobs} parallel")
    results = []
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        for name, code, run_dir, secs in pool.map(one, names):
            summary_file = inst_mod.sim_home() / "runs" / run_dir / "summary.json"
            summary = json.loads(summary_file.read_text()) if run_dir and summary_file.exists() else {}
            xfail = any(not e["passed"] and e.get("known_failure") for e in summary.get("expectations", []))
            status = {0: "XFAIL" if xfail else "PASS", 1: "FAIL", 2: "INVALID", 3: "BROKEN"}.get(code, f"EXIT {code}")
            if summary.get("unexpected_pass"):
                status = "XPASS"
            results.append((name, status, run_dir, secs))
            print(f"  {status:7} {name:40} {secs:6.0f}s  {run_dir}", flush=True)
    bad = [r for r in results if r[1] in ("FAIL", "INVALID", "BROKEN") or r[1].startswith("EXIT")]
    print(f"suite: {len(results) - len(bad)}/{len(results)} ok")
    return 1 if bad else 0


def cmd_prune(args: argparse.Namespace) -> int:
    runs_dir = inst_mod.sim_home() / "runs"
    runs = sorted(p for p in runs_dir.iterdir() if p.is_dir()) if runs_dir.is_dir() else []
    keep = set(runs[-args.keep :]) if args.keep else set()
    cutoff = time.time() - parse_duration(args.older_than) if args.older_than else None
    removed = 0
    for run in runs:
        if run in keep or (cutoff is not None and run.stat().st_mtime > cutoff):
            continue
        subprocess.run(["rm", "-rf", str(run)], check=True)
        removed += 1
    shots = 0
    for inst in inst_mod.list_instances():
        for shot in sorted((inst.dir / "shots").glob("*.png"))[: -args.keep_shots or None]:
            shot.unlink()
            shots += 1
    print(f"removed {removed} run(s) and {shots} screenshot(s); kept {len(runs) - removed} run(s)")
    return 0


def cmd_up(args: argparse.Namespace) -> int:
    inst = Instance.live(args.name)
    if inst.is_running():
        print(f"{args.name} already running: {inst.url()}")
        return 0
    from .scenario import load_scenario_dict

    if args.from_run:
        _seed_from_run(inst, _resolve_run(args.from_run))
        scn = load_scenario_dict(json.loads(inst.scenario_path.read_text()))
    elif args.fresh or not inst.scenario_path.exists():
        if not args.scenario:
            raise RuntimeError("new instance needs --scenario")
        if inst.dir.exists():
            subprocess.run(["rm", "-rf", str(inst.dir)], check=True)
        scn = load_scenario(args.scenario, _overrides(args.set))
    else:
        scn = load_scenario_dict(json.loads(inst.scenario_path.read_text()))
    rm_src = roommind_src(override=args.roommind_src)
    if not args.roommind_src:
        _check_frontend()
    port = inst_mod.allocate_port(args.name)
    _prepare(inst, scn, port, args.recorder, rm_src)
    inst.write_meta(
        name=args.name, kind="live", port=port, ha_version=args.ha, source=source_info(rm_src), scenario=scn.name
    )
    boot_args = ["--until", "catch-up" if args.catch_up else "none", "--then", "pause" if args.paused else "realtime"]
    if args.speed and not args.catch_up:
        boot_args += ["--mode", "scaled", "--factor", str(args.speed)]
    elif args.paused and not args.catch_up:
        boot_args += ["--mode", "paused"]
    launcher = inst_mod.start_live(inst, _python(args.ha), boot_args, int(parse_duration(args.ttl)))
    print(f"starting {args.name} ({launcher}) from {REPO_ROOT} ...", flush=True)
    if not _wait_ready(inst):
        print(f"not ready after {READY_TIMEOUT_S}s; check: sim logs {args.name}", file=sys.stderr)
        return 1
    print(f"ready: {inst.url()}  (local http://127.0.0.1:{port})")
    return 0


def _seed_from_run(inst: Instance, run_dir: Path) -> None:
    if not (run_dir / "scenario.json").exists():
        candidate = inst_mod.sim_home() / "runs" / run_dir
        run_dir = candidate if candidate.exists() else run_dir
    if not (run_dir / "scenario.json").exists():
        raise RuntimeError(f"not a run directory: {run_dir}")
    if inst.dir.exists():
        subprocess.run(["rm", "-rf", str(inst.dir)], check=True)
    inst.dir.mkdir(parents=True)
    for part in ("config", "state", "timeline", "scenario.json", "token"):
        src = run_dir / part
        if src.exists():
            subprocess.run(["cp", "-a", str(src), str(inst.dir / part)], check=True)
    # Continue from where the run stopped, paused until told otherwise.
    clock_file = inst.state_dir / "clock.json"
    if clock_file.exists():
        state = json.loads(clock_file.read_text())
        state.update(mode="paused", target=None, then_action=None)
        clock_file.write_text(json.dumps(state))


def cmd_down(args: argparse.Namespace) -> int:
    inst = _live(args.name)
    stopped = inst_mod.stop(inst)
    print(f"{args.name}: {'stopped' if stopped else 'was not running'}")
    if args.rm:
        inst.remove()
        print(f"{args.name}: removed")
    return 0


def cmd_ps(args: argparse.Namespace) -> int:
    rows = []
    for inst in inst_mod.list_instances():
        meta = inst.meta()
        rows.append(
            (
                inst.name,
                "running" if inst.is_running() else "stopped",
                str(meta.get("port", "")),
                meta.get("scenario", ""),
                str((meta.get("source") or {}).get("git", meta.get("source", "")))
                if isinstance(meta.get("source"), dict)
                else meta.get("source", ""),
            )
        )
    if not rows:
        print("no live instances")
        return 0
    widths = [max(len(r[i]) for r in rows) for i in range(5)]
    for row in rows:
        print("  ".join(c.ljust(w) for c, w in zip(row, widths, strict=False)))
    return 0


def _source_label(source: Any) -> str:
    if isinstance(source, dict):
        return f"{source.get('git', '')} {source.get('path', '')}".strip()
    return str(source or "")


def cmd_logs(args: argparse.Namespace) -> int:
    inst = _live(args.name) if not args.run else Instance(Path(args.name).name, Path(args.name))
    log = inst.logs_dir / "home-assistant.log"
    cmd = ["tail", "-n", str(args.lines)] + (["-F"] if args.follow else []) + [str(log)]
    return subprocess.call(cmd)


def cmd_status(args: argparse.Namespace) -> int:
    inst = _live(args.name)
    st = _ws(inst, "simhome/status")
    clk = st["clock"] or {}
    print(f"{args.name}: {st['scenario']}  url {inst.url()}")
    print(f"  sim time  {_fmt_time(st['now'])}  ({format_offset(st['elapsed'])} of {format_offset(st['duration'])})")
    lag = st["now"] - st["real_time"]
    print(f"  clock     {clk.get('mode')} x{clk.get('factor')}  (sim - real = {format_offset(lag)})")
    print(f"  timeline  {len(st['timeline_done'])}/{st['timeline_total']} done, provisioned={st['provisioned']}")
    return 0


def cmd_clock(args: argparse.Namespace) -> int:
    inst = _live(args.name)
    payload: dict[str, Any] = {}
    if args.op == "ff":
        payload = {"ff": parse_duration(args.value), "then": args.then}
    elif args.op == "speed":
        payload = {"mode": "scaled", "factor": float(args.value)}
    elif args.op == "pause":
        payload = {"mode": "paused"}
    elif args.op == "realtime":
        payload = {"mode": "scaled", "factor": 1.0}
    elif args.op == "until":
        scn_tz = json.loads(inst.scenario_path.read_text()).get("location", {}).get("time_zone", "UTC")
        from .scenario.timespec import parse_start

        payload = {"until": parse_start(args.value, scn_tz), "then": args.then}
    print(json.dumps(_ws(inst, "simhome/clock", payload), indent=2))
    return 0


def cmd_do(args: argparse.Namespace) -> int:
    inst = _live(args.name)
    result = _ws(inst, "simhome/action", {"action": args.action, "args": _kv(args.kv)})
    print(json.dumps(result, indent=2, default=str))
    return 0


def cmd_ws(args: argparse.Namespace) -> int:
    inst = _live(args.name)
    payload = json.loads(args.payload) if args.payload else {}
    print(json.dumps(_ws(inst, args.type, payload), indent=2, default=str))
    return 0


def cmd_world(args: argparse.Namespace) -> int:
    inst = _live(args.name)
    print(json.dumps(_ws(inst, "simhome/world"), indent=2, default=str))
    return 0


def cmd_shot(args: argparse.Namespace) -> int:
    from .ui import screenshot

    inst = _live(args.name)
    status = _ws(inst, "simhome/status")
    result = screenshot(
        inst,
        path=args.path,
        viewport=args.viewport,
        dark=args.dark,
        lang=args.lang,
        wait_s=args.wait,
        full_page=args.full,
        out=Path(args.out) if args.out else None,
        sim_now=status["now"],
        actions=args.do,
    )
    errors = _ws(inst, "system_log/list")
    recent = [e for e in errors if e.get("level") in ("ERROR", "CRITICAL")]
    print(result["file"])
    for c in result["console"]:
        print(f"  browser {c['type']}: {c['text'][:300]}")
    for e in recent[:10]:
        print(f"  HA {e.get('level')}: {e.get('name')}: {' | '.join(e.get('message', []))[:300]}")
    return 0


def cmd_import(args: argparse.Namespace) -> int:
    from .importer.diag import import_diagnostics

    path = import_diagnostics(
        Path(args.diagnostics),
        [Path(h) for h in args.history],
        name=args.name,
        mode=args.mode,
        duration=args.duration,
    )
    scenario = yaml.safe_load(path.read_text())
    print(f"scenario: {path}")
    print(
        f"  {len(scenario['house']['rooms'])} room(s), start {scenario['start']}, duration {scenario['duration']}, mode {args.mode}"
    )
    print("assumptions:")
    for a in scenario.get("assumptions", []):
        print(f"  - {a}")
    print(f"next: sim run {path}   or   sim up <name> --scenario {path}")
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    """Metric diff of two runs, e.g. before/after a fix (sim run X --roommind-src v1.7.8 vs. this checkout)."""
    a_dir, b_dir = _resolve_run(args.a), _resolve_run(args.b)
    a = json.loads((a_dir / "summary.json").read_text())
    b = json.loads((b_dir / "summary.json").read_text())
    print(f"A: {a_dir.name}  ({(a.get('source') or {}).get('git', '?')})")
    print(f"B: {b_dir.name}  ({(b.get('source') or {}).get('git', '?')})")
    for group in ("rooms", "devices", "model"):
        for name, ma in a["metrics"][group].items():
            mb = b["metrics"][group].get(name, {})
            rows = []
            for key, va in ma.items():
                vb = mb.get(key)
                if isinstance(va, int | float) and isinstance(vb, int | float) and va != vb:
                    delta = vb - va
                    pct = f" ({100 * delta / va:+.0f}%)" if va else ""
                    rows.append(f"    {key:22} {va:>10} -> {vb:<10} {delta:+.3g}{pct}")
            if rows:
                print(f"  {dict(rooms='room', devices='device', model='model')[group]} {name}")
                print("\n".join(rows))
    ea = {e["label"]: e["passed"] for e in a.get("expectations", [])}
    for e in b.get("expectations", []):
        before = ea.get(e["label"])
        if before is not None and before != e["passed"]:
            print(f"  expectation {e['label']}: {'PASS' if before else 'FAIL'} -> {'PASS' if e['passed'] else 'FAIL'}")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    from .analysis import evaluate_run

    run_dir = _resolve_run(args.run)
    summary = evaluate_run(run_dir)
    _print_summary(summary, 0)
    print(f"report: {run_dir / 'report.html'}")
    return 0 if summary.get("passed", True) else 1


def _resolve_run(value: str) -> Path:
    path = Path(value)
    if (path / "scenario.json").exists():
        return path
    runs = inst_mod.sim_home() / "runs"
    if value == "last":
        candidates = sorted(p for p in runs.iterdir() if (p / "scenario.json").exists())
        if not candidates:
            raise RuntimeError("no runs yet")
        return candidates[-1]
    if (runs / value / "scenario.json").exists():
        return runs / value
    matches = sorted(p for p in runs.glob(f"*{value}*") if (p / "scenario.json").exists())
    if matches:
        return matches[-1]
    raise RuntimeError(f"no run {value!r}")


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="sim", description="RoomMind simulation environment")
    sub = p.add_subparsers()

    run = sub.add_parser("run", help="batch run a scenario (turbo) and evaluate it")
    run.add_argument("scenario")
    run.add_argument("--set", action="append", default=[], metavar="KEY=VALUE")
    run.add_argument("--until", help="override duration, e.g. 3d")
    run.add_argument("--ha", default=DEFAULT_HA_VERSION)
    run.add_argument(
        "--roommind-src", help="RoomMind code to test: path or git ref (e.g. v1.7.7); default: this checkout"
    )
    run.add_argument("--recorder", action="store_true")
    run.add_argument("--keep", action="store_true", help="keep the full HA config dir")
    run.add_argument(
        "--ui", action="store_true", help="build the frontend first (to open the run with sim up --from-run)"
    )
    run.add_argument("-q", "--quiet", action="store_true")
    run.add_argument(
        "--stall-timeout",
        type=float,
        default=300.0,
        help="abort when the sim clock does not move for this many real seconds",
    )
    run.set_defaults(func=cmd_run)

    up = sub.add_parser("up", help="start a live instance (UI on the LAN)")
    up.add_argument("name", nargs="?", default="main")
    up.add_argument("--scenario")
    up.add_argument("--set", action="append", default=[], metavar="KEY=VALUE")
    up.add_argument("--fresh", action="store_true", help="discard existing state")
    up.add_argument("--from-run", help="continue from a finished batch run (paused)")
    up.add_argument("--catch-up", action="store_true", help="turbo until real now, then real time")
    up.add_argument("--paused", action="store_true")
    up.add_argument("--speed", type=float, help="time-lapse factor")
    up.add_argument("--ttl", default="4h", help="auto-stop after this real time")
    up.add_argument("--ha", default=DEFAULT_HA_VERSION)
    up.add_argument("--roommind-src", help="RoomMind code: path or git ref; default: this checkout")
    up.add_argument("--recorder", action="store_true")
    up.set_defaults(func=cmd_up)

    down = sub.add_parser("down", help="stop a live instance")
    down.add_argument("name", nargs="?", default="main")
    down.add_argument("--rm", action="store_true", help="also delete its data")
    down.set_defaults(func=cmd_down)

    ps = sub.add_parser("ps", help="list live instances")
    ps.set_defaults(func=cmd_ps)

    logs = sub.add_parser("logs", help="show the HA log")
    logs.add_argument("name", nargs="?", default="main")
    logs.add_argument("-n", "--lines", type=int, default=50)
    logs.add_argument("-f", "--follow", action="store_true")
    logs.add_argument("--run", action="store_true", help="name is a run directory")
    logs.set_defaults(func=cmd_logs)

    status = sub.add_parser("status", help="clock and progress of a live instance")
    status.add_argument("name", nargs="?", default="main")
    status.set_defaults(func=cmd_status)

    clock = sub.add_parser("clock", help="control the clock: ff 6h | speed 60 | pause | realtime | until ISO")
    clock.add_argument("name")
    clock.add_argument("op", choices=["ff", "speed", "pause", "realtime", "until"])
    clock.add_argument("value", nargs="?")
    clock.add_argument("--then", default="keep", choices=["keep", "realtime", "pause"])
    clock.set_defaults(func=cmd_clock)

    do = sub.add_parser("do", help="run an action now, e.g. sim do main window.open entity_id=binary_sensor.x")
    do.add_argument("name")
    do.add_argument("action")
    do.add_argument("kv", nargs="*")
    do.set_defaults(func=cmd_do)

    ws = sub.add_parser("ws", help="send any WebSocket command, e.g. sim ws main roommind/rooms/list")
    ws.add_argument("name")
    ws.add_argument("type")
    ws.add_argument("payload", nargs="?")
    ws.set_defaults(func=cmd_ws)

    world = sub.add_parser("world", help="ground truth of a live instance")
    world.add_argument("name", nargs="?", default="main")
    world.set_defaults(func=cmd_world)

    shot = sub.add_parser(
        "shot", help="screenshot the UI, e.g. sim shot main --path /roommind/room/wohnzimmer --viewport mobile"
    )
    shot.add_argument("name", nargs="?", default="main")
    shot.add_argument("--path", default="/roommind")
    shot.add_argument("--viewport", default="desktop", choices=["desktop", "mobile", "tablet"])
    shot.add_argument("--dark", action="store_true")
    shot.add_argument("--lang", default="de")
    shot.add_argument("--wait", type=float, default=4.0, help="seconds to let the panel settle")
    shot.add_argument("--full", action="store_true", help="full page")
    shot.add_argument("--do", action="append", default=[], help="click:<text> | wait:<ms> | scroll:<px>, repeatable")
    shot.add_argument("--out")
    shot.set_defaults(func=cmd_shot)

    suite = sub.add_parser("suite", help="run all library scenarios (or by tag) in parallel")
    suite.add_argument("--tag", action="append", default=[])
    suite.add_argument("--skip-tag", action="append", default=[])
    suite.add_argument("-j", "--jobs", type=int, default=3)
    suite.add_argument("--roommind-src")
    suite.set_defaults(func=cmd_suite)

    prune = sub.add_parser("prune", help="delete old runs and screenshots")
    prune.add_argument("--keep", type=int, default=20, help="keep the newest N runs")
    prune.add_argument("--older-than", help="only delete runs older than this, e.g. 7d")
    prune.add_argument("--keep-shots", type=int, default=30)
    prune.set_defaults(func=cmd_prune)

    imp = sub.add_parser(
        "import", help="diagnostics export (+ history CSVs) -> scenario under $ROOMMIND_SIM_HOME/imports"
    )
    imp.add_argument("diagnostics")
    imp.add_argument("--history", action="append", default=[], help="roommind_<room>_*.csv from the analytics export")
    imp.add_argument("--name")
    imp.add_argument("--mode", choices=["closed", "replay"], default="closed")
    imp.add_argument("--duration", default="2d", help="closed mode: how long to continue after the export")
    imp.set_defaults(func=cmd_import)

    compare = sub.add_parser("compare", help="metric diff of two runs (names, paths or 'last')")
    compare.add_argument("a")
    compare.add_argument("b")
    compare.set_defaults(func=cmd_compare)

    report = sub.add_parser("report", help="re-evaluate a run (name, path or 'last')")
    report.add_argument("run", nargs="?", default="last")
    report.set_defaults(func=cmd_report)
    return p


if __name__ == "__main__":
    sys.exit(main())
