# RoomMind

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2024.1%2B-blue.svg)](https://www.home-assistant.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Tests](https://github.com/snazzybean/roommind/actions/workflows/ci.yml/badge.svg)](https://github.com/snazzybean/roommind/actions/workflows/ci.yml)
![Coverage](https://raw.githubusercontent.com/snazzybean/roommind/python-coverage-comment-action-data/badge.svg)

[![Open your Home Assistant instance and open RoomMind inside HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=snazzybean&repository=roommind&category=integration)

**Intelligent room climate control for Home Assistant** - self-learning thermal model, proportional valve control, and a dedicated management panel.

![Dashboard](docs/images/page-dashboard.png)

## Features

- **Self-Learning MPC** - Per-room thermal model (Extended Kalman Filter) that learns your home's heating/cooling behavior over time. Automatic fallback to on/off control while learning.
- **Proportional Valve Control** - TRVs receive calculated setpoints instead of simple on/off, producing smoother temperature curves with less overshoot.
- **Solar Gain Awareness** - Estimates solar irradiance from sun position and weather data. The model learns each room's solar response and reduces unnecessary heating.
- **Multi-Scheduler** - Multiple `schedule.*` entities per room with selector switching via `input_boolean` or `input_number`.
- **Manual Override** - Boost, eco, or custom temperature with configurable duration and instant UI feedback.
- **Presence Detection** - Link `person.*`, `device_tracker.*`, `binary_sensor.*`, or `input_boolean.*` entities globally or per room. Eco temperature is used when all assigned persons are away.
- **Vacation Mode** - Global setback temperature with end date for all rooms.
- **Window/Door Pause** - Pauses climate control when windows or doors are open, with configurable open/close delays.
- **Mold Risk Detection & Prevention** - Surface humidity estimation using the DIN 4108-2 method. Configurable notifications and automatic temperature raise to prevent mold growth.
- **Valve Protection** - Periodic cycling of idle TRV valves to prevent seizing and calcification.
- **Analytics Dashboard** - Temperature charts with heating power, solar irradiance, and model predictions over 24h to 90 days.
- **Mobile Ready** - Responsive layout with HA-native toolbar for the companion app.
- **Multilingual** - English and German, auto-detected from your HA language setting.

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Click the three-dot menu > **Custom repositories**
3. Add `https://github.com/snazzybean/roommind` as an **Integration**
4. Search for "RoomMind" and install
5. Restart Home Assistant
6. Go to **Settings > Devices & Services > Add Integration > RoomMind**

### Manual

1. Copy `custom_components/roommind/` to your `config/custom_components/` directory
2. Restart Home Assistant
3. Go to **Settings > Devices & Services > Add Integration > RoomMind**

## Quick Start

After installation, RoomMind appears as a panel in the HA sidebar.

1. **Open RoomMind** from the sidebar - you'll see all your HA areas as room cards
2. **Click a room card** to open the detail view
3. **Add devices** - assign at least one thermostat or AC (`climate.*` entity)
4. **Add a temperature sensor** (optional but recommended) - enables Full Control with proportional valve control
5. **Add a schedule** - create a `schedule.*` helper in HA and assign it
6. **Set temperatures** - configure comfort (schedule on) and eco (schedule off) temperatures

RoomMind starts controlling immediately. If MPC is enabled (default), the thermal model begins learning in the background.

## Analytics

![Analytics](docs/images/page-analytics.png)

Select a room and time range (24h / 7d / 30d / 90d / custom) to view temperature history, heating/cooling power, solar irradiance, and model predictions. Export as CSV or diagnostics report.

## How It Works

### Target Temperature Priority

```
Manual Override > Vacation > Presence Away > Schedule Block > Comfort / Eco  (+Mold Delta)
```

### Full Control vs. Managed Mode

| | Full Control | Managed Mode |
|---|---|---|
| **When** | External temperature sensor assigned | No external sensor |
| **How** | RoomMind decides heating/cooling/idle | Device self-regulates |
| **TRV behavior** | Proportional setpoint (MPC) or boost (on/off) | Target temperature sent to device |

### MPC Climate Control

The Extended Kalman Filter observes temperature changes and learns each room's heat loss rate, heating/cooling power, and solar responsiveness. Once calibrated (prediction accuracy < 0.5 C), the MPC optimizer plans ahead and calculates proportional power for smoother control.

Until calibrated (~60 idle + ~20 active samples), RoomMind falls back to simple on/off control with hysteresis.

## Entities Created

| Entity | Description |
|--------|-------------|
| `sensor.roommind_{area_id}_target_temp` | Current target temperature |
| `sensor.roommind_{area_id}_mode` | Current mode: `idle`, `heating`, or `cooling` |

These can be used in HA automations, dashboards, or other integrations.

## Troubleshooting

**MPC shows "learning" for a long time** - The model needs ~60 idle and ~20 heating/cooling observations. This can take a few days for rooms that heat rarely. Check progress in the Analytics tab.

**Room not heating/cooling when expected** - Check outdoor gating thresholds in Settings > Control. Default: no cooling below 16 C, no heating above 22 C.

**Thermal model seems wrong after room changes** - If you've changed insulation, radiators, or moved sensors, reset the model in Settings > Reset Thermal Data.

**Frontend not updating after update** - Hard-refresh: **Cmd+Shift+R** (Mac) or **Ctrl+Shift+R** (Windows/Linux).

## Requirements

- **Home Assistant** 2024.1.0+
- At least one HA area with a `climate.*` entity
- Optional: temperature sensor, humidity sensor, window sensors, weather entity, schedule helpers, person entities

No cloud services required - everything runs locally.

## License

[MIT](LICENSE) - Copyright (c) 2026 SnazzyBean
