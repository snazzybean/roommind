"""Constants for the RoomMind integration."""

import time
from typing import NamedTuple

from homeassistant.const import Platform
from homeassistant.core import Context

DOMAIN = "roommind"
VERSION = "1.7.1-beta.4"

# Platforms
PLATFORMS = [Platform.SENSOR, Platform.SWITCH, Platform.BINARY_SENSOR, Platform.CLIMATE]

# Climate modes
CLIMATE_MODE_AUTO = "auto"
CLIMATE_MODE_HEAT_ONLY = "heat_only"
CLIMATE_MODE_COOL_ONLY = "cool_only"
CLIMATE_MODES = [CLIMATE_MODE_AUTO, CLIMATE_MODE_HEAT_ONLY, CLIMATE_MODE_COOL_ONLY]

# Override types
OVERRIDE_BOOST = "boost"
OVERRIDE_ECO = "eco"
OVERRIDE_CUSTOM = "custom"
OVERRIDE_TYPES = [OVERRIDE_BOOST, OVERRIDE_ECO, OVERRIDE_CUSTOM]

# Room modes
MODE_IDLE = "idle"
MODE_HEATING = "heating"
MODE_COOLING = "cooling"

# Schedule states
SCHEDULE_STATE_ON = "on"

# Defaults
DEFAULT_COMFORT_TEMP = 21.0
DEFAULT_ECO_TEMP = 17.0

# Split heat/cool defaults
DEFAULT_COMFORT_HEAT = 21.0
DEFAULT_COMFORT_COOL = 24.0
DEFAULT_ECO_HEAT = 17.0
DEFAULT_ECO_COOL = 27.0


# Context identifier for RoomMind-initiated service calls.
# Automations can check: trigger.context.parent_id == "roommind"
ROOMMIND_CONTEXT_ID = "roommind"


def make_roommind_context() -> Context:
    """Create a HA Context tagged as originating from RoomMind."""
    return Context(parent_id=ROOMMIND_CONTEXT_ID)


class TargetTemps(NamedTuple):
    """Dual-target temperatures for heating and cooling."""

    heat: float | None = None  # None = don't heat / force off
    cool: float | None = None  # None = don't cool / force off


# Smart control defaults
BANGBANG_HEAT_HYSTERESIS = 0.2  # °C below target → start heating (bang-bang fallback)
BANGBANG_COOL_HYSTERESIS = 0.2  # °C above target → start cooling (bang-bang fallback)
DEFAULT_OUTDOOR_COOLING_MIN = 16  # Hard block: NEVER cool if outdoor < this
DEFAULT_OUTDOOR_HEATING_MAX = 22  # Don't heat if outdoor > this
HEATING_BOOST_TARGET = 30  # Fallback TRV heating boost (used when entity max_temp unavailable)
AC_HEATING_BOOST_TARGET = 30  # Fallback AC heating boost (used when entity max_temp unavailable)
AC_COOLING_BOOST_TARGET = 16  # Fallback AC cooling boost (used when entity min_temp unavailable)
MIN_POWER_FRACTION = 0.15  # Minimum non-zero power fraction (prevents TRV dead zone)

# Update interval in seconds
UPDATE_INTERVAL = 30

# Sensor dropout: keep using cached temperature for this many seconds
# before falling back to idle (~10 coordinator cycles at 30s).
MAX_SENSOR_STALENESS = 300

# Coordinator throttle intervals (in cycles of UPDATE_INTERVAL)
HISTORY_WRITE_CYCLES = 6  # ~3 min at 30s cycle
THERMAL_SAVE_CYCLES = 30  # ~15 min
HISTORY_ROTATE_CYCLES = 360  # ~3 hours

# EKF update: accumulate observations before updating (better signal-to-noise)
EKF_UPDATE_MIN_DT = 3.0  # minutes — matches HISTORY_WRITE_CYCLES

# Prediction clamping: max °C change in one prediction step (prevents unrealistic jumps)
MAX_PREDICTION_DELTA = 3.0

# Valve protection (anti-seize): periodic cycling of idle TRV valves
VALVE_PROTECTION_CHECK_CYCLES = 120  # ~1 hour — how often to scan for stale valves
VALVE_PROTECTION_CYCLE_DURATION = 15  # seconds — minimum before closing (actual ≥ UPDATE_INTERVAL)
DEFAULT_VALVE_PROTECTION_INTERVAL = 7  # days — default idle threshold before cycling

# Mold risk detection & prevention
MOLD_RISK_OK = "ok"
MOLD_RISK_WARNING = "warning"
MOLD_RISK_CRITICAL = "critical"
MOLD_SURFACE_RH_WARNING = 70.0  # estimated surface RH % — warning threshold
MOLD_SURFACE_RH_CRITICAL = 80.0  # estimated surface RH % — critical threshold
DEFAULT_MOLD_HUMIDITY_THRESHOLD = 70.0  # room air RH % — notification trigger
DEFAULT_MOLD_SUSTAINED_MINUTES = 30  # minutes risk must persist before notification
DEFAULT_MOLD_COOLDOWN_MINUTES = 60  # minutes between repeated notifications per room
MOLD_PREVENTION_DELTAS = {"light": 1.0, "medium": 2.0, "strong": 3.0}
MOLD_HYSTERESIS = 5.0  # surface RH must drop this much below warning to clear
MIN_MOLD_GROWTH_TEMP = 5.0  # °C — below this surface temp, mold risk negligible

# Heating system profiles — residual heat modeling per system type
# tau_minutes: exponential decay time constant of residual heat after heating stops
# initial_fraction: fraction of beta_h at t=0 (fully charged thermal mass)
# tau_charge_minutes: time constant for thermal mass to charge (how long heating must run)
# min_run_minutes: minimum heating run time for the MPC optimizer
HEATING_SYSTEM_PROFILES: dict[str, dict[str, float]] = {
    "radiator": {
        "tau_minutes": 10.0,
        "initial_fraction": 0.3,
        "tau_charge_minutes": 15.0,
        "min_run_minutes": 10.0,
    },
    "underfloor": {
        "tau_minutes": 90.0,
        "initial_fraction": 0.85,
        "tau_charge_minutes": 60.0,
        "min_run_minutes": 30.0,
    },
}
RESIDUAL_HEAT_CUTOFF = 0.02  # below this q_residual is treated as zero

# Blind/cover control
COVER_SOLAR_MIN: float = 0.15
COVER_HYSTERESIS: float = 1.0
COVER_MIN_HOLD_SECONDS: int = 900
COVER_POS_SCALE: float = 50.0
COVER_MAX_EFFECTIVENESS: float = 0.85
COVER_USER_CONFLICT_THRESHOLD: int = 15
COVER_USER_OVERRIDE_MINUTES: int = 60
COVER_TRANSITION_SETTLE_S: int = 90  # seconds after commanding before override detection activates
COVER_DEFAULT_BETA_S: float = 3.0  # °C/h per unit q_solar (default for rooms without learned data)
COVER_LINEAR_LOOKAHEAD_H: float = 1.0  # linear fallback: 1h (no heat-loss correction → keep short)
COVER_PREDICTION_DT_MINUTES: float = 5.0  # time step for RC trajectory simulation
COVER_MAX_PREDICTION_STD: float = 0.5  # max idle+solar prediction_std to activate RC tier
COVER_CONFIDENCE_REFERENCE_SOLAR: float = 0.5  # reference q_solar for confidence check
COVER_MIN_IDLE_FOR_LEARNED: int = 30  # Min idle observations before trusting EKF's beta_s
COVER_POS_DEADBAND: int = 20  # min position change (%) to trigger motor movement
COVER_DAILY_LOOKAHEAD_H: float = 8.0  # hours ahead to search for daily solar peak (Tier 2)

# Heat source orchestration — smart routing for rooms with multiple heating device types
DEFAULT_HEAT_SOURCE_PRIMARY_DELTA = 1.5  # °C gap to engage primary (boiler/radiator)
DEFAULT_HEAT_SOURCE_OUTDOOR_THRESHOLD = 5.0  # °C outdoor: above = prefer AC, below = prefer boiler
DEFAULT_HEAT_SOURCE_AC_MIN_OUTDOOR = -15.0  # °C hard-disable AC heating below this
HEAT_SOURCE_HYSTERESIS = 0.3  # °C hysteresis band to prevent oscillation
HEAT_SOURCE_LARGE_GAP_MULTIPLIER = 2.0  # activate both sources when gap > primary_delta * this
HEAT_SOURCE_SECONDARY_POWER_SCALE = 0.7  # throttle secondary when both active (prevent overshoot)

# Compressor group defaults
DEFAULT_COMPRESSOR_MIN_RUN_MINUTES = 15
DEFAULT_COMPRESSOR_MIN_OFF_MINUTES = 5

# Compressor group master device — conflict resolution strategies
CONFLICT_RESOLUTION_HEATING_PRIORITY = "heating_priority"
CONFLICT_RESOLUTION_COOLING_PRIORITY = "cooling_priority"
CONFLICT_RESOLUTION_MAJORITY = "majority"
CONFLICT_RESOLUTION_OUTDOOR_TEMP = "outdoor_temp"
CONFLICT_RESOLUTIONS = [
    CONFLICT_RESOLUTION_HEATING_PRIORITY,
    CONFLICT_RESOLUTION_COOLING_PRIORITY,
    CONFLICT_RESOLUTION_MAJORITY,
    CONFLICT_RESOLUTION_OUTDOOR_TEMP,
]
DEFAULT_CONFLICT_RESOLUTION = CONFLICT_RESOLUTION_HEATING_PRIORITY


# Far-future sentinel: vacation active indefinitely (year 2999)
VACATION_SENTINEL_UNTIL = 32503680000.0


def build_override_live(room: dict) -> dict:
    """Build override fields for live data from a room config dict."""
    override_temp = room.get("override_temp")
    override_until = room.get("override_until")
    active = bool(override_temp is not None and (override_until is None or time.time() < override_until))
    return {
        "override_active": active,
        "override_type": room.get("override_type") if active else None,
        "override_temp": override_temp if active else None,
        "override_until": override_until if active else None,
    }
