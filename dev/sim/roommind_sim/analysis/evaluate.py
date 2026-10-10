"""Evaluate a finished run: metrics, default invariants, scenario expectations, report."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from ..scenario.timespec import format_offset, parse_at
from .invariants import DEFAULT_INVARIANTS, INVARIANTS
from .load import RunData, load_run
from .metrics import compute_metrics


def evaluate_run(run_dir: Path, write_report: bool = True) -> dict[str, Any]:
    run = load_run(run_dir)
    metrics = compute_metrics(run)
    results = [_evaluate(run, metrics, exp) for exp in run.scenario.expect]
    explicit = {e.get("invariant") for e in run.scenario.expect}
    warnings = []
    for name in DEFAULT_INVARIANTS:
        if name in explicit:
            continue
        found = INVARIANTS[name](run)
        if found:
            warnings.append({"invariant": name, "violations": [v.as_dict() for v in found[:10]], "count": len(found)})
    broken = _broken(run)
    if broken:
        results.insert(0, {"label": "run sanity", "passed": False, "detail": broken})
    failed = [r for r in results if not r["passed"]]
    known = run.scenario.known_failure
    for r in failed:
        if r["label"] != "run sanity":
            r["known_failure"] = known
    summary = {
        "scenario": run.scenario.name,
        "refs": run.scenario.refs,
        "simulated_s": run.end - run.start,
        "metrics": metrics,
        "expectations": results,
        "warnings": warnings,
        "known_failure": known,
        "passed": not failed or (bool(known) and not broken),
        "unexpected_pass": bool(known) and not failed and bool(results),
        "lines": _lines(metrics, warnings),
        "real_seconds": run.meta.get("real_seconds"),
        "source": run.meta.get("source"),
    }
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
    if write_report:
        from .report import write_report as _write

        _write(run, summary)
    return summary


def _broken(run: RunData) -> str | None:
    """A run that never controlled anything must not pass silently."""
    code = run.meta.get("exit_code")
    if code not in (None, 0):
        return f"HA exited with code {code}"
    failed = next((e for e in run.events if e.get("type") == "ha" and e.get("what") == "provision_failed"), None)
    if failed:
        return f"RoomMind rejected the scenario config: {failed.get('error')}"
    if not any(e.get("type") == "ha" and e.get("what") == "provisioned" for e in run.events):
        return "RoomMind was never provisioned (see logs/home-assistant.log)"
    if not run.observer:
        return "no RoomMind state observed"
    expected = (run.end - run.start) / max(run.scenario.sample_interval, 1)
    if len(run.samples) < 0.9 * expected:
        return f"only {len(run.samples)} of ~{expected:.0f} samples"
    return None


def _evaluate(run: RunData, metrics: dict[str, Any], exp: dict[str, Any]) -> dict[str, Any]:
    if "invariant" in exp:
        name = exp["invariant"]
        if name not in INVARIANTS:
            return {
                "label": f"invariant {name}",
                "passed": False,
                "detail": f"unknown invariant (known: {', '.join(INVARIANTS)})",
            }
        args = {k: v for k, v in exp.items() if k not in ("invariant", "label")}
        found = INVARIANTS[name](run, **args)
        detail = (
            "ok" if not found else f"{len(found)} violation(s), first at {_rel(run, found[0].t)}: {found[0].detail}"
        )
        return {
            "label": exp.get("label", f"invariant {name}"),
            "passed": not found,
            "detail": detail,
            "violations": [v.as_dict() for v in found[:50]],
        }
    if "metric" in exp:
        return _metric(run, metrics, exp)
    return _check(run, exp)


def _metric(run: RunData, metrics: dict[str, Any], exp: dict[str, Any]) -> dict[str, Any]:
    group, _, key = exp["metric"].partition(".")
    label = exp.get("label", exp["metric"])
    if group == "comfort" or group == "room":
        scope = metrics["rooms"].get(exp.get("room", ""), {})
        label += f"[{exp.get('room')}]"
    elif group == "device":
        scope = metrics["devices"].get(exp.get("entity_id", ""), {})
        label += f"[{exp.get('entity_id')}]"
    elif group == "model":
        scope = metrics["model"].get(exp.get("room", ""), {})
        label += f"[{exp.get('room')}]"
    else:
        return {"label": label, "passed": False, "detail": f"unknown metric group {group!r}"}
    value = scope.get(key)
    if value is None:
        return {
            "label": label,
            "passed": False,
            "detail": f"no value for {key!r} (available: {', '.join(sorted(scope))})",
        }
    ok = True
    bounds = []
    if "max" in exp:
        ok &= value <= exp["max"]
        bounds.append(f"<= {exp['max']}")
    if "min" in exp:
        ok &= value >= exp["min"]
        bounds.append(f">= {exp['min']}")
    return {
        "label": label,
        "passed": bool(ok),
        "detail": f"{value} (expected {' and '.join(bounds) or 'a value'})",
        "value": value,
    }


class _Obj(SimpleNamespace):
    def __getattr__(self, name: str) -> Any:  # missing fields read as None instead of raising
        return None


def _ns(data: Any) -> Any:
    if isinstance(data, dict):
        return _Obj(**{k: _ns(v) for k, v in data.items()})
    return data


def _check(run: RunData, exp: dict[str, Any]) -> dict[str, Any]:
    expr = exp["check"]
    label = exp.get("label", f"check {expr}")
    at = parse_at(exp.get("at", run.end - run.start), run.start, run.scenario.location.time_zone)
    t = run.start + at
    obs = run.observer_at(t) or {"rooms": {}}
    sample = run.sample_at(t) or {"rooms": {}, "devices": {}, "outdoor": {}}
    env = {
        "room": _ns(obs["rooms"]),
        "world": _ns(sample),
        "dev": lambda eid: _ns(sample["devices"].get(eid) or {}),
        "cover": lambda eid: _ns(sample.get("covers", {}).get(eid) or {}),
        "true_temp": lambda area: sample["rooms"][area]["t_air"],
        "outdoor": _ns(sample.get("outdoor") or {}),
        "true": True,
        "false": False,
        "null": None,
        "abs": abs,
        "min": min,
        "max": max,
        "round": round,
    }
    try:
        ok = bool(eval(expr, {"__builtins__": {}}, env))  # noqa: S307 - expressions come from our own scenario files
        detail = "ok" if ok else f"false at {_rel(run, t)}"
    except Exception as err:  # noqa: BLE001
        ok, detail = False, f"error: {err}"
    return {"label": f"{label} @ {_rel(run, t)}", "passed": ok, "detail": detail}


def _rel(run: RunData, t: float) -> str:
    return format_offset(t - run.start)


def _lines(metrics: dict[str, Any], warnings: list[dict[str, Any]]) -> list[str]:
    lines = []
    for area, m in metrics["rooms"].items():
        lines.append(
            f"room {area}: {m['temp_min']}..{m['temp_max']} °C, under {m['undershoot_kh']} Kh, over heat+0.5 {m['heat_overshoot_kh']} Kh, over cool {m['overshoot_kh']} Kh, in band {m['in_band_pct']}%"
            + (f", pred MAE {m['prediction_mae_30m']} K" if m.get("prediction_mae_30m") is not None else "")
        )
    for eid, m in metrics["devices"].items():
        lines.append(
            f"device {eid}: {m['commands']} cmds ({m['commands_per_hour']}/h, {m['redundant_commands']} no-op, {m['rejected_commands']} rejected), "
            f"{m['device_starts']} starts, active {m['active_h']} h, {m['electric_kwh']} kWh el"
        )
    for area, m in metrics["model"].items():
        if m["learned_alpha_per_h"] is not None:
            lines.append(
                f"model {area}: alpha learned {m['learned_alpha_per_h']} vs lumped truth {m['truth_alpha_per_h']} 1/h ({m['n_updates']} updates)"
            )
    for w in warnings:
        lines.append(f"WARNING {w['invariant']}: {w['count']}x, e.g. {w['violations'][0]['detail']}")
    return lines
