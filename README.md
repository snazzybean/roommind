# RoomMind

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2024.1%2B-blue.svg)](https://www.home-assistant.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Tests](https://github.com/snazzybean/roommind/actions/workflows/ci.yml/badge.svg)](https://github.com/snazzybean/roommind/actions/workflows/ci.yml)
![Coverage](https://raw.githubusercontent.com/snazzybean/roommind/python-coverage-comment-action-data/badge.svg)

[![Open your Home Assistant instance and open RoomMind inside HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=snazzybean&repository=roommind&category=integration)

**Intelligent room climate control for Home Assistant** — self-learning thermal model, proportional valve control, and a dedicated management panel.

---

## Features

- **Self-Learning Climate Control** — MPC (Model Predictive Control) with per-room thermal model that learns your home's heating/cooling behavior over time. Automatic fallback to simple on/off control while learning.
- **Proportional Valve Control** — TRVs receive calculated setpoints instead of simple on/off, enabling smoother temperature regulation with less oscillation.
- **Solar Gain Awareness** — Estimates solar irradiance from sun position and weather data. The model learns each room's solar response and reduces heating when sun is expected.
- **Multi-Scheduler** — Multiple schedule entities per room with selector switching via `input_boolean` or `input_number`.
- **Manual Override** — Boost, eco, or custom temperature with configurable duration and instant UI feedback.
- **Presence-Based Scheduling** — Link schedules to `person.*`, `device_tracker.*`, `binary_sensor.*`, or `input_boolean.*` entities. A room's comfort schedule only applies when assigned persons are home — otherwise eco temperature is used.
- **Vacation Mode** — Global setback temperature with end date for all rooms.
- **Window/Door Pause** — Automatically pauses climate control when windows or doors are open, with configurable delays.
- **Mold Risk Detection & Prevention** — Science-based mold risk assessment using surface humidity estimation (DIN 4108-2). Configurable notifications and automatic temperature raise to prevent mold growth.
- **Valve Protection** — Periodic cycling of idle TRV valves to prevent seizing and calcification.
- **Analytics Dashboard** — Temperature charts with heating power, solar irradiance, and model predictions over 24h to 90 days.
- **Two Operating Modes** — Full Control (RoomMind decides heating/cooling) or Managed Mode (device self-regulates).
- **Mobile Ready** — Responsive layout with HA-native toolbar for the iOS/Android companion app.
- **Multilingual** — English and German, auto-detected from your HA language setting.

---

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Click the three-dot menu → **Custom repositories**
3. Add `https://github.com/snazzybean/roommind` as an **Integration**
4. Search for "RoomMind" and install it
5. Restart Home Assistant
6. Go to **Settings → Devices & Services → Add Integration → RoomMind**

### Manual

1. Copy the `custom_components/roommind/` folder to your `config/custom_components/` directory
2. Restart Home Assistant
3. Go to **Settings → Devices & Services → Add Integration → RoomMind**

---

## Quick Start

After installation, RoomMind appears as a panel in the HA sidebar.

1. **Open RoomMind** from the sidebar — you'll see all your HA areas as room cards
2. **Click a room card** to open the detail view
3. **Add devices** — assign at least one thermostat or AC (climate entity)
4. **Add a temperature sensor** (optional but recommended) — enables Full Control mode with proportional valve control
5. **Add a schedule** — create a `schedule.*` helper in HA and assign it to the room
6. **Set temperatures** — configure comfort (schedule on) and eco (schedule off) temperatures

RoomMind starts controlling your climate devices immediately. If MPC mode is enabled (default), the thermal model begins learning your room's characteristics in the background.

---

## Usage Guide

### Dashboard

![Dashboard Overview](docs/images/page-dashboard.png)

The dashboard shows all configured rooms as cards. Each card displays:

- **Current temperature** and **target temperature**
- **Humidity** (if sensor configured)
- **Mode pill** — idle, heating, or cooling (with power percentage when using proportional control)
- **MPC badge** — shows "MPC active" or "MPC learning" when using Model Predictive Control
- **Mold badges** — warning/critical mold risk indicator and active prevention with temperature delta

You can **hide rooms** from the dashboard using the eye icon on hover. Toggle visibility of hidden rooms with the icon in the stats bar.

### Room Configuration

Click any room card to open the detail view with these configuration sections:

#### Devices

Assign `climate.*` entities to the room. RoomMind auto-detects the device type:
- **Thermostat** — entity only supports `heat` mode
- **AC** — entity supports `cool` or `heat_cool` mode

You can override the auto-detection if needed. A room needs at least one thermostat or AC to be considered "configured".

#### Sensors

- **Temperature sensor** — an external room temperature sensor. When set, enables **Full Control** mode where RoomMind directly decides heating/cooling/idle. Without it, the room operates in **Managed Mode** where the device self-regulates.
- **Humidity sensor** — optional, shown on the dashboard and in analytics. Required for mold risk detection.
- **Window/door sensors** — assign `binary_sensor.*` entities (device class: window or door). Climate control pauses when any sensor reports "open". Configure **open delay** and **close delay** (in seconds) to prevent brief openings from interrupting climate control.

#### Schedules

Assign one or more `schedule.*` helper entities. Each schedule defines time blocks — when a block is active, RoomMind uses its temperature (if set) or the room's comfort temperature. Outside schedule blocks, eco temperature is used.

**Multiple schedules:** Use a `schedule_selector_entity` to switch between schedules:
- `input_boolean` — off = schedule 1, on = schedule 2
- `input_number` — value selects which schedule (1-based)

#### Climate Mode

Choose how the room handles heating and cooling:
- **Auto** — both heating and cooling allowed (with outdoor temperature gating)
- **Heat Only** — cooling disabled
- **Cool Only** — heating disabled

#### Comfort & Eco Temperatures

- **Comfort** — target temperature when a schedule block is active (default: 21 °C)
- **Eco** — target temperature outside schedule blocks, during presence-away, or vacation (default: 17 °C)

#### Manual Override

Temporarily override the calculated target temperature:
- **Boost** — quick increase above comfort temperature
- **Eco** — drop to eco temperature
- **Custom** — set any temperature with a custom duration

Overrides have the highest priority and auto-clear when the timer expires.

#### Presence

Optionally assign `person.*`, `device_tracker.*`, `binary_sensor.*`, or `input_boolean.*` entities per room. The room's comfort schedule only applies when at least one assigned person is home — otherwise eco temperature is used. If no per-room persons are set, the global person list from settings applies.

### Settings

![Settings Page](docs/images/page-settings.png)

Access settings via the gear tab in the RoomMind panel.

#### General

| Setting | Description |
|---------|-------------|
| **Climate Control** | Master switch — when off, all devices are set to idle |
| **Model Learning** | Enable/disable thermal model training globally. Expand to pause learning for individual rooms |
| **Vacation Mode** | Set a global setback temperature + end date. All rooms use the vacation temperature until it expires |
| **Presence** | Track `person.*`, `device_tracker.*`, `binary_sensor.*`, or `input_boolean.*` entities globally. Rooms only use comfort temperature when assigned persons are home |
| **Valve Protection** | Periodically opens idle TRV valves to prevent seizing. Configure the idle threshold (1–90 days, default: 7) |

#### Sensors & Weather

| Setting | Description |
|---------|-------------|
| **Outdoor Temperature Sensor** | Used for outdoor gating thresholds (prevents heating when warm outside) |
| **Outdoor Humidity Sensor** | Informational, shown in analytics |
| **Weather Entity** | Provides cloud coverage for solar gain estimation and MPC forecasting |

#### Control

| Setting | Description |
|---------|-------------|
| **Control Mode** | MPC (self-learning, proportional) or On/Off (simple threshold control with hysteresis) |
| **Comfort/Energy Balance** | Slider (0–100, default: 70) — higher values prioritize comfort, lower values save energy |
| **Outdoor Cooling Minimum** | Don't cool if outdoor temperature is below this (default: 16 °C) |
| **Outdoor Heating Maximum** | Don't heat if outdoor temperature is above this (default: 22 °C) |
| **Prediction** | Enable/disable temperature forecast display in analytics |

#### Mold Risk

| Setting | Description |
|---------|-------------|
| **Mold Detection** | Estimates surface relative humidity using indoor temperature, humidity, and outdoor temperature (DIN 4108-2 method). Risk levels: ok / warning / critical |
| **Humidity Threshold** | Room air humidity (%) above which risk is flagged (default: 70 %) |
| **Sustained Time** | How long risk must persist before a notification is sent (default: 30 min) |
| **Notification Cooldown** | Minimum time between repeated notifications per room (default: 60 min) |
| **Notification Targets** | Mobile app notification services with optional per-person home/away filtering |
| **Mold Prevention** | Automatically raises the target temperature when mold risk is warning or critical |
| **Prevention Intensity** | Temperature increase: light (+1 °C), medium (+2 °C), or strong (+3 °C) |

Mold risk badges appear on the dashboard cards and in the room detail view when risk is detected.

#### Reset Thermal Data

Reset the learned thermal model for all rooms or a specific room. Useful if room characteristics change significantly (new insulation, different heating system).

### Analytics

![Analytics Chart](docs/images/page-analytics.png)

Select a room and time range (24h / 7d / 30d / 90d) to view:

- **Room temperature** vs. **target temperature** over time
- **Heating/cooling power** percentage
- **Solar irradiance** when the weather entity is configured
- **Model predictions** (when enabled) showing where the model expects the temperature to go

Hover over heating periods to see the exact power percentage and calculated TRV setpoint in the tooltip.

---

## How It Works

### Target Temperature Priority

RoomMind resolves the target temperature using this priority chain:

```
Manual Override  →  Vacation  →  Presence Away  →  Schedule Block  →  Comfort / Eco  (+Mold Delta)
  (highest)                                                            (lowest)        (additive)
```

- **Manual override** — user-set temperature with timer (boost/eco/custom)
- **Vacation** — global setback temperature until the configured end date
- **Presence away** — eco temperature when all assigned persons are away (`not_home` for `person`/`device_tracker`, `off` for `binary_sensor`/`input_boolean`)
- **Schedule block** — temperature from the active schedule block (if set), otherwise comfort temperature
- **Comfort / Eco** — comfort when schedule is on, eco when schedule is off
- **Mold prevention** — when active, adds +1/+2/+3 °C on top of the resolved target above

### MPC Climate Control

RoomMind uses Model Predictive Control — a self-learning approach that builds a thermal model of each room:

1. **Learning phase** — The Extended Kalman Filter (EKF) observes temperature changes during heating, cooling, and idle periods. It learns the room's heat loss rate, heating power, cooling power, and solar responsiveness.

2. **Prediction** — Once calibrated (prediction accuracy < 0.5 °C), the model can predict how the room temperature will evolve over the next 30 minutes.

3. **Optimization** — The MPC optimizer simulates 6 blocks ahead (5 min each) and finds the action sequence that minimizes a cost function balancing comfort (temperature deviation) and energy use.

4. **Proportional control** — Instead of binary on/off, TRVs receive a calculated setpoint between the current temperature and 30 °C based on the optimal power fraction. This produces smoother temperature curves with less overshoot.

**Automatic fallback:** Until the model is calibrated (needs ~60 idle samples and ~20 heating/cooling samples), RoomMind automatically uses simple on/off control with 0.2 °C hysteresis.

### Full Control vs. Managed Mode

| | Full Control | Managed Mode |
|---|---|---|
| **When** | External temperature sensor assigned | No external temperature sensor |
| **How** | RoomMind decides HEATING / COOLING / IDLE | RoomMind sets target temp, device self-regulates |
| **TRV behavior** | Proportional setpoint (MPC) or boost target (on/off) | Actual target temperature sent to device |
| **Best for** | Maximum control with external sensors | Simple setups or devices with good built-in control |

### Solar Gain Modeling

RoomMind estimates solar heat gain using:
- **Sun position** calculated from your HA latitude/longitude (NOAA algorithm)
- **Clear-sky model** (Meinel) for theoretical maximum irradiance
- **Cloud attenuation** from your weather entity's cloud coverage (if configured)

The thermal model learns a per-room solar factor (how much the room heats up from sunlight) and uses this to:
- Reduce heating when sun is shining into the room
- Plan ahead using weather forecasts for MPC optimization

Three tiers of accuracy depending on configuration:
1. No weather entity → clear-sky estimate only
2. Weather entity → real-time cloud attenuation
3. Weather entity with forecast → predictive solar planning for MPC

---

## Entities Created

RoomMind creates two sensor entities per configured room:

| Entity | Description |
|--------|-------------|
| `sensor.roommind_{area_id}_target_temp` | Current target temperature (°C) |
| `sensor.roommind_{area_id}_mode` | Current mode: `idle`, `heating`, or `cooling` |

These can be used in HA automations, dashboards, or other integrations.

> **Note:** RoomMind does not create entities for current temperature or humidity — these would duplicate your existing source sensors.

---

## Troubleshooting

**MPC shows "learning" for a long time**
The model needs at least 60 idle observations and 20 heating (or cooling) observations before MPC activates. In a room that heats rarely, this can take a few days. You can check progress in the Analytics tab under model status.

**Temperature seems to oscillate**
In on/off mode (or during MPC learning), some oscillation is normal (0.2 °C hysteresis). Once MPC is active with proportional control, oscillation should decrease significantly.

**Room is not heating/cooling when expected**
Check the outdoor gating thresholds in Settings → Control. By default, cooling is blocked below 16 °C outdoor temperature and heating above 22 °C.

**"MPC active" but device isn't responding**
Verify the climate entity is available in HA (Settings → Devices). RoomMind uses `climate.set_hvac_mode` and `climate.set_temperature` service calls.

**Thermal model seems wrong after changes**
If you've made significant changes to a room (new insulation, different radiator, moved sensors), reset the thermal model for that room in Settings → Reset Thermal Data.

**Frontend not updating after update**
Hard-refresh your browser: **Cmd+Shift+R** (Mac) or **Ctrl+Shift+R** (Windows/Linux).

---

## Requirements

- **Home Assistant** 2024.1.0 or newer
- At least one HA **area** with a `climate.*` entity
- Optional: external temperature sensor, humidity sensor, window/door sensors, weather entity, `schedule.*` helpers, `person.*` / `device_tracker.*` entities

No external dependencies or cloud services required — everything runs locally.

---

## License

[MIT](LICENSE) - Copyright (c) 2026 SnazzyBean
