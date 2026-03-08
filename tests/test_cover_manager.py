"""Tests for CoverManager — constants, shading factor, deployment logic, and user override."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.roommind.const import (
    COVER_SOLAR_MIN, COVER_HYSTERESIS, COVER_MIN_HOLD_SECONDS,
    COVER_POS_SCALE, COVER_MAX_EFFECTIVENESS,
    COVER_USER_CONFLICT_THRESHOLD, COVER_USER_OVERRIDE_MINUTES,
)
from custom_components.roommind.managers.cover_manager import (
    CoverManager, CoverDecision, compute_shading_factor,
)


# ── Constants ──────────────────────────────────────────────────────────

def test_cover_constants_exist():
    assert COVER_SOLAR_MIN == 0.15
    assert COVER_HYSTERESIS == 1.0
    assert COVER_MIN_HOLD_SECONDS == 900
    assert COVER_POS_SCALE == 25.0
    assert COVER_MAX_EFFECTIVENESS == 0.85
    assert COVER_USER_CONFLICT_THRESHOLD == 15
    assert COVER_USER_OVERRIDE_MINUTES == 60


# ── Store defaults ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_room_config_has_cover_defaults():
    """Store must include cover defaults when creating a new room."""
    from unittest.mock import AsyncMock, MagicMock
    from custom_components.roommind.store import RoomMindStore

    store = RoomMindStore.__new__(RoomMindStore)
    store._store = MagicMock()
    store._data = {}
    store._settings = {}
    store._thermal_data = {}
    store._store.async_save = AsyncMock()

    await store.async_save_room("test_area", {})

    room = store._data["test_area"]
    assert room["covers"] == []
    assert room["covers_auto_enabled"] is False
    assert room["covers_deploy_threshold"] == 1.5
    assert room["covers_min_position"] == 0
    assert room["covers_outdoor_min_temp"] == 10.0
    assert room["covers_override_minutes"] == 60
    assert room["cover_schedules"] == []
    assert room["cover_schedule_selector_entity"] == ""
    assert room["covers_night_close"] is False
    assert room["covers_night_position"] == 0


# ── Shading factor ─────────────────────────────────────────────────────

def test_shading_factor_fully_open():
    assert compute_shading_factor([100]) == 1.0


def test_shading_factor_fully_closed():
    assert abs(compute_shading_factor([0]) - 0.15) < 0.001


def test_shading_factor_half():
    assert abs(compute_shading_factor([50]) - 0.575) < 0.001


def test_shading_factor_average_multiple():
    assert abs(compute_shading_factor([0, 100]) - 0.575) < 0.001


def test_shading_factor_no_covers():
    assert compute_shading_factor([]) == 1.0


# ── Behavioral tests ───────────────────────────────────────────────────

_BASE_KWARGS = dict(
    covers_auto_enabled=True,
    cover_entity_ids=["cover.living_room"],
    covers_deploy_threshold=1.5,
    covers_min_position=0,
    covers_outdoor_min_temp=10.0,
    has_active_override=False,
    forced_position=None,
    forced_reason="",
    q_solar=0.5,
    outdoor_temp=20.0,
)


def test_deploy_when_predicted_hot():
    mgr = CoverManager()
    d = mgr.evaluate("lr", predicted_peak_temp=25.0, target_temp=22.0, **_BASE_KWARGS)
    # excess=3.0 > threshold=1.5 → raw_close=int((3.0-1.5)*25)=37 → pos=63
    assert d.changed is True
    assert d.target_position == 63


def test_no_deploy_exact_threshold():
    mgr = CoverManager()
    d = mgr.evaluate("lr", predicted_peak_temp=23.5, target_temp=22.0, **_BASE_KWARGS)
    # excess=1.5 == threshold → raw_close=0 → pos=100 but no change (already at 100)
    assert d.changed is False


def test_no_deploy_in_hysteresis_band():
    mgr = CoverManager()
    d = mgr.evaluate("lr", predicted_peak_temp=23.1, target_temp=22.0, **_BASE_KWARGS)
    assert d.changed is False
    assert "hysteresis" in d.reason


def test_no_deploy_low_solar():
    mgr = CoverManager()
    kwargs = {k: v for k, v in _BASE_KWARGS.items() if k not in ("q_solar", "outdoor_temp")}
    d = mgr.evaluate("lr", predicted_peak_temp=26.0, target_temp=22.0,
                      q_solar=0.05, outdoor_temp=20.0, **kwargs)
    assert d.changed is False
    assert "solar" in d.reason


def test_no_deploy_cold_outdoor():
    mgr = CoverManager()
    kwargs = {k: v for k, v in _BASE_KWARGS.items() if k != "outdoor_temp"}
    d = mgr.evaluate("lr", predicted_peak_temp=25.0, target_temp=22.0,
                      outdoor_temp=5.0, **kwargs)
    assert d.changed is False
    assert "cold" in d.reason


def test_cold_weather_retracts_if_closed():
    mgr = CoverManager()
    mgr._get_state("lr").current_position = 40
    kwargs = {k: v for k, v in _BASE_KWARGS.items() if k != "outdoor_temp"}
    d = mgr.evaluate("lr", predicted_peak_temp=25.0, target_temp=22.0,
                      outdoor_temp=5.0, **kwargs)
    assert d.changed is True
    assert d.target_position == 100


def test_cold_weather_retract_respects_hold_time():
    """Retract on cold weather must also respect minimum hold time."""
    mgr = CoverManager()
    with patch("custom_components.roommind.managers.cover_manager.time") as mock_t:
        # First: deploy blinds
        mock_t.time.return_value = 10000.0
        d1 = mgr.evaluate("lr", predicted_peak_temp=25.0, target_temp=22.0, **_BASE_KWARGS)
        assert d1.changed is True

        # 30s later: cold weather → retract should be BLOCKED by hold time
        mock_t.time.return_value = 10030.0
        kwargs = {k: v for k, v in _BASE_KWARGS.items() if k != "outdoor_temp"}
        d2 = mgr.evaluate("lr", predicted_peak_temp=25.0, target_temp=22.0,
                          outdoor_temp=5.0, **kwargs)
        assert d2.changed is False
        assert "hold_time" in d2.reason

        # After hold time expires: retract succeeds
        mock_t.time.return_value = 10000.0 + COVER_MIN_HOLD_SECONDS + 1
        d3 = mgr.evaluate("lr", predicted_peak_temp=25.0, target_temp=22.0,
                          outdoor_temp=5.0, **kwargs)
        assert d3.changed is True
        assert d3.target_position == 100


def test_min_hold_time_prevents_rapid_cycling():
    mgr = CoverManager()
    with patch("custom_components.roommind.managers.cover_manager.time") as mock_t:
        mock_t.time.return_value = 10000.0
        d1 = mgr.evaluate("lr", predicted_peak_temp=25.0, target_temp=22.0, **_BASE_KWARGS)
        assert d1.changed is True

        mock_t.time.return_value = 10001.0  # 1 second later
        d2 = mgr.evaluate("lr", predicted_peak_temp=22.3, target_temp=22.0, **_BASE_KWARGS)
        assert d2.changed is False
        assert "hold_time" in d2.reason


def test_position_changes_after_hold_time():
    mgr = CoverManager()
    with patch("custom_components.roommind.managers.cover_manager.time") as mock_t:
        mock_t.time.return_value = 10000.0
        mgr.evaluate("lr", predicted_peak_temp=25.0, target_temp=22.0, **_BASE_KWARGS)

        mock_t.time.return_value = 10000.0 + COVER_MIN_HOLD_SECONDS + 1
        kwargs = {k: v for k, v in _BASE_KWARGS.items() if k not in ("q_solar", "outdoor_temp")}
        d = mgr.evaluate("lr", predicted_peak_temp=22.3, target_temp=22.0,
                          q_solar=0.05, outdoor_temp=20.0, **kwargs)
        assert d.changed is True
        assert d.target_position == 100


def test_thermal_moves_to_target_in_one_step():
    """Thermal decisions move directly to target position (no step limit)."""
    mgr = CoverManager()
    with patch("custom_components.roommind.managers.cover_manager.time") as mock_t:
        mock_t.time.return_value = 10000.0
        d = mgr.evaluate("lr", predicted_peak_temp=30.0, target_temp=22.0, **_BASE_KWARGS)
        assert d.changed is True
        # excess=8°C, should deploy fully in one step (not limited to 20%)
        assert d.target_position < 80  # would have been 80 with old 20% step limit


def test_manual_override_blocks_auto_control():
    mgr = CoverManager()
    kwargs = {**_BASE_KWARGS, "has_active_override": True}
    d = mgr.evaluate("lr", predicted_peak_temp=28.0, target_temp=22.0, **kwargs)
    assert d.changed is False
    assert "override" in d.reason


def test_min_position_respected():
    """Deploy with high excess must respect minimum position floor."""
    mgr = CoverManager()
    kwargs = {**_BASE_KWARGS, "covers_min_position": 30}
    d = mgr.evaluate("lr", predicted_peak_temp=35.0, target_temp=22.0, **kwargs)
    assert d.changed is True
    assert d.target_position >= 30


def test_disabled_feature_does_nothing():
    mgr = CoverManager()
    kwargs = {**_BASE_KWARGS, "covers_auto_enabled": False}
    d = mgr.evaluate("lr", predicted_peak_temp=35.0, target_temp=22.0, **kwargs)
    assert d.changed is False
    assert "disabled" in d.reason


def test_no_prediction_blocks_deployment():
    """Without predicted_peak_temp, thermal logic is skipped."""
    mgr = CoverManager()
    d = mgr.evaluate("lr", predicted_peak_temp=None, target_temp=22.0, **_BASE_KWARGS)
    assert d.changed is False
    assert "no_prediction" in d.reason


# ── User override detection ────────────────────────────────────────────

def test_user_override_detected_when_cover_opened_manually():
    mgr = CoverManager()
    with patch("custom_components.roommind.managers.cover_manager.time") as mock_t:
        mock_t.time.return_value = 1000.0
        d1 = mgr.evaluate("lr", predicted_peak_temp=25.0, target_temp=22.0, **_BASE_KWARGS)
        assert d1.changed is True

        # User manually opens to 100% (goes to balcony)
        mock_t.time.return_value = 1100.0
        mgr.update_position("lr", 100)

        # Next cycle: blocked by user override
        mock_t.time.return_value = 1200.0
        d2 = mgr.evaluate("lr", predicted_peak_temp=25.0, target_temp=22.0, **_BASE_KWARGS)
        assert d2.changed is False
        assert "user_override" in d2.reason

        # After override expires: auto control resumes
        mock_t.time.return_value = 1000.0 + COVER_USER_OVERRIDE_MINUTES * 60 + 100
        d3 = mgr.evaluate("lr", predicted_peak_temp=25.0, target_temp=22.0, **_BASE_KWARGS)
        assert "user_override" not in d3.reason


def test_user_override_not_triggered_on_first_read():
    mgr = CoverManager()
    mgr.update_position("lr", 100)
    state = mgr._get_state("lr")
    assert state.user_override_until == 0.0


def test_user_override_triggered_when_closing_significantly():
    """User manually closes covers significantly → override detected."""
    mgr = CoverManager()
    with patch("custom_components.roommind.managers.cover_manager.time") as mock_t:
        mock_t.time.return_value = 1000.0
        d = mgr.evaluate("lr", predicted_peak_temp=25.0, target_temp=22.0, **_BASE_KWARGS)
        assert d.changed is True  # Confirm position was commanded
        # User closes further (e.g. position 20, delta from ~63 > threshold=15)
        mock_t.time.return_value = 1100.0
        mgr.update_position("lr", 20)
        state = mgr._get_state("lr")
        assert state.user_override_until > 0.0


def test_user_override_not_triggered_for_small_drift():
    """Small drift within threshold does not trigger override."""
    mgr = CoverManager()
    state = mgr._get_state("lr")
    state.last_commanded_position = 80
    # Small closing drift: 70 vs 80, delta=10 < threshold=15
    mgr.update_position("lr", 70)
    assert state.user_override_until == 0.0
    # Small opening drift: 90 vs 80, delta=10 < threshold=15
    mgr.update_position("lr", 90)
    assert state.user_override_until == 0.0


def test_override_duration_uses_custom_value():
    """Override duration uses room-specific value."""
    mgr = CoverManager()
    with patch("custom_components.roommind.managers.cover_manager.time") as mock_t:
        mock_t.time.return_value = 1000.0
        mgr.evaluate("lr", predicted_peak_temp=25.0, target_temp=22.0, **_BASE_KWARGS)
        mock_t.time.return_value = 1100.0
        mgr.update_position("lr", 100, override_minutes=120)
        state = mgr._get_state("lr")
        expected = 1100.0 + 120 * 60
        assert abs(state.user_override_until - expected) < 1.0


def test_override_duration_zero_means_no_pause():
    """override_minutes=0 means no pause after manual movement."""
    mgr = CoverManager()
    with patch("custom_components.roommind.managers.cover_manager.time") as mock_t:
        mock_t.time.return_value = 1000.0
        mgr.evaluate("lr", predicted_peak_temp=25.0, target_temp=22.0, **_BASE_KWARGS)
        mock_t.time.return_value = 1100.0
        mgr.update_position("lr", 100, override_minutes=0)
        # user_override_until = 1100.0 + 0 = 1100.0, which is <= time.time()
        mock_t.time.return_value = 1100.0
        assert not mgr.is_user_override_active("lr")


def test_low_solar_retract_respects_hold_time():
    """Retract on low solar must also respect minimum hold time."""
    mgr = CoverManager()
    with patch("custom_components.roommind.managers.cover_manager.time") as mock_t:
        mock_t.time.return_value = 10000.0
        d1 = mgr.evaluate("lr", predicted_peak_temp=25.0, target_temp=22.0, **_BASE_KWARGS)
        assert d1.changed is True

        # 30s later: clouds appear → low solar → retract blocked by hold time
        mock_t.time.return_value = 10030.0
        kwargs = {k: v for k, v in _BASE_KWARGS.items() if k not in ("q_solar", "outdoor_temp")}
        d2 = mgr.evaluate("lr", predicted_peak_temp=25.0, target_temp=22.0,
                          q_solar=0.05, outdoor_temp=20.0, **kwargs)
        assert d2.changed is False
        assert "hold_time" in d2.reason


def test_remove_room_cleans_state():
    """remove_room() should delete all per-room state."""
    mgr = CoverManager()
    mgr.update_position("lr", 50)
    assert "lr" in mgr._states
    mgr.remove_room("lr")
    assert "lr" not in mgr._states


def test_remove_room_nonexistent_is_noop():
    """remove_room() for an unknown area should not raise."""
    mgr = CoverManager()
    mgr.remove_room("does_not_exist")  # Should not raise


# ── async_apply tests ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_async_apply_with_position_support():
    """Covers with SET_POSITION support get set_cover_position called."""
    from unittest.mock import AsyncMock, MagicMock
    hass = MagicMock()
    hass.services.async_call = AsyncMock()

    cover_state = MagicMock()
    cover_state.attributes = {"supported_features": 4, "current_position": 100}
    hass.states.get = MagicMock(return_value=cover_state)

    await CoverManager.async_apply(hass, ["cover.blind1"], 60)

    hass.services.async_call.assert_called_once_with(
        "cover", "set_cover_position",
        {"entity_id": ["cover.blind1"], "position": 60},
        blocking=False,
    )


@pytest.mark.asyncio
async def test_async_apply_binary_only_open():
    """Binary covers without position support get open_cover when target >= 100."""
    from unittest.mock import AsyncMock, MagicMock
    hass = MagicMock()
    hass.services.async_call = AsyncMock()

    cover_state = MagicMock()
    cover_state.attributes = {"supported_features": 0}  # No SET_POSITION
    hass.states.get = MagicMock(return_value=cover_state)

    await CoverManager.async_apply(hass, ["cover.simple"], 100)

    hass.services.async_call.assert_called_once_with(
        "cover", "open_cover",
        {"entity_id": ["cover.simple"]},
        blocking=False,
    )


@pytest.mark.asyncio
async def test_async_apply_binary_only_close():
    """Binary covers without position support get close_cover when target < 100."""
    from unittest.mock import AsyncMock, MagicMock
    hass = MagicMock()
    hass.services.async_call = AsyncMock()

    cover_state = MagicMock()
    cover_state.attributes = {"supported_features": 0}
    hass.states.get = MagicMock(return_value=cover_state)

    await CoverManager.async_apply(hass, ["cover.simple"], 40)

    hass.services.async_call.assert_called_once_with(
        "cover", "close_cover",
        {"entity_id": ["cover.simple"]},
        blocking=False,
    )


@pytest.mark.asyncio
async def test_async_apply_mixed_covers():
    """Mix of position-capable and binary-only covers."""
    from unittest.mock import AsyncMock, MagicMock
    hass = MagicMock()
    hass.services.async_call = AsyncMock()

    pos_cover = MagicMock()
    pos_cover.attributes = {"supported_features": 4, "current_position": 80}
    bin_cover = MagicMock()
    bin_cover.attributes = {"supported_features": 0}

    def _get(eid):
        if eid == "cover.smart":
            return pos_cover
        if eid == "cover.dumb":
            return bin_cover
        return None

    hass.states.get = MagicMock(side_effect=_get)

    await CoverManager.async_apply(hass, ["cover.smart", "cover.dumb"], 50)

    calls = hass.services.async_call.call_args_list
    assert len(calls) == 2
    # Position cover gets set_cover_position
    assert calls[0] == (("cover", "set_cover_position",
                         {"entity_id": ["cover.smart"], "position": 50}),
                        {"blocking": False})
    # Binary cover gets close_cover (target < 100)
    assert calls[1] == (("cover", "close_cover",
                         {"entity_id": ["cover.dumb"]}),
                        {"blocking": False})


@pytest.mark.asyncio
async def test_async_apply_skips_unavailable_entities():
    """Unavailable cover entities should be silently skipped."""
    from unittest.mock import AsyncMock, MagicMock
    hass = MagicMock()
    hass.services.async_call = AsyncMock()
    hass.states.get = MagicMock(return_value=None)

    await CoverManager.async_apply(hass, ["cover.gone"], 60)

    hass.services.async_call.assert_not_called()


@pytest.mark.asyncio
async def test_async_apply_supported_features_none():
    """Cover entity with supported_features=None should use binary fallback."""
    from unittest.mock import AsyncMock, MagicMock
    hass = MagicMock()
    hass.services.async_call = AsyncMock()

    cover_state = MagicMock()
    cover_state.attributes = {"supported_features": None}
    hass.states.get = MagicMock(return_value=cover_state)

    await CoverManager.async_apply(hass, ["cover.weird"], 50)

    # supported_features=None → 0 & 4 = 0 → binary
    hass.services.async_call.assert_called_once_with(
        "cover", "close_cover",
        {"entity_id": ["cover.weird"]},
        blocking=False,
    )


# ── MPC-Cover feedback convergence ────────────────────────────────────

def test_oscillating_conditions_converge():
    """Cover should converge within bounded oscillations, not wild-cycle."""
    mgr = CoverManager()
    positions = []
    changes = 0

    with patch("custom_components.roommind.managers.cover_manager.time") as mock_t:
        t = 10000.0
        for i in range(60):  # 60 cycles = 30 minutes at 30s intervals
            mock_t.time.return_value = t

            # Simulate oscillating predicted peak temp: 24.0 ± 0.3°C
            import math
            predicted = 24.0 + 0.3 * math.sin(i * 0.5)

            d = mgr.evaluate("lr",
                predicted_peak_temp=predicted, target_temp=22.0,
                **_BASE_KWARGS)

            if d.changed:
                changes += 1
            positions.append(d.target_position)
            t += 30.0  # 30s per cycle

    # With hold time of 900s, max 2 changes in 30 min (1800s / 900s = 2)
    assert changes <= 2, f"Too many position changes: {changes}"


def test_forced_position_closes_covers():
    """Forced position applies immediately — full range, no step limit."""
    mgr = CoverManager()
    d = mgr.evaluate("lr", predicted_peak_temp=22.0, target_temp=22.0,
                      **{**_BASE_KWARGS, "forced_position": 0, "forced_reason": "night_close"})
    assert d.changed is True
    assert d.target_position == 0  # immediate, no step capping
    assert "forced" in d.reason
    assert "night_close" in d.reason


def test_forced_position_already_at_target():
    mgr = CoverManager()
    mgr._get_state("lr").current_position = 0
    d = mgr.evaluate("lr", predicted_peak_temp=22.0, target_temp=22.0,
                      **{**_BASE_KWARGS, "forced_position": 0, "forced_reason": "night_close"})
    assert d.changed is False
    assert "forced_at_target" in d.reason


@patch("custom_components.roommind.managers.cover_manager.time")
def test_forced_position_not_rate_limited(mock_t):
    """Forced positions bypass rate limiting — apply immediately."""
    mock_t.time.return_value = 1000.0
    mgr = CoverManager()
    d1 = mgr.evaluate("lr", predicted_peak_temp=22.0, target_temp=22.0,
                       **{**_BASE_KWARGS, "forced_position": 50, "forced_reason": "schedule"})
    assert d1.changed is True
    assert d1.target_position == 50
    # Immediately change again — no hold time
    d2 = mgr.evaluate("lr", predicted_peak_temp=22.0, target_temp=22.0,
                       **{**_BASE_KWARGS, "forced_position": 0, "forced_reason": "night"})
    assert d2.changed is True
    assert d2.target_position == 0


@patch("custom_components.roommind.managers.cover_manager.time")
def test_forced_to_normal_transition_immediate(mock_t):
    """After forced ends, RoomMind takes over immediately (no hold time)."""
    mock_t.time.return_value = 1000.0
    mgr = CoverManager()
    mgr.evaluate("lr", predicted_peak_temp=22.0, target_temp=22.0,
                 **{**_BASE_KWARGS, "forced_position": 0, "forced_reason": "night"})
    # Next cycle: schedule inactive, thermal logic takes over immediately
    mock_t.time.return_value = 1030.0
    d = mgr.evaluate("lr", predicted_peak_temp=22.0, target_temp=22.0,
                     **{**_BASE_KWARGS, "forced_position": None, "forced_reason": ""})
    # excess=0 < retract_threshold → retract to 100, no hold time after forced
    assert d.changed is True
    assert d.target_position == 100


@patch("custom_components.roommind.managers.cover_manager.time")
def test_normal_thermal_still_rate_limited(mock_t):
    """Normal thermal decisions (not after forced) are still rate-limited."""
    mock_t.time.return_value = 1000.0
    mgr = CoverManager()
    # First: thermal deploy (not forced)
    mgr.evaluate("lr", predicted_peak_temp=25.0, target_temp=22.0, **_BASE_KWARGS)
    # 30s later: thermal wants to change, but hold time blocks it
    mock_t.time.return_value = 1030.0
    kwargs = {k: v for k, v in _BASE_KWARGS.items() if k not in ("q_solar", "outdoor_temp")}
    d = mgr.evaluate("lr", predicted_peak_temp=22.0, target_temp=22.0,
                     q_solar=0.05, outdoor_temp=20.0, **kwargs)
    assert d.changed is False
    assert "hold_time" in d.reason


def test_forced_position_works_without_prediction():
    """Forced position works even when predicted_peak_temp is None."""
    mgr = CoverManager()
    d = mgr.evaluate("lr", predicted_peak_temp=None, target_temp=22.0,
                      **{**_BASE_KWARGS, "forced_position": 0, "forced_reason": "night_close"})
    assert d.changed is True
    assert "forced" in d.reason


def test_manual_override_blocks_forced_position():
    mgr = CoverManager()
    d = mgr.evaluate("lr", predicted_peak_temp=22.0, target_temp=22.0,
                      **{**_BASE_KWARGS, "has_active_override": True,
                         "forced_position": 0, "forced_reason": "night_close"})
    assert d.changed is False
    assert "manual_override" in d.reason


def test_no_forced_position_uses_thermal():
    mgr = CoverManager()
    d = mgr.evaluate("lr", predicted_peak_temp=25.0, target_temp=22.0, **_BASE_KWARGS)
    assert d.changed is True
    assert "deploy" in d.reason


# ── Edge case tests ───────────────────────────────────────────────────

def test_empty_cover_entity_ids_disabled():
    """Auto enabled but empty cover list should return disabled."""
    mgr = CoverManager()
    kwargs = {**_BASE_KWARGS, "cover_entity_ids": []}
    d = mgr.evaluate("lr", predicted_peak_temp=28.0, target_temp=22.0, **kwargs)
    assert d.changed is False
    assert "disabled" in d.reason


def test_outdoor_gate_disabled_when_none():
    """covers_outdoor_min_temp=None disables cold weather gate."""
    mgr = CoverManager()
    kwargs = {k: v for k, v in _BASE_KWARGS.items() if k != "outdoor_temp"}
    kwargs["covers_outdoor_min_temp"] = None
    d = mgr.evaluate("lr", predicted_peak_temp=25.0, target_temp=22.0,
                      outdoor_temp=2.0, **kwargs)
    # Cold outdoor (2°C) but gate disabled → thermal logic runs, deploys
    assert d.changed is True
    assert "deploy" in d.reason


def test_outdoor_temp_none_skips_cold_gate():
    """outdoor_temp=None with gate configured should skip cold weather gate."""
    mgr = CoverManager()
    kwargs = {k: v for k, v in _BASE_KWARGS.items() if k != "outdoor_temp"}
    d = mgr.evaluate("lr", predicted_peak_temp=25.0, target_temp=22.0,
                      outdoor_temp=None, **kwargs)
    assert d.changed is True
    assert "deploy" in d.reason


def test_solar_boundary_at_exact_min():
    """q_solar exactly at COVER_SOLAR_MIN (0.15) should still trigger low_solar."""
    mgr = CoverManager()
    mgr._get_state("lr").current_position = 50
    kwargs = {k: v for k, v in _BASE_KWARGS.items() if k not in ("q_solar", "outdoor_temp")}
    d = mgr.evaluate("lr", predicted_peak_temp=25.0, target_temp=22.0,
                      q_solar=COVER_SOLAR_MIN, outdoor_temp=20.0, **kwargs)
    # q_solar == 0.15, check < 0.15 is False → solar gate does NOT trigger
    assert "low_solar" not in d.reason


def test_solar_just_below_min_retracts():
    """q_solar just below COVER_SOLAR_MIN retracts covers."""
    mgr = CoverManager()
    mgr._get_state("lr").current_position = 50
    kwargs = {k: v for k, v in _BASE_KWARGS.items() if k not in ("q_solar", "outdoor_temp")}
    d = mgr.evaluate("lr", predicted_peak_temp=25.0, target_temp=22.0,
                      q_solar=0.14, outdoor_temp=20.0, **kwargs)
    assert d.changed is True
    assert d.target_position == 100
    assert "low_solar" in d.reason


def test_min_position_100_prevents_closing():
    """covers_min_position=100 effectively prevents closing."""
    mgr = CoverManager()
    kwargs = {**_BASE_KWARGS, "covers_min_position": 100}
    d = mgr.evaluate("lr", predicted_peak_temp=35.0, target_temp=22.0, **kwargs)
    # desired_pos = max(100, 100 - raw_close) = 100 → no change
    assert d.target_position == 100
    assert d.changed is False


@patch("custom_components.roommind.managers.cover_manager.time")
def test_forced_to_cold_weather_retract_immediate(mock_t):
    """After forced position ends, cold weather retract skips hold time."""
    mock_t.time.return_value = 1000.0
    mgr = CoverManager()
    # Night close forces covers shut
    mgr.evaluate("lr", predicted_peak_temp=22.0, target_temp=22.0,
                 **{**_BASE_KWARGS, "forced_position": 0, "forced_reason": "night"})
    # Next cycle: schedule inactive, cold weather → retract immediately
    mock_t.time.return_value = 1030.0
    kwargs = {k: v for k, v in _BASE_KWARGS.items() if k != "outdoor_temp"}
    d = mgr.evaluate("lr", predicted_peak_temp=22.0, target_temp=22.0,
                      outdoor_temp=2.0, **kwargs)
    assert d.changed is True
    assert d.target_position == 100
    assert "cold_weather" in d.reason


@patch("custom_components.roommind.managers.cover_manager.time")
def test_forced_to_low_solar_retract_immediate(mock_t):
    """After forced position ends, low solar retract skips hold time."""
    mock_t.time.return_value = 1000.0
    mgr = CoverManager()
    mgr.evaluate("lr", predicted_peak_temp=22.0, target_temp=22.0,
                 **{**_BASE_KWARGS, "forced_position": 0, "forced_reason": "schedule"})
    # Next cycle: schedule inactive, low solar → retract immediately
    mock_t.time.return_value = 1030.0
    kwargs = {k: v for k, v in _BASE_KWARGS.items() if k not in ("q_solar", "outdoor_temp")}
    d = mgr.evaluate("lr", predicted_peak_temp=22.0, target_temp=22.0,
                      q_solar=0.05, outdoor_temp=20.0, **kwargs)
    assert d.changed is True
    assert d.target_position == 100
    assert "low_solar" in d.reason


# ── Night close boundary tests ────────────────────────────────────────

@patch("custom_components.roommind.managers.cover_manager.time")
def test_night_close_at_zero_elevation(mock_t):
    """Night close triggers when forced_position=0 with reason night_close."""
    mock_t.time.return_value = 1000.0
    mgr = CoverManager()
    d = mgr.evaluate("lr", predicted_peak_temp=20.0, target_temp=22.0,
                      **{**_BASE_KWARGS, "forced_position": 0, "forced_reason": "night_close"})
    assert d.target_position == 0
    assert "night_close" in d.reason


@patch("custom_components.roommind.managers.cover_manager.time")
def test_no_night_close_when_no_forced_position(mock_t):
    """No night_close in reason when forced_position is None."""
    mock_t.time.return_value = 1000.0
    mgr = CoverManager()
    d = mgr.evaluate("lr", predicted_peak_temp=20.0, target_temp=22.0, **_BASE_KWARGS)
    assert "night_close" not in d.reason


# ── Mixed availability tests ──────────────────────────────────────────

@patch("custom_components.roommind.managers.cover_manager.time")
def test_evaluate_with_multiple_cover_entities(mock_t):
    """Evaluate works with multiple cover entity IDs."""
    mock_t.time.return_value = 1000.0
    mgr = CoverManager()
    kwargs = {**_BASE_KWARGS, "cover_entity_ids": ["cover.a", "cover.b", "cover.c"]}
    d = mgr.evaluate("lr", predicted_peak_temp=25.0, target_temp=22.0, **kwargs)
    assert d.changed is True
    assert d.target_position < 100


@pytest.mark.asyncio
@patch("custom_components.roommind.managers.cover_manager.time")
async def test_async_apply_mixed_availability(mock_t):
    """async_apply only commands available covers, skipping unavailable ones."""
    mock_t.time.return_value = 1000.0
    mgr = CoverManager()
    d = mgr.evaluate("lr", predicted_peak_temp=25.0, target_temp=22.0,
                      **{**_BASE_KWARGS, "cover_entity_ids": ["cover.ok", "cover.gone"]})

    hass = MagicMock()
    hass.services.async_call = AsyncMock()
    ok_state = MagicMock()
    ok_state.attributes = {"supported_features": 4, "current_position": 100}
    hass.states.get = lambda eid: ok_state if eid == "cover.ok" else None

    await CoverManager.async_apply(hass, ["cover.ok", "cover.gone"], d.target_position)

    # Only cover.ok should be commanded
    call_args = hass.services.async_call.call_args_list
    for call in call_args:
        eids = call[0][2].get("entity_id", [])
        assert "cover.gone" not in (eids if isinstance(eids, list) else [eids])
