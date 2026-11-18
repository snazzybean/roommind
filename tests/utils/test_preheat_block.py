"""Pre-heating per schedule block: ``preheat`` in a block's data overrides the room's switch."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

import pytest
from homeassistant.util import dt as dt_util

from custom_components.roommind.control import analytics_simulator
from custom_components.roommind.control.mpc_controller import MODE_COOLING, MODE_HEATING, MODE_IDLE, MPCController
from custom_components.roommind.control.mpc_optimizer import MPCOptimizer, preheat_lead_blocks
from custom_components.roommind.control.thermal_model import RCModel, RoomModelManager
from custom_components.roommind.utils.schedule_utils import (
    _UNSET,
    make_preheat_lead_resolver,
    parse_block_preheat,
)
from tests.control.conftest import build_hass, make_room

# Radiator sized to the heat load: +2 K in 3 h needs about 4 h at full power
SLOW = RCModel(C=1.0, U=0.014, Q_heat=0.56, Q_cool=4.0)

# ---------------------------------------------------------------------------
# Block data
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (True, None),
        (False, 0.0),
        ("on", None),
        (" YES ", None),
        ("false", 0.0),
        ("Off", 0.0),
        (45, 2700.0),
        (45.5, 2730.0),
        ("30", 1800.0),
        (0, 0.0),
        (-10, 0.0),
    ],
)
def test_parse_block_preheat(raw, expected):
    assert parse_block_preheat(raw) == expected


@pytest.mark.parametrize("raw", [None, "maybe", float("nan"), [1]])
def test_parse_block_preheat_unusable(raw):
    assert parse_block_preheat(raw) is _UNSET


def _blocks(data_morning: dict, data_evening: dict | None = None) -> dict:
    day = [
        {"from": "06:00:00", "to": "08:00:00", "data": data_morning},
        {"from": "17:00:00", "to": "22:00:00", "data": data_evening or {}},
    ]
    return {d: day for d in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")}


def _ts(hour: int, minute: int = 0) -> float:
    return dt_util.as_utc(datetime(2026, 1, 12, hour, minute, tzinfo=dt_util.get_default_time_zone())).timestamp()


def test_lead_resolver_room_default_and_block_override():
    lead = make_preheat_lead_resolver(_blocks({"preheat": 45}, {"preheat": False}), {})
    assert lead is not None
    assert lead(_ts(7)) == 2700.0  # morning block: 45 min
    assert lead(_ts(18)) == 0.0  # evening block: off
    assert lead(_ts(12)) is None  # outside blocks: the room's switch (on)
    off_room = make_preheat_lead_resolver(_blocks({}, {"preheat": True}), {"preheat_enabled": False})
    assert off_room is not None
    assert off_room(_ts(7)) == 0.0  # no block value: room switched off
    assert off_room(_ts(18)) is None  # the block switches it on


def test_no_resolver_without_a_block_setting_preheat():
    """Only the room's switch applies then, exactly as without this feature."""
    assert make_preheat_lead_resolver(None, {}) is None
    assert make_preheat_lead_resolver({}, {"preheat_enabled": False}) is None
    assert make_preheat_lead_resolver(_blocks({"temperature": 21}), {"preheat_enabled": False}) is None
    assert make_preheat_lead_resolver(_blocks({"preheat": "maybe"}), {}) is None


def test_lead_blocks():
    assert preheat_lead_blocks(None) is None
    assert preheat_lead_blocks(0.0) == 0
    assert preheat_lead_blocks(2700.0) == 9
    assert preheat_lead_blocks(2999.0) == 9


# ---------------------------------------------------------------------------
# Optimizer: the lead limits the pre-heat deadline
# ---------------------------------------------------------------------------


def _plan(T_room, rise_at, lead_at_rise, *, n=72, preheat_max_blocks=None):
    leads = [None] * rise_at + [lead_at_rise] * (n - rise_at)
    opt = MPCOptimizer(
        SLOW,
        can_heat=True,
        can_cool=False,
        preheat_max_blocks=preheat_max_blocks,
        preheat_lead_blocks=leads,
    )
    return opt.optimize(
        T_room=T_room,
        T_outdoor_series=[0.0] * n,
        heat_target_series=[17.5] * rise_at + [20.0] * (n - rise_at),
        dt_minutes=5,
    )


def test_unlimited_block_lead_preheats_like_before():
    plan = _plan(18.0, rise_at=36, lead_at_rise=None)
    assert plan.actions[0] == MODE_HEATING
    assert plan.preheat_blocks == 36


def test_block_switched_off_does_not_preheat():
    plan = _plan(18.0, rise_at=36, lead_at_rise=0)
    assert plan.actions[0] == MODE_IDLE
    assert plan.preheat_blocks == 0


def test_block_lead_shorter_than_the_rise_waits():
    assert _plan(18.0, rise_at=36, lead_at_rise=24).actions[0] == MODE_IDLE  # 2 h lead, block 3 h away
    plan = _plan(18.0, rise_at=36, lead_at_rise=36)  # within the lead
    assert plan.actions[0] == MODE_HEATING
    assert plan.preheat_blocks == 36


def test_slider_limit_still_applies_on_top():
    assert _plan(18.0, rise_at=36, lead_at_rise=None, preheat_max_blocks=12).actions[0] == MODE_IDLE


# ---------------------------------------------------------------------------
# Controller and analytics
# ---------------------------------------------------------------------------


def _controller(room, preheat_lead):
    return MPCController(
        build_hass(),
        room,
        model_manager=RoomModelManager(),
        outdoor_temp=0.0,
        settings={"comfort_weight": 70},
        has_external_sensor=True,
        preheat_lead=preheat_lead,
    )


def test_room_switch_goes_into_the_block_lead():
    """A room switched off still lets a block pre-heat: the room's default comes per block."""
    room = make_room(preheat_enabled=False)
    assert _controller(room, None)._preheat_max_blocks == 0
    assert _controller(room, lambda ts: None)._preheat_max_blocks is None


def test_analytics_passes_the_forecast_lead():
    seen = []
    real = analytics_simulator.MPCOptimizer

    def spy(*args, **kwargs):
        seen.append((kwargs.get("preheat_max_blocks"), kwargs.get("preheat_lead_blocks")))
        return real(*args, **kwargs)

    eco = {"target_temp": 17.5, "heat_target": 17.5, "cool_target": 30.0, "preheat_lead": 0.0}
    block = {"target_temp": 20.0, "heat_target": 20.0, "cool_target": 30.0, "preheat_lead": 1800.0}
    room = make_room(preheat_enabled=False, climate_mode="heat_only")
    with patch.object(analytics_simulator, "MPCOptimizer", side_effect=spy):
        analytics_simulator._simulate_mpc(
            SLOW, [eco] * 3 + [block] * 3, [0.0] * 6, current_temp=18.0, room_config=room, settings={}
        )
    max_blocks, leads = seen[0]
    assert max_blocks is None  # the room's switch is in the leads
    assert leads == [0, 0, 0, 6, 6, 6]


def test_analytics_without_lead_keeps_the_room_switch():
    seen = []
    real = analytics_simulator.MPCOptimizer

    def spy(*args, **kwargs):
        seen.append((kwargs.get("preheat_max_blocks"), kwargs.get("preheat_lead_blocks")))
        return real(*args, **kwargs)

    forecast = [{"target_temp": 17.5, "heat_target": 17.5, "cool_target": 30.0}] * 6
    room = make_room(preheat_enabled=False, climate_mode="heat_only")
    with patch.object(analytics_simulator, "MPCOptimizer", side_effect=spy):
        analytics_simulator._simulate_mpc(SLOW, forecast, [0.0] * 6, current_temp=18.0, room_config=room, settings={})
    assert seen and all(v == (0, None) for v in seen)


@pytest.mark.asyncio
async def test_forecast_carries_the_block_lead():
    from unittest.mock import AsyncMock, MagicMock

    from custom_components.roommind.services import analytics_service

    hass = MagicMock()
    hass.config.units.temperature_unit = "°C"
    room = {"comfort_heat": 21.0, "eco_heat": 17.0, "schedules": [{"entity_id": "schedule.x"}]}
    all_day = {d: [{"from": "00:00:00", "to": "23:59:59", "data": {"preheat": 30}}] for d in _blocks({})}
    with (
        patch("custom_components.roommind.utils.schedule_utils.get_active_schedule_entity", return_value="schedule.x"),
        patch("custom_components.roommind.utils.schedule_utils.read_schedule_blocks", AsyncMock(return_value=all_day)),
        patch("custom_components.roommind.utils.presence_utils.is_presence_away", return_value=False),
    ):
        forecast = await analytics_service._compute_target_forecast(hass, room, {}, hours=0.5)
    assert forecast and all(p["preheat_lead"] == 1800.0 for p in forecast[:-1])

    plain = await analytics_service._compute_target_forecast(hass, {"schedules": []}, {}, hours=0.5)
    assert all("preheat_lead" not in p for p in plain)


# ---------------------------------------------------------------------------
# Pre-cooling: the same lead limits the pre-cool deadline
# ---------------------------------------------------------------------------

SMALL_AC = RCModel(C=1.0, U=0.05, Q_heat=3.0, Q_cool=2.0)


def _precool(lead_at_fall, *, n=72, fall_at=18):
    cool = [27.0] * fall_at + [24.0] * (n - fall_at)
    opt = MPCOptimizer(
        SMALL_AC,
        can_heat=False,
        can_cool=True,
        cool_min_run_blocks=2,
        preheat_lead_blocks=[None] * fall_at + [lead_at_fall] * (n - fall_at),
    )
    return opt.optimize(
        T_room=26.8,
        T_outdoor_series=[32.0] * n,
        heat_target_series=[min(26.8, c) for c in cool],
        cool_target_series=cool,
        dt_minutes=5,
    )


def test_block_lead_limits_the_precool():
    assert _precool(None).actions[0] == MODE_COOLING  # 1.5 h ahead, as without preheat
    assert _precool(0).actions[0] == MODE_IDLE  # preheat: false
    assert _precool(12).actions[0] == MODE_IDLE  # 1 h lead, block 1.5 h away
    assert _precool(18).actions[0] == MODE_COOLING
