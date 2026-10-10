"""Single-file HTML report (uPlot embedded, works offline)."""

from __future__ import annotations

import html
import json
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from ..scenario.timespec import format_offset
from .load import RunData

ASSETS = Path(__file__).parent / "assets"
MAX_POINTS = 6000

CSS = """
.viz-root{color-scheme:light;--surface-1:#fcfcfb;--surface-2:#f1f0ec;--text-primary:#0b0b0b;--text-secondary:#52514e;
--grid:#e4e3de;--s1:#2a78d6;--s2:#eb6834;--s3:#1baf7a;--s4:#eda100;--muted:#8a8984;--good:#1a7f37;--bad:#c62828;--warn:#9a6700}
@media (prefers-color-scheme: dark){:root:where(:not([data-theme="light"])) .viz-root{color-scheme:dark;--surface-1:#1a1a19;--surface-2:#242423;
--text-primary:#fff;--text-secondary:#c3c2b7;--grid:#333331;--s1:#3987e5;--s2:#d95926;--s3:#199e70;--s4:#c98500;--muted:#8d8c86;--good:#4ac26b;--bad:#ff6b6b;--warn:#d4a72c}}
body{margin:0;background:var(--surface-1)}
.viz-root{font:14px/1.45 system-ui,-apple-system,Segoe UI,sans-serif;color:var(--text-primary);background:var(--surface-1);padding:16px;max-width:1400px;margin:0 auto}
h1{font-size:20px;margin:0 0 4px}h2{font-size:16px;margin:28px 0 8px}h3{font-size:14px;margin:16px 0 4px;color:var(--text-secondary)}
.sub{color:var(--text-secondary);margin-bottom:12px}
table{border-collapse:collapse;width:100%;margin:6px 0 12px;font-size:13px}
th,td{text-align:left;padding:4px 8px;border-bottom:1px solid var(--grid);vertical-align:top}
th{color:var(--text-secondary);font-weight:600}
.pass,.fail,.xfail{font-weight:600}.pass{color:var(--good)}.fail{color:var(--bad)}.xfail{color:var(--warn)}
.chart{background:var(--surface-1);margin:6px 0 14px}
.u-legend{font-size:12px;color:var(--text-secondary)}.u-legend .u-marker{border-radius:2px}
details{margin:8px 0}summary{cursor:pointer;color:var(--text-secondary)}
code{font-size:12px}
"""


def write_report(run: RunData, summary: dict[str, Any]) -> Path:
    tz = ZoneInfo(run.scenario.location.time_zone)
    data = _series(run)
    parts = [
        f"<h1>{html.escape(run.scenario.name)}</h1>",
        f"<div class='sub'>{html.escape(run.scenario.description)}</div>",
        "<div class='sub'>"
        + f"{_dt(run.start, tz)} → {_dt(run.end, tz)} ({format_offset(run.end - run.start)} simulated"
        + (f", {summary['real_seconds']} s real" if summary.get("real_seconds") else "")
        + ")"
        + (" · issues " + ", ".join(f"#{r}" for r in run.scenario.refs) if run.scenario.refs else "")
        + "</div>",
        _result_block(summary),
        _metrics_tables(summary["metrics"]),
    ]
    for area in run.scenario.rooms:
        parts.append(f"<h2>Raum {html.escape(run.scenario.rooms[area].name)} <code>{area}</code></h2>")
        parts.append(f"<h3>Temperatur (°C)</h3><div class='chart' id='temp-{area}'></div>")
        parts.append(
            f"<h3>Wärme-/Kälteleistung der Geräte (W, negativ = Kühlen)</h3><div class='chart' id='power-{area}'></div>"
        )
    parts.append(_events_table(run, tz))
    uplot_js = (ASSETS / "uPlot.iife.min.js").read_text()
    uplot_css = (ASSETS / "uPlot.min.css").read_text()
    doc = f"""<!doctype html><html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(run.scenario.name)} – RoomMind Sim</title><style>{uplot_css}{CSS}</style></head>
<body><div class="viz-root">{"".join(parts)}</div>
<script>{uplot_js}</script>
<script>const DATA={json.dumps(data, separators=(",", ":"))};const TZ={json.dumps(run.scenario.location.time_zone)};{_JS}</script>
</body></html>"""
    out = run.dir / "report.html"
    out.write_text(doc)
    return out


def _dt(epoch: float, tz: ZoneInfo) -> str:
    return datetime.fromtimestamp(epoch, tz).strftime("%Y-%m-%d %H:%M")


def _result_block(summary: dict[str, Any]) -> str:
    rows = []
    for e in summary["expectations"]:
        cls, label = (
            ("pass", "PASS") if e["passed"] else (("xfail", "XFAIL") if e.get("known_failure") else ("fail", "FAIL"))
        )
        rows.append(
            f"<tr><td class='{cls}'>{label}</td><td>{html.escape(e['label'])}</td><td>{html.escape(str(e['detail']))}</td></tr>"
        )
    for w in summary.get("warnings", []):
        rows.append(
            f"<tr><td class='xfail'>WARN</td><td>{html.escape(w['invariant'])} (default)</td>"
            f"<td>{w['count']}×, z. B. {html.escape(w['violations'][0]['detail'])}</td></tr>"
        )
    verdict = "<span class='pass'>PASS</span>" if summary["passed"] else "<span class='fail'>FAIL</span>"
    if summary.get("xfailed"):
        verdict += f" ({summary['xfailed']} bekannte Fehler)"
    for label in summary.get("unexpected_pass") or []:
        verdict += f" · XPASS: {html.escape(label)}"
    table = "<table><tr><th></th><th>Erwartung</th><th>Ergebnis</th></tr>" + "".join(rows) + "</table>" if rows else ""
    return f"<h2>Ergebnis: {verdict}</h2>{table}"


def _metrics_tables(metrics: dict[str, Any]) -> str:
    def table(title: str, rows: dict[str, dict[str, Any]]) -> str:
        if not rows:
            return ""
        keys = list(next(iter(rows.values())).keys())
        head = "".join(f"<th>{html.escape(k)}</th>" for k in keys)
        body = "".join(
            f"<tr><th><code>{html.escape(name)}</code></th>"
            + "".join(f"<td>{html.escape(str(v))}</td>" for v in m.values())
            + "</tr>"
            for name, m in rows.items()
        )
        return f"<h3>{title}</h3><table><tr><th></th>{head}</tr>{body}</table>"

    return (
        "<h2>Kennzahlen</h2>"
        + table("Räume", metrics["rooms"])
        + table("Geräte", metrics["devices"])
        + table("Thermisches Modell (RoomMind EKF vs. Simulation)", metrics["model"])
    )


def _events_table(run: RunData, tz: ZoneInfo) -> str:
    rows = []
    for e in run.events:
        t = _dt(e["t"], tz) + datetime.fromtimestamp(e["t"], tz).strftime(":%S")
        if e["type"] == "command":
            what = f"<code>{html.escape(e['entity_id'])}</code> {html.escape(e['service'])} {html.escape(json.dumps(e['data']))}"
            res = html.escape(str(e.get("result")))
        elif e["type"] == "action":
            what = f"Aktion {html.escape(e['action'])} {html.escape(json.dumps(e.get('args', {})))}"
            res = "ok" if e.get("ok") else html.escape(str(e.get("error")))
        elif e["type"] == "mark":
            what, res = f"Marke: {html.escape(e['label'])}", ""
        else:
            what, res = f"HA: {html.escape(str(e.get('what')))}", ""
        rows.append(f"<tr><td>{t}</td><td>{what}</td><td>{res}</td></tr>")
    return (
        f"<h2>Ereignisse ({len(rows)})</h2><details><summary>Kommandos, Aktionen, HA-Ereignisse anzeigen</summary>"
        f"<table><tr><th>Zeit</th><th>Was</th><th>Ergebnis</th></tr>{''.join(rows)}</table></details>"
    )


def _series(run: RunData) -> dict[str, Any]:
    samples = run.samples
    step = max(1, len(samples) // MAX_POINTS)
    picked = samples[::step]
    ts = [s["t"] for s in picked]
    out: dict[str, Any] = {"t": ts, "outdoor": [s["outdoor"]["temp"] for s in picked], "rooms": {}, "marks": []}
    obs = [run.observer_at(t) or {"rooms": {}} for t in ts]
    for area, room in run.scenario.rooms.items():
        live = [o["rooms"].get(area) or {} for o in obs]
        out["rooms"][area] = {
            "t_air": [s["rooms"][area]["t_air"] for s in picked],
            "heat": [r.get("heat_target") for r in live],
            "cool": [r.get("cool_target") for r in live],
            "pred": [r.get("predicted_temp") for r in live],
            "devices": {
                d.entity_id: [s["devices"].get(d.entity_id, {}).get("heat_w") for s in picked] for d in room.devices
            },
        }
    for e in run.events:
        if e["type"] in ("mark", "action") or (e["type"] == "ha" and e.get("what") != "provisioned"):
            label = e.get("label") or e.get("action") or e.get("what")
            out["marks"].append([e["t"], str(label)])
    return out


_JS = r"""
const css=getComputedStyle(document.querySelector('.viz-root'));
const v=n=>css.getPropertyValue(n).trim();
const fmt=new Intl.DateTimeFormat('de-DE',{timeZone:TZ,day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'});
const axis={stroke:v('--text-secondary'),grid:{stroke:v('--grid'),width:1},ticks:{stroke:v('--grid')}};
const xaxis={...axis,values:(u,vals)=>vals.map(x=>fmt.format(new Date(x*1000)))};
const marks={hooks:{drawClear:[u=>{const c=u.ctx;c.save();c.strokeStyle=v('--muted');c.setLineDash([3,3]);c.lineWidth=1;
 for(const [t] of DATA.marks){const x=u.valToPos(t,'x',true);if(x<u.bbox.left||x>u.bbox.left+u.bbox.width)continue;
 c.beginPath();c.moveTo(x,u.bbox.top);c.lineTo(x,u.bbox.top+u.bbox.height);c.stroke();}c.restore();}]}};
const sync=uPlot.sync('sim');
function mk(id,series,data){const el=document.getElementById(id);if(!el)return;
 const w=Math.max(320,el.clientWidth||900);
 new uPlot({width:w,height:260,plugins:[marks],cursor:{sync:{key:sync.key}},scales:{x:{time:false}},
  axes:[xaxis,{...axis,size:50}],series:[{value:(u,x)=>x==null?'':fmt.format(new Date(x*1000))},...series]},[DATA.t,...data],el);}
const pal=['--s1','--s2','--s3','--s4'];
for(const [area,r] of Object.entries(DATA.rooms)){
 mk('temp-'+area,[
  {label:'Raum (wahr)',stroke:v('--s1'),width:2},
  {label:'Heizziel',stroke:v('--s2'),width:2,dash:[6,4]},
  {label:'Kühlziel',stroke:v('--s3'),width:2,dash:[6,4]},
  {label:'Prognose',stroke:v('--s4'),width:1.5},
  {label:'Außen',stroke:v('--muted'),width:1.5}],
  [r.t_air,r.heat,r.cool,r.pred,DATA.outdoor]);
 const devs=Object.entries(r.devices);
 mk('power-'+area,devs.map(([e],i)=>({label:e,stroke:v(pal[i%4]),width:2})),devs.map(([,s])=>s));
}
"""
