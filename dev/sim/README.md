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
| `sim compare <run-a> <run-b>` | Metric diff, e.g. a git ref against your working tree |
| `sim report [run]` | Re-evaluate a run (`last` by default) |
| `sim up [name] --scenario X [--catch-up] [--speed 60] [--paused] [--from-run R] [--ttl 4h]` | Live instance with UI, reachable on the LAN without password (trusted networks) |
| `sim clock <name> ff 6h \| speed 60 \| pause \| realtime \| until <ISO>` | Control the clock of a live instance |
| `sim do <name> <action> k=v ...` | Run a timeline action now (open a window, person leaves, ...) |
| `sim ws <name> <type> [json]` | Any WebSocket command, e.g. `roommind/rooms/list` |
| `sim status`, `sim world`, `sim logs [-f]`, `sim ps`, `sim down [--rm]` | Inspect and manage |
| `sim shot <name> [--path] [--viewport desktop\|mobile\|tablet] [--dark] [--lang de] [--do click:Text]` | Screenshot with Playwright; prints browser console and HA errors |
| `sim import <diagnostics.json> [--history roommind_room_*.csv] [--mode closed\|replay]` | Turn a reporter's export into a scenario (see below) |
| `sim venv add\|list\|prune <ha-version>` | Additional HA versions, e.g. betas: `sim up --ha 2026.11.0b0` |
| `sim prune [--keep 20]` | Delete old runs and screenshots |

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

Actions: `window.open/close`, `person.leave/arrive`, `occupancy.set`, `cover.manual`,
`device.manual`, `entity.unavailable/available/remove`, `weather.set`,
`weather.forecast_unavailable`, `humidity.event`, `roommind.ws`, `ha.service`,
`ha.restart`, `roommind.reload`, `sim.param`, `clock.speed/pause`, `mark`.

Invariants: `min_run_respected` (physical compressor), `min_run_commanded`,
`min_off_respected`, `target_never_empty`, `no_cooling_below_outdoor_min`,
`setpoints_within_device_range`, `no_rejected_commands`, `window_open_pauses`,
`no_heat_and_cool_same_group`, `no_commands_when_climate_off`, `max_commands_per_hour`.
Check expressions see `room.<area>.<live field>`, `dev('<entity_id>')`,
`cover('<entity_id>')`, `true_temp('<area>')` and `outdoor`.

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

## Limits

- The simulation reproduces what is known about devices; it cannot discover unknown
  firmware behaviour.
- Physics parameters of imported setups are fitted to the learned EKF loss rate, not
  measured.
- In scaled mode the browser's own clock differs from the simulated one; `sim shot`
  aligns it, a phone looking at a live instance does not.
- Live instances accept anyone on the local /24 network without a password. They contain
  only simulated devices; stop them with `sim down` (they also stop after `--ttl`).

## Tests

```bash
$ROOMMIND_SIM_HOME/venvs/ha-2026.10.0/bin/python -m pytest dev/sim/tests -q
```
