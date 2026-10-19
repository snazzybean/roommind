# Control And Device Guide

This page explains RoomMind's control settings and related device options.

## What Priority Does

In `Settings -> Control -> Priority`, the slider balances comfort against runtime/energy use for MPC.

- Toward `Comfort`: RoomMind reacts earlier and works harder to stay close to the target temperature.
- Toward `Efficiency`: RoomMind allows more drift around the target to reduce heating/cooling runtime.

### Pre-heating

When a schedule block raises the target (for example eco 17 °C until 06:00, then 21 °C), RoomMind works out from the learned room model how long the room needs to heat up and starts early enough for the room to be warm when the block begins. Rooms whose radiators need hours to recover from a night setback start correspondingly early.

- At the default position and toward `Comfort`, pre-heating may start up to 12 hours ahead.
- Below the default, the longest pre-heat lead shrinks with the slider; at full `Efficiency` RoomMind only heats shortly before the block, as before v1.7.9. The room then reaches the comfort temperature some time after the block has started, which uses a little less energy.
- Underfloor heating uses its own pre-heating that accounts for the heat stored in the screed.
- `Simple` control mode does not pre-heat.

This setting does **not** change your schedule targets, overrides, comfort temperature, or eco temperature. It only changes how aggressively MPC tries to reach and hold those targets.

## Thermostat vs Climate Device

Both options are Home Assistant `climate.*` entities, but RoomMind treats them differently:

- `Thermostat`: a radiator thermostat / TRV style device.
- `Climate Device`: an AC, heat pump, or other climate entity used for cooling or forced-air heating.

In practice:

- Choose `Thermostat` for radiator valves and similar heating-only valve devices.
- Choose `Climate Device` for ACs, minisplits, heat pumps, and other self-contained HVAC units.

## Full Control vs Managed

An external room temperature sensor is the key split:

- `Full Control`: RoomMind uses the external sensor as the room truth and can actively shape device output.
- `Managed`: without an external room sensor, RoomMind sends target temperatures but the device mostly regulates itself using its own internal sensor.

This matters for the options below.

## Setpoint Mode: Proportional vs Direct

`Setpoint mode` is relevant for thermostat/TRV devices in `Full Control` rooms.

### Proportional

RoomMind calculates the required heating power, then sends a boosted device setpoint to achieve roughly that output.

Example:

- room target is `21°C`
- more heat is needed
- RoomMind may send `26-28°C` to the TRV to force the valve open harder

Best for:

- radiator valves / TRVs
- devices that need an exaggerated setpoint to actually deliver heat

### Direct

RoomMind sends the real target temperature and lets the device regulate itself.

Best for:

- space heaters
- pellet stoves
- devices with their own thermostat logic that should stay in control internally

#### Setpoint offset

Some devices measure the room differently than your room sensor, for example an AC mounted near the floor that cools its own sensor. With `Direct` and an external room sensor you can set a `Setpoint offset` (-5 to +5 °C, step 0.5, default 0). It is added to the room target before the target is sent to the device, for heating and cooling alike.

- Device reads **colder** than the room: use a **negative** value.
- Device reads **warmer** than the room: use a **positive** value.

Example: the room target is 24°C. While cooling, the device thinks the room is 2° colder than it is and switches off too early. Set the offset to `-2`: the device receives 22°C and keeps running until the room is really at 24°C.

The offset is applied before the device limits (`min_temp`/`max_temp`) and the step rounding, and it is kept for the `Setback` idle action. It has no effect in `Proportional` mode. The field is only offered in rooms with an external room sensor, because Managed rooms have no reference to correct against; an old value stays ignored there. On Fahrenheit systems the field is shown in °F.

#### Learned sensor offset (ACs)

An AC regulates on the sensor in its indoor unit. A wall unit under the ceiling often reads the warm layer: warmer than the room sensor while it runs, and warmer still once it stops. RoomMind learns this offset per AC from the device's `current_temperature`, separately for heating, cooling and idle, while the device is switched on and reports that state in `hvac_action` (readings from the first 4 minutes after a start or stop are skipped; a device that is off, or in fan or dry mode, teaches nothing). Once an offset has 10 readings, it is applied in steps of 0.5 °C (an offset below 0.25 °C changes nothing, and the applied step only moves when the learned value has moved clearly), and an AC in `Proportional` mode gets its setpoints in its own frame: the proportional heating and cooling setpoint and the setpoint kept during the compressor min-run use the heating or cooling offset, and the `Setback` idle setpoint uses the idle offset. The device then stops and restarts where the room, not its own sensor, is at the intended temperature.

This only applies in rooms with an external room sensor and to devices that report `hvac_action`. `Direct` devices keep the offset you set yourself. Offsets beyond ±4 °C are ignored as a misplaced or broken sensor. The learned values are in the diagnostics download (`ac_head_offsets`).

#### Upper device limit

In `Proportional` mode the boosted heating setpoint stays one step (`target_temp_step`, 0.5 °C if the device reports none) below the device's `max_temp`, and never below the room target. Some integrations reject exactly their own `max_temp`, which made the Dyson Heat/Cool purifier ignore the 37°C setpoint. The cooling floor (`min_temp`) is unchanged.

## Direct Valve Control (TRVs)

Some TRVs let Home Assistant set the valve opening itself through `number` entities, for example the SONOFF TRVZB in Zigbee2MQTT (`valve_opening_degree` and `valve_closing_degree`). With a setpoint, a TRV opens its valve fully as soon as it wants heat, so the radiator runs at full power in short bursts. With direct valve control RoomMind holds the valve at the opening the room needs, for example 30 %, for as long as it is needed.

To use it, open the TRV in the room's device list and pick the opening degree entity; RoomMind fills in the closing degree entity of the same device when it finds one. Both are needed. The fields are only shown in rooms with an external room sensor, for TRVs whose device has `number` entities (valve-like ones are offered first).

How it behaves:

- While heating, RoomMind sets the opening degree to the heating power and the closing degree to `100 - opening`, so the valve stays at that position whatever the TRV's own controller decides. The TRV keeps getting its proportional setpoint as before. The setpoint mode does not apply to these TRVs.
- In a room that heats only through TRVs with direct valve control (no heat-capable AC, no underfloor heating), a running room keeps heating at the target with the power that holds it there, instead of stopping and restarting below it. The opening is the share of full heating power the learned room model needs to hold the target (losses minus sun and occupancy), plus 100 % per 1 °C below the target; above the target it drops until the valve closes. A new run still starts only below the start hysteresis, and pre-heating ahead of a schedule block works as for other TRVs. The heating power shown in the room is the opening RoomMind computes; the valve follows it within the limits below.
- To spare battery and motor noise, a new position goes out only if it differs by at least 5 % and at the earliest 10 minutes after the last move; a changed room target goes out at once.
- During a boiler min-run hold (compressor group) the valve runs at 15 % right away.
- When the room stops heating, RoomMind sets both degrees back to 100 % (the device default) and the configured idle action switches the TRV off as usual.
- Both degrees also go back to 100 % when you clear the fields, remove the TRV or the room, switch climate control off, reload or remove the integration, or the room has no external sensor (`Managed` mode). When RoomMind lets go of a heating TRV this way, the TRV also gets the room target as its setpoint, so it works like a normal thermostat again instead of heating on RoomMind's raised setpoint. Degrees you change by hand afterwards stay as you set them until the next restart or reload; to set them yourself for good, clear the fields. While RoomMind controls the valve, a limit you set on the degrees yourself (for example for hydraulic balancing) is overwritten: RoomMind uses the full range.
- In such a room the valve closes at the latest 0.5 °C above the target. In mixed rooms the valve follows the heating power of the normal on/off rules.
- During the first days, while the room model learns, RoomMind controls the room with simple on/off rules and the valve opens fully when heating.

A valve does not deliver heat in proportion to its opening: many radiators give most of their output at a small opening. RoomMind learns the room's response at the openings it actually uses.

## Idle Behavior: Off, Fan Only, Setback

`When idle` applies to `Climate Device` entries.

### Turn off

RoomMind turns the device off, or falls back to the device's minimum/off-like behavior if true off is not supported.

### Fan only

RoomMind keeps the device running in fan mode without active heating/cooling.

Useful when you want:

- air circulation
- less harsh on/off transitions

### Setback

RoomMind keeps the current HVAC mode active, but moves the target away from the room target:

- heating setback = `heat target - 2°C`
- cooling setback = `cool target + 2°C`

A `Direct` device's own offset and, for ACs, the learned idle sensor offset (see [Learned sensor offset](#learned-sensor-offset-acs)) are added to it.

This lets the device back off instead of shutting off completely, so short pauses between runs don't turn into off/on cycles.

Long pauses end in off: once the room has had no heating or cooling demand for an hour, and RoomMind's plan expects no run in the device's mode for the next hour, the device is turned off. When demand returns, RoomMind switches it back on as usual. This needs the predictive control (Full Control with an external sensor and a trained model). In Managed Mode, with `Simple` control, or while the model is still learning, the setback stays until the next run.

Important:

- the setback offset is currently fixed at `2°C`
- it is **not configurable** in the current UI

## Idle Behavior for Thermostats: Off, Low

`When idle` also applies to `Thermostat` / TRV entries, with different options.

### Turn off

RoomMind sends the TRV to its `off` state.

### Low

RoomMind keeps the TRV in its current heating mode but lowers the setpoint to the device's minimum temperature.

Useful for battery-powered Zigbee TRVs that enter deep sleep when set to `off` and then stop reacting to commands. `Low` keeps the valve responsive while effectively stopping heating.

## Evaporator Drying

`Settings -> Evaporator drying` (with a per-device override in `Devices`) keeps an AC's indoor fan running for a while after cooling stops, before the unit really switches off.

Drying the evaporator coil this way cuts down on biofilm buildup and a musty smell on the next cooling start. It is off by default.

### Turning it on

- Enable it globally in `Settings -> Evaporator drying`.
- Or override a single device in `Devices`: `Use global setting`, `Always on`, or `Always off`. Only `Climate Device` / AC entries offer this; TRVs have no evaporator coil.

Drying time, the minimum cooling time before a run is worth it, an optional drain delay, drying mode (`fan_only` or `dry`), and fan speed are all configurable, both globally and per device. A device left on its default values falls back to the global setting.

### While it runs

- A returning cooling demand cancels the run immediately and the AC goes straight back to cooling.
- A returning heating demand cancels it too, and resets the tracked wetness for that room's ACs.
- A running or draining device shows a badge with the remaining time on the room's status.

### Relation to `When idle`

If a drain delay is configured, a run normally holds the device off first so condensate can drain, then switches to the fan. With `When idle` set to `Setback` the device is never actually off, so the drain step is skipped and the run starts directly in the fan phase.

### Relation to an explicit shutdown

An explicit shutdown, `Action when schedule is off` or `Action when away` set to `Turn off devices`, overrides `When idle` (described in the next section) so a device cannot stay fanning or set back indefinitely. Evaporator drying is different: an explicit shutdown does not block it. A run can start fresh or keep going, and always finishes normally, before the device goes off.

## When "Turn off devices" Overrides `When idle`

`When idle` describes what a device should do while the room simply has no heating or cooling demand. It does **not** apply when you explicitly shut a room down via:

- `Settings → Control → Action when schedule is off` set to `Turn off devices`
- `Settings → Presence → Action when away` set to `Turn off devices`

In those cases RoomMind turns the devices off even if `When idle` is set to `Fan only` or `Setback`. Otherwise an AC would keep circulating air after the schedule ended.

The single exception is `Low` on thermostats: it stays active because the affected TRVs stop responding after being set to `off`. Lowering the setpoint to the device minimum already stops all heat output.

## Smart Source Selection

`Smart source selection` only appears when a room has:

- at least one `Thermostat` / TRV
- at least one `Climate Device` / AC
- an external temperature sensor

In that case RoomMind can decide which source should heat:

- TRV / boiler side
- AC / heat pump side
- or both, when the gap is large

It uses temperature gap and outdoor conditions to make that choice.
