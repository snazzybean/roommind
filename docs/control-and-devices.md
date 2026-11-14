# Control And Device Guide

This page explains RoomMind's control settings and related device options.

## What Priority Does

In `Settings -> Control -> Priority`, the slider balances comfort against runtime/energy use for MPC.

- Toward `Comfort`: RoomMind reacts earlier and works harder to stay close to the target temperature.
- Toward `Efficiency`: RoomMind allows more drift around the target to reduce heating/cooling runtime.

### Pre-heating

When a schedule block raises the target (for example eco 17 °C until 06:00, then 21 °C), RoomMind works out from the learned room model how long the room needs to heat up and starts early enough for the room to be warm when the block begins. Rooms whose radiators need hours to recover from a night setback start correspondingly early.

- At the default position and toward `Comfort`, pre-heating may start up to 12 hours ahead.
- Below the default, the longest pre-heat lead shrinks with the slider; at full `Efficiency` RoomMind only heats shortly before the block, as before v1.7.9. The room then reaches the comfort temperature some time after the block has started, which uses a little less energy. The line under the slider shows the current limit in hours.
- Each room has its own switch `Pre-heat before schedule blocks` in the schedule section. Turned off, that room only heats shortly before a block, whatever the slider says, for example a bedroom that should not heat up during the night. The same applies to the end of a vacation or an override. The switch is shown for rooms with their own temperature sensor in `Intelligent (MPC)` mode; underfloor heating keeps its own pre-heating unless an orchestrated AC heats the room.
- Underfloor heating uses its own pre-heating that accounts for the heat stored in the screed.
- Radiator rooms learn how much heat their radiators release after a run stops, and how slowly (from the room sensor in the hour after each undisturbed run). A run whose stored heat carries the room to the target stops early, also during pre-heating. Where a short run is enough, the pre-heat is a short run started as late as it still reaches the block, so less of the stored heat arrives after the block. Diagnostics show the learned values as `residual_scale` and `residual_decay_minutes`.
- `Simple` control mode does not pre-heat.

This setting does **not** change your schedule targets, overrides, comfort temperature, or eco temperature. It only changes how aggressively MPC tries to reach and hold those targets.

## Thermostat vs Climate Device

Both options are Home Assistant `climate.*` entities, but RoomMind treats them differently:

- `Thermostat`: a radiator thermostat / TRV style device.
- `Climate Device`: an AC, heat pump, or other climate entity used for cooling or forced-air heating.

In practice:

- Choose `Thermostat` for radiator valves and similar heating-only valve devices.
- Choose `Climate Device` for ACs, minisplits, heat pumps, and other self-contained HVAC units.

A climate device that can heat heats along with the thermostats in `Auto`. In `Heat only` it stays off when the room also has a thermostat, unless `Smart source selection` is on. In a room with only climate devices, `Heat only` heats with them.

## Full Control vs Managed

An external room temperature sensor is the key split:

- `Full Control`: RoomMind uses the external sensor as the room truth and can actively shape device output.
- `Managed`: without an external room sensor, RoomMind sends target temperatures but the device mostly regulates itself using its own internal sensor.

This matters for the options below.

## Changes Made on the Device

RoomMind writes its setpoint to every device it controls and sets it again when the device reports something else, so a turn of the TRV dial is undone with RoomMind's next command (usually within 30 seconds; a TRV that RoomMind switched off keeps the value until its next run). With `Take over changes made on the device` (schedule settings of the room, off by default) such a change becomes the room target instead, until the next change of the active schedule, like a temperature set on the room climate entity. Without a schedule it holds until you end the override; if the schedule helper cannot be read at that moment, for 4 hours. A running override, also one with a duration, is replaced and then holds until the next schedule change as well.

- The value set on the device is the new target, also in `Full Control`, where the device showed RoomMind's boost or idle setpoint before (e.g. 29.5 °C while heating, or 5 °C while idle). A direct setpoint offset is taken off again. Afterwards the device shows RoomMind's setpoint for the new target, not the value turned in.
- ACs count too: a TRV and an AC in heating mode change the heating side, an AC in cooling or dry mode the cooling side, a range change on a `heat_cool` device both sides.
- Only devices that report their setpoint to Home Assistant can be followed. IR devices without state feedback cannot.
- Thermostats always change the heating side. An AC with a single setpoint in `heat_cool`/`auto` changes the side it reports heating or cooling for; when it reports neither, or is off or in fan mode, it counts only in heat-only or cool-only rooms (for the side the room uses). A change on a side the room does not use (e.g. a thermostat in a cool-only room) is ignored.
- RoomMind cannot see who changed a setpoint. A value it sent itself and the device has not shown yet counts as RoomMind's, as does a setpoint the device reports while RoomMind switches its mode (until the device shows that mode and up to a minute after, at most 5 minutes after the command). A mode picked on the device itself does not count as such a switch. Everything else counts as a change on the device, also a device's own weekly program, its frost or window protection setting a setpoint, or an automation writing to the device. Leave the option off for such devices.
- Like every override, the taken-over target outranks vacation, presence and an empty room, and lifts the outdoor temperature limits while it lasts.
- After a device was unavailable, or after a room was not controlled for a while (e.g. its area was deleted), the first setpoint it reports is not taken over.
- While climate control is off for the room or globally, nothing is taken over: RoomMind sends no commands then, the device keeps whatever is set on it.

## Setpoint Mode: Proportional vs Direct

`Setpoint mode` is relevant for thermostat/TRV devices in `Full Control` rooms.

### Proportional

RoomMind decides from your room sensor when the room needs heat. While heating, the TRV gets a raised setpoint, in most cases close to its maximum (around `30°C`); a TRV opens its valve fully anyway once its setpoint is a little above its own reading. Once the room sensor shows the target, RoomMind switches the TRV off (or to whatever `When idle` says). So the radiator runs at full power in runs rather than at a steady partial output, and the TRV setpoint does not tell how much heat the room needs. If something else reads the TRV setpoint, for example an automation that sets the flow temperature, use `Direct` for that TRV, or read the valve opening or the `hvac_action` of the room climate entity instead. For a steady partial opening, see [Direct Valve Control](#direct-valve-control-trvs).

Best for:

- radiator valves / TRVs
- devices that need an exaggerated setpoint to actually deliver heat

### Direct

RoomMind sends the real target temperature and lets the device regulate itself.

Best for:

- space heaters
- pellet stoves
- devices with their own thermostat logic that should stay in control internally

An AC in `Direct` mode decides itself when its compressor runs. Once a run has started, RoomMind leaves it to the AC to end it, as long as the AC reports that it is still heating or cooling (`hvac_action`): RoomMind does not switch it off just because the room has reached the target, only when the room is 0.5 °C past it or, in `Auto` rooms, reaches the target of the other side. This needs every AC in the room set to `Direct` and, for heating, no TRVs in the room. ACs that report no `hvac_action` are switched off at the target after the minimum run time, as before.

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

To use it, open the TRV in the room's device list and switch on `Direct valve control`. RoomMind finds the opening and closing degree entities of the device itself. Only if it cannot recognise them (for example after renaming the entities), you pick both by hand instead of the switch. The option is only shown in rooms with an external room sensor, for TRVs whose device has `number` entities.

The SONOFF TRV-ZBT (gen2) names its two values differently in Zigbee2MQTT: `heating_valve_position` and `idle_valve_position`. Its second value is not a closing degree but the valve opening while the TRV does not heat. Pick `heating_valve_position` as the opening degree and `idle_valve_position` as the second value, then set `Second value is` to `Opening while idle`. Left at `Closing degree`, the valve stays open whenever the room needs no heat.

How it behaves:

- While heating, RoomMind sets the opening degree to the heating power and the closing degree to `100 - opening` (with `Opening while idle`: both to the heating power), so the valve stays at that position whatever the TRV's own controller decides. The TRV keeps getting its proportional setpoint as before. The setpoint mode does not apply to these TRVs.
- In a room that heats only through TRVs with direct valve control (no heat-capable AC that heats along, no underfloor heating), a running room keeps heating at the target with the power that holds it there, instead of stopping and restarting below it. The opening is the share of full heating power the learned room model needs to hold the target (losses minus sun and occupancy), plus 100 % per 1 °C below the target; above the target it drops until the valve closes. A new run still starts only below the start hysteresis, and pre-heating ahead of a schedule block works as for other TRVs. The heating power shown in the room is the opening RoomMind computes; the valve follows it within the limits below.
- To spare battery and motor noise, a new position goes out only if it differs by at least 5 % and at the earliest 10 minutes after the last move; a changed room target goes out at once.
- During a boiler min-run hold (compressor group) the valve runs at 15 % right away.
- When the room stops heating, RoomMind hands the valve back to the TRV: both degrees to 100 % (the device default; with `Opening while idle`: opening 100 %, idle position 0 %, so the valve closes while the TRV does not heat) and the configured idle action switches the TRV off as usual.
- The valve is also handed back this way when you switch it off (or clear the fields), remove the TRV or the room, switch climate control off, reload or remove the integration, or the room has no external sensor (`Managed` mode). When RoomMind lets go of a heating TRV this way, the TRV also gets the room target as its setpoint, so it works like a normal thermostat again instead of heating on RoomMind's raised setpoint. Degrees you change by hand afterwards stay as you set them until the next restart or reload; to set them yourself for good, switch direct valve control off. While RoomMind controls the valve, a limit you set on the degrees yourself (for example for hydraulic balancing) is overwritten: RoomMind uses the full range.
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

By default the device stays on in setback however long the pause is. With **Turn off after an hour without demand** (below the idle setting) long pauses end in off: once the room has had no heating or cooling demand for an hour, and RoomMind's plan expects no run in the device's mode for the next hour, the device is turned off. When demand returns, RoomMind switches it back on as usual. This needs the predictive control (Full Control with an external sensor and a trained model). In Managed Mode, with `Simple` control, or while the model is still learning, the setback stays until the next run.

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
