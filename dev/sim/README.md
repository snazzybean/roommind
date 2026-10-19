# RoomMind simulation environment (`dev/sim`)

A real Home Assistant instance with a simulated house and a controllable clock, for
reproducing issues and verifying fixes by behaviour instead of mocks alone. Not part of
the integration: HACS ships only `custom_components/roommind`.

- **One engine.** Every simulation is a real HA process (default 2026.10) with the
  RoomMind code of the checkout you call `sim` from. A virtual clock is installed before
  HA is imported, so the same instance can run in **turbo** (jump to the next timer
  whenever the event loop is idle), **scaled** (time-lapse, 1 = real time) or **paused**.
  14 simulated days of a 4-room flat with MPC take about 3 minutes.
- **A house, not mocks.** `simhome` (a custom integration) exposes climate devices,
  sensors, windows, covers, weather with forecasts and people's phones. Behind it runs a
  two-node thermal model per room (air + building mass, radiator water / screed slab as
  emitter nodes), sun position and cloud cover, humidity, people with weekly plans.
- **Device quirks from the issue tracker**: return-air sensor offsets and internal
  hysteresis (#436), rejected values (#396, #162), duty cycle (#317), IR units without
  feedback (#416), state lag, side effects of command sequences (#337), unavailable
  after restart (#437, #183), °F and whole-degree rounding (#22, #277).
- **Oracles.** Metrics (comfort, energy, starts, commands/h, EKF vs ground truth),
  invariants (physical compressor min run, no target, outdoor gate, window pause, ...)
  and per-scenario expectations give a pass/fail exit code plus an HTML report.

## Quick start

```bash
dev/sim/bin/sim run smoke-ac-compressor        # batch run in turbo, prints PASS/FAIL + report path
dev/sim/bin/sim suite -j 4                     # whole library
dev/sim/bin/sim up main --scenario baseline-radiator-house --set start=now-3d --catch-up
dev/sim/bin/sim shot main --path /roommind/room/wohnzimmer --viewport mobile
dev/sim/bin/sim down main
```

The first call creates a Home Assistant venv with `uv`. Runtime data (venvs, instances,
runs, imports, browsers) lives in `$ROOMMIND_SIM_HOME` (default `~/.roommind-sim`),
never in the repository.

## Commands

| Command | Purpose |
|---|---|
| `sim run <scenario> [--set k=v] [--until 3d] [--roommind-src v1.7.7]` | Fresh instance, turbo to the end, evaluate. Exit 0 pass / 1 fail / 2 invalid scenario / 3 HA crashed |
| `sim suite [-j N] [--tag t] [--roommind-src ref]` | All scenarios in `scenarios/` |
| `sim compare <run-a> <run-b> [--timeline]` | Metric diff, e.g. a git ref against your working tree; `--timeline` also checks record by record (determinism) |
| `sim report [run]` | Re-evaluate a run (`last` by default) |
| `sim up [name] --scenario X [--catch-up] [--speed 60] [--paused] [--from-run R] [--ttl 2h]` | Live instance with UI, reachable on the LAN without password (trusted networks) |
| `sim clock <name> ff 6h \| speed 60 \| pause \| realtime \| until <ISO>` | Control the clock of a live instance |
| `sim do <name> <action> k=v ...` | Run a timeline action now (open a window, person leaves, ...) |
| `sim ws <name> <type> [json]` | Any WebSocket command, e.g. `roommind/rooms/list` |
| `sim status`, `sim world`, `sim logs [-f]`, `sim ps`, `sim down [--rm]` | Inspect and manage |
| `sim shot <name> [--path] [--viewport desktop\|mobile\|tablet] [--dark] [--lang de] [--do click:Text]` | Screenshot with Playwright; prints browser console and HA errors |
| `sim import <diagnostics.json> [--history roommind_room_*.csv] [--mode closed\|replay]` | Turn a reporter's export into a scenario (see below) |
| `sim venv add\|list\|prune <ha-version>` | Additional HA versions, e.g. betas: `sim up --ha 2026.11.0b0` |
| `sim prune [--keep 20]` | Delete old runs and screenshots (never running or < 6 h old ones) |

`--roommind-src` takes a path to another checkout or any git ref; refs are exported
once into `$ROOMMIND_SIM_HOME/src/`. Called through a symlink from inside a git
worktree, `bin/sim` switches to that worktree's own copy, so parallel worktrees always
test their own code.

## Scenarios

YAML in `scenarios/`, profiles in `profiles/{devices,buildings,sensors,covers,people,weather}`.
A scenario describes location, start/duration, weather, rooms with devices and sensors,
helpers (schedules, input_boolean/number), RoomMind settings and room configs (sent
through RoomMind's real WebSocket handlers, so validation is identical to the panel),
a timeline of events and expectations:

```yaml
name: my-check
extends: smoke-ac-compressor        # optional base scenario
start: 2026-01-12T00:00             # or now-3d (ends at real time, good for the UI)
duration: 3d
timeline:
  - {at: "+1d07h", do: window.open, entity_id: binary_sensor.wohnzimmer_fenster, for: 15m}
  - {at: "+2d", do: roommind.ws, type: roommind/override/set, area_id: wohnzimmer, override_type: boost, duration: 2}
  - {at: "+2d12h", do: ha.restart}
expect:
  - {invariant: min_run_respected}
  - {metric: device.commands_per_hour, entity_id: climate.wohnzimmer_ac, max: 4}
  - {check: "room.wohnzimmer.override_active == true", at: "+2d00h10m"}
known_failure: "candidate: ..."    # failing expectations count as XFAIL
```

`extends:` merges mappings recursively and replaces lists; `key+: [...]` appends to the
inherited list, `key-: ~` removes an inherited key.

Actions: `window.open/close`, `person.leave/arrive`, `occupancy.set`, `cover.manual`,
`device.manual`, `entity.unavailable/available/remove`, `weather.set`,
`weather.forecast_unavailable`, `humidity.event`, `roommind.ws`, `ha.service`,
`ha.restart`, `roommind.reload`, `sim.param`, `clock.speed/pause`, `mark`.

Invariants: `min_run_respected` (physical compressor), `min_run_commanded`,
`min_run_hold_keeps_setpoint` (#436: no setpoint cut while the min run holds a unit),
`min_off_respected`, `target_never_empty`, `no_cooling_below_outdoor_min`,
`setpoints_within_device_range`, `no_full_cooling_at_target` (#450: no lowest AC
setpoint once the room is at its cool target), `no_rejected_commands`, `window_open_pauses`,
`no_heat_and_cool_same_group`, `no_commands_when_climate_off`, `max_commands_per_hour`.
Check expressions see `room.<area>.<live field>`, `dev('<entity_id>')`,
`cover('<entity_id>')`, `true_temp('<area>')` and `outdoor`.

## Realism defaults

Defaults follow typical installations; scenarios switch them off where a test needs a
clean signal (with a comment why).

| Default | Where | Switch |
|---|---|---|
| Weather-compensated supply: straight heating curve from `supply_foot_c` (25 °C, underfloor 24) at +20 °C to `supply_temp_c` at `design_outdoor_c` | `generic_trv`, `generic_boiler`, `ufh_zone` params | `heating_curve: false` = fixed `supply_temp_c` |
| Radiator output ∝ excess temperature^1.3 (EN 442), rated output unchanged at the design point | `generic_trv` | `radiator_exponent` |
| Forecasts drift from the weather with lead time (temperature ~1.4 K RMS on day 1, ~1.8 K on day 2; cloud cover ±15-20 %), the next hour is almost exact | `weather:` spec | `forecast_error: false` (perfect), or a dict with `temp_c`, `temp_c_per_day`, `cloud_pct`, `cloud_pct_per_day`, `ramp_h` |
| Air-source units frost up while heating in humid air between -20 and +6 °C and defrost for `defrost_s` (300 s, no heat) after at least `defrost_interval_s` (2700 s); `hvac_action` meanwhile is `defrost_action` (`heating`) | `generic_split_ac`, `ecobee` | `defrost_interval_s: 0` |
| ECO/quiet modes cap a split AC's output | `generic_split_ac` | `max_output` (1.0 = off) |
| Zigbee sensor reporting in 0.2 K steps | profile `sonoff_snzb02d` (opt-in) | |
| TRV valve flow linear in the valve position | `generic_trv` | `valve_flow_exponent` (< 1 = concave, low valve authority), `valve_dead_zone` (no flow below it) |
| Direct valve control: `number.<trv object_id>_valve_opening_degree` / `_valve_closing_degree` (0-100 %, default 100 = the TRV's own control; open position = opening, closed position = 100 - closing, also in `off`) | capability `valve_numbers` (`sonoff_trvzb`) | metrics `device.valve_travel_per_day` (full strokes), `device.valve_commands_per_hour` |

The heating curve was checked against a real radiator room in October (rate 20-30 min into a
run 0.75-0.8 K/h, real 0.78-0.92; before: 1.8-2.0). Forecast error sizes, defrost timing and
`defrost_action` are assumptions, not fitted. Runs before these defaults (2f43c4c heating,
829f34e forecasts, ea185c0 AC heating) are no valid "before" for runs after them; re-run with
`--roommind-src`.

## Extending

- **New device**: a YAML file in `profiles/devices/` (`extends:` an existing one,
  override `capabilities`, `params`, `quirks`).
- **New quirk**: a class in `roommind_sim/devices/quirks.py` with `@register("name")`
  and the hooks `before_command`, `after_command`, `on_step`, `transform_attributes`,
  `state_override`.
- **New action**: `World.apply_action` (house) or `ha_component/simhome/actions.py` (HA).
- **New invariant**: a function in `roommind_sim/analysis/invariants.py`, added to `INVARIANTS`.

## Importing a reporter's setup

`sim import` reads a RoomMind diagnostics export (schema v2 adds device
capabilities, referenced entity states, schedule blocks, the full EKF state and 48 h of
history; older exports work with more assumptions) and writes a scenario to
`$ROOMMIND_SIM_HOME/imports/<name>/`, never into the repository.

- `--mode closed` starts at the export time with the reporter's temperatures, EKF state
  and history, then simulates on. Use it to check a fix against the reporter's setup.
- `--mode replay` replays the recorded room and outdoor temperatures exactly over the
  history period; devices are simulated but cannot change the room. Use it to reproduce
  a decision bug with identical inputs.

Everything the export does not contain (window orientation, device behaviour, presence
plans) is guessed and listed under `assumptions:` in the generated scenario.

## Reproducibility

A batch run is deterministic: the same scenario, `seed` and code give identical
timelines (commands, samples, observer) and therefore identical metrics, so a
before/after comparison shows only the effect of the change. `sim compare A B --timeline`
checks this and prints the first differing record (exit 1); `tests/test_determinism.py`
runs one simulated day twice.

- HA staggers its update coordinators and time trackers by a random 0.05–0.5 s
  (`random.randint`). `boot.seed_randint` derives these draws from the scenario `seed`,
  one generator per calling module. `--set seed=N` changes them together with weather
  and sensor noise, which is the way to look at the spread on purpose.
- Samples and timeline actions first step the physics to the current instant. asyncio
  orders timers due at the same instant by heap shape, so otherwise a sample saw the
  previous physics step on some runs and the current one on others.
- An in-run `ha.restart` in turbo resumes after a fixed 5 s of virtual downtime
  (`boot.RESTART_DOWNTIME_S`); the shutdown runs in real time and used to shift
  everything after the restart by a few milliseconds. A shutdown that takes longer
  prints a warning and stays unreproducible.
- Not reproducible: live instances in scaled or real time, the shutdown after the end of
  a batch run (real time, ignored by the check) and runs with `--recorder` (not checked).
  Changed RoomMind code may reorder other timers due at the same instant; that is part of
  its effect, not noise.

## Limits

- The simulation reproduces what is known about devices; it cannot discover unknown
  firmware behaviour.
- Physics parameters of imported setups are fitted to the learned EKF loss rate, not
  measured.
- In scaled mode the browser's own clock differs from the simulated one; `sim shot`
  aligns it, a phone looking at a live instance does not.
- Live instances accept anyone on the local /24 network without a password. They contain
  only simulated devices; stop them with `sim down`.

## Housekeeping

- Live instances stop by themselves after `--ttl` (default 2 h): via systemd
  `RuntimeMaxSec` and, independently, a real-time alarm inside the process.
- Batch runs abort after `--max-real` (default 2 h) or when the simulated clock stops
  moving for 5 minutes.
- After every batch run, finished runs older than 3 days are deleted, then the oldest
  finished runs while all runs exceed 2 GB; screenshots older than 3 days go too.
  Running runs and runs younger than 6 hours are never touched.

## CPU cap

Every batch run keeps one core busy, so several agents running suites at once can
saturate the machine. If a systemd slice `roommind-heavy.slice` exists (name via
`ROOMMIND_CPU_SLICE`), `bin/sim` and `dev/check` re-run themselves in it as root, and
live instances are started in it; all of them then share the slice's `CPUQuota`.
Runs only get slower, batch results stay the same (see Reproducibility). Without the
slice nothing changes.

```ini
# /etc/systemd/system/roommind-heavy.slice, then systemctl daemon-reload
[Slice]
CPUQuota=400%
```

## Tests

```bash
$ROOMMIND_SIM_HOME/venvs/ha-2026.10.0/bin/python -m pytest dev/sim/tests -q
```
