"""Tests for mold_manager.py — mold risk detection and prevention manager."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.roommind.const import MOLD_PREVENTION_RELEASE_MINUTES
from custom_components.roommind.managers import mold_manager
from custom_components.roommind.managers.mold_manager import MoldManager

RELEASE_S = MOLD_PREVENTION_RELEASE_MINUTES * 60


@pytest.fixture
def mm(hass):
    return MoldManager(hass)


@pytest.fixture
def clock(monkeypatch):
    """The mold manager's clock, moved by the test."""
    now = {"t": 1_000_000.0}
    monkeypatch.setattr(mold_manager, "time", SimpleNamespace(time=lambda: now["t"]))
    return now


def _settings_prevention_notify(**overrides):
    """Return settings with mold prevention + notification enabled."""
    s = {
        "mold_detection_enabled": True,
        "mold_prevention_enabled": True,
        "mold_prevention_notify_enabled": True,
        "mold_notifications_enabled": True,
        "mold_prevention_intensity": "medium",
        "mold_prevention_notify_targets": ["notify.mobile"],
        "mold_humidity_threshold": 70.0,
        "mold_sustained_minutes": 0,
    }
    s.update(overrides)
    return s


# --- prevention activation notification (lines 143-156) ---


@pytest.mark.asyncio
async def test_prevention_activation_sends_notification(mm):
    """When prevention activates for first time, notification is sent."""
    settings = _settings_prevention_notify()

    with (
        patch(
            "custom_components.roommind.managers.mold_manager.calculate_mold_risk",
            return_value=("warning", 75.0, 14.5),
        ),
        patch(
            "custom_components.roommind.managers.mold_manager.mold_prevention_delta",
            return_value=2.0,
        ),
        patch(
            "custom_components.roommind.managers.mold_manager.async_send_mold_notification",
            new_callable=AsyncMock,
        ) as mock_notify,
    ):
        result = await mm.evaluate(
            area_id="living",
            area_name="Living Room",
            current_temp=18.0,
            current_humidity=75.0,
            outdoor_temp=-5.0,
            settings=settings,
            celsius_delta_to_ha_fn=lambda x: x,
            ha_temp_unit_str_fn=lambda: "°C",
        )

    assert result.prevention_active is True
    assert result.prevention_delta == 2.0
    assert mock_notify.call_count >= 1
    # Check that prevention notification was sent (not just detection)
    prevention_call = [c for c in mock_notify.call_args_list if c.kwargs.get("tag_suffix") == "prevention"]
    assert len(prevention_call) == 1


@pytest.mark.asyncio
async def test_prevention_notification_not_sent_without_helper_fns(mm):
    """Prevention notification skipped if celsius_delta_to_ha_fn is None."""
    settings = _settings_prevention_notify()

    with (
        patch(
            "custom_components.roommind.managers.mold_manager.calculate_mold_risk",
            return_value=("warning", 75.0, 14.5),
        ),
        patch(
            "custom_components.roommind.managers.mold_manager.mold_prevention_delta",
            return_value=2.0,
        ),
        patch(
            "custom_components.roommind.managers.mold_manager.async_send_mold_notification",
            new_callable=AsyncMock,
        ) as mock_notify,
    ):
        result = await mm.evaluate(
            area_id="living",
            area_name="Living Room",
            current_temp=18.0,
            current_humidity=75.0,
            outdoor_temp=-5.0,
            settings=settings,
            celsius_delta_to_ha_fn=None,
            ha_temp_unit_str_fn=None,
        )

    assert result.prevention_active is True
    # Only detection notification, no prevention notification
    prevention_calls = [c for c in mock_notify.call_args_list if c.kwargs.get("tag_suffix") == "prevention"]
    assert len(prevention_calls) == 0


@pytest.mark.asyncio
async def test_prevention_notification_not_sent_on_second_evaluation(mm):
    """Prevention notification only sent on first activation, not repeated."""
    settings = _settings_prevention_notify()

    with (
        patch(
            "custom_components.roommind.managers.mold_manager.calculate_mold_risk",
            return_value=("warning", 75.0, 14.5),
        ),
        patch(
            "custom_components.roommind.managers.mold_manager.mold_prevention_delta",
            return_value=2.0,
        ),
        patch(
            "custom_components.roommind.managers.mold_manager.async_send_mold_notification",
            new_callable=AsyncMock,
        ) as mock_notify,
    ):
        await mm.evaluate(
            area_id="living",
            area_name="Living Room",
            current_temp=18.0,
            current_humidity=75.0,
            outdoor_temp=-5.0,
            settings=settings,
            celsius_delta_to_ha_fn=lambda x: x,
            ha_temp_unit_str_fn=lambda: "°C",
        )
        mock_notify.reset_mock()

        await mm.evaluate(
            area_id="living",
            area_name="Living Room",
            current_temp=18.0,
            current_humidity=75.0,
            outdoor_temp=-5.0,
            settings=settings,
            celsius_delta_to_ha_fn=lambda x: x,
            ha_temp_unit_str_fn=lambda: "°C",
        )

    prevention_calls = [c for c in mock_notify.call_args_list if c.kwargs.get("tag_suffix") == "prevention"]
    assert len(prevention_calls) == 0


# --- remove_room (lines 182-185) ---


@pytest.mark.asyncio
async def test_remove_room_clears_state(mm):
    """remove_room cleans up all internal state for a room."""
    settings = _settings_prevention_notify()

    with (
        patch(
            "custom_components.roommind.managers.mold_manager.calculate_mold_risk",
            return_value=("warning", 75.0, 14.5),
        ),
        patch(
            "custom_components.roommind.managers.mold_manager.mold_prevention_delta",
            return_value=2.0,
        ),
        patch(
            "custom_components.roommind.managers.mold_manager.async_send_mold_notification",
            new_callable=AsyncMock,
        ),
    ):
        await mm.evaluate(
            area_id="living",
            area_name="Living Room",
            current_temp=18.0,
            current_humidity=75.0,
            outdoor_temp=-5.0,
            settings=settings,
            celsius_delta_to_ha_fn=lambda x: x,
            ha_temp_unit_str_fn=lambda: "°C",
        )

    assert "living" in mm._risk_since
    assert mm._prevention_active.get("living") is True

    mm.remove_room("living")

    assert "living" not in mm._risk_since
    assert "living" not in mm._prevention_active


def test_remove_room_no_op_for_unknown(mm):
    """remove_room on unknown area_id does not raise."""
    mm.remove_room("nonexistent")


# --- detection notification (tag_suffix="risk") ---


@pytest.mark.asyncio
async def test_detection_notification_sent_on_risk(mm):
    """When mold risk is detected, a notification with tag_suffix='risk' is sent."""
    settings = {
        "mold_detection_enabled": True,
        "mold_prevention_enabled": False,
        "mold_notifications_enabled": True,
        "mold_humidity_threshold": 70.0,
        "mold_sustained_minutes": 0,
    }

    with (
        patch(
            "custom_components.roommind.managers.mold_manager.calculate_mold_risk",
            return_value=("warning", 75.0, 14.5),
        ),
        patch(
            "custom_components.roommind.managers.mold_manager.async_send_mold_notification",
            new_callable=AsyncMock,
        ) as mock_notify,
    ):
        result = await mm.evaluate(
            area_id="living",
            area_name="Living Room",
            current_temp=18.0,
            current_humidity=75.0,
            outdoor_temp=-5.0,
            settings=settings,
        )

    assert result.risk_level == "warning"
    assert mock_notify.call_count == 1
    assert mock_notify.call_args.kwargs["tag_suffix"] == "risk"


# --- hysteresis deactivation ---


@pytest.mark.asyncio
async def test_hysteresis_deactivation(mm, clock):
    """Prevention deactivates when surface_rh drops below threshold minus hysteresis."""
    settings = _settings_prevention_notify()

    # First call: activate prevention
    with (
        patch(
            "custom_components.roommind.managers.mold_manager.calculate_mold_risk",
            return_value=("warning", 75.0, 14.5),
        ),
        patch(
            "custom_components.roommind.managers.mold_manager.mold_prevention_delta",
            return_value=2.0,
        ),
        patch(
            "custom_components.roommind.managers.mold_manager.async_send_mold_notification",
            new_callable=AsyncMock,
        ),
    ):
        r1 = await mm.evaluate(
            area_id="living",
            area_name="Living Room",
            current_temp=18.0,
            current_humidity=75.0,
            outdoor_temp=-5.0,
            settings=settings,
            celsius_delta_to_ha_fn=lambda x: x,
            ha_temp_unit_str_fn=lambda: "°C",
        )
    assert r1.prevention_active is True
    assert mm._prevention_active["living"] is True

    # Below MOLD_SURFACE_RH_WARNING - MOLD_HYSTERESIS (70 - 5 = 65) the boost still holds for
    # MOLD_PREVENTION_RELEASE_MINUTES, then it ends
    clear = {"current_temp": 21.0, "current_humidity": 50.0, "outdoor_temp": 5.0}
    with patch(
        "custom_components.roommind.managers.mold_manager.calculate_mold_risk",
        return_value=("ok", 60.0, 17.0),
    ):
        held = await mm.evaluate(area_id="living", area_name="Living Room", settings=settings, **clear)
    assert held.prevention_active is True
    clock["t"] += RELEASE_S
    with (
        patch(
            "custom_components.roommind.managers.mold_manager.calculate_mold_risk",
            return_value=("ok", 60.0, 17.0),
        ),
        patch(
            "custom_components.roommind.managers.mold_manager.dismiss_mold_notification",
        ) as mock_dismiss,
    ):
        r2 = await mm.evaluate(
            area_id="living",
            area_name="Living Room",
            current_temp=21.0,
            current_humidity=50.0,
            outdoor_temp=5.0,
            settings=settings,
            celsius_delta_to_ha_fn=lambda x: x,
            ha_temp_unit_str_fn=lambda: "°C",
        )

    assert r2.prevention_active is False
    assert mm._prevention_active["living"] is False
    # Both risk and prevention notifications dismissed
    assert mock_dismiss.call_count == 2
    dismiss_suffixes = [c[0][2] for c in mock_dismiss.call_args_list]
    assert "risk" in dismiss_suffixes
    assert "prevention" in dismiss_suffixes


# --- sustained_minutes delays notification ---


@pytest.mark.asyncio
async def test_sustained_minutes_delays_notification(mm):
    """With sustained_minutes > 0, notification is not sent until risk persists long enough."""
    settings = {
        "mold_detection_enabled": True,
        "mold_prevention_enabled": False,
        "mold_notifications_enabled": True,
        "mold_humidity_threshold": 70.0,
        "mold_sustained_minutes": 5,
    }

    with (
        patch(
            "custom_components.roommind.managers.mold_manager.calculate_mold_risk",
            return_value=("warning", 75.0, 14.5),
        ),
        patch(
            "custom_components.roommind.managers.mold_manager.async_send_mold_notification",
            new_callable=AsyncMock,
        ) as mock_notify,
        patch("custom_components.roommind.managers.mold_manager.time") as mock_time,
    ):
        # First call at t=1000: risk just started
        mock_time.time.return_value = 1000.0
        await mm.evaluate(
            area_id="living",
            area_name="Living Room",
            current_temp=18.0,
            current_humidity=75.0,
            outdoor_temp=-5.0,
            settings=settings,
        )
        assert mock_notify.call_count == 0, "Should not notify yet (sustained_minutes not met)"

        # Second call at t=1100 (100s later, still < 5 min = 300s)
        mock_time.time.return_value = 1100.0
        await mm.evaluate(
            area_id="living",
            area_name="Living Room",
            current_temp=18.0,
            current_humidity=75.0,
            outdoor_temp=-5.0,
            settings=settings,
        )
        assert mock_notify.call_count == 0, "Still not sustained long enough"

        # Third call at t=1301 (301s > 300s)
        mock_time.time.return_value = 1301.0
        await mm.evaluate(
            area_id="living",
            area_name="Living Room",
            current_temp=18.0,
            current_humidity=75.0,
            outdoor_temp=-5.0,
            settings=settings,
        )
        assert mock_notify.call_count == 1, "Now notification should be sent"


# --- dismiss notification on risk clear ---


@pytest.mark.asyncio
async def test_dismiss_notification_on_risk_clear(mm, clock):
    """When risk clears (surface_rh < threshold - hysteresis), dismiss is called."""
    settings = _settings_prevention_notify()

    # Activate prevention first
    with (
        patch(
            "custom_components.roommind.managers.mold_manager.calculate_mold_risk",
            return_value=("warning", 75.0, 14.5),
        ),
        patch(
            "custom_components.roommind.managers.mold_manager.mold_prevention_delta",
            return_value=2.0,
        ),
        patch(
            "custom_components.roommind.managers.mold_manager.async_send_mold_notification",
            new_callable=AsyncMock,
        ),
    ):
        await mm.evaluate(
            area_id="living",
            area_name="Living Room",
            current_temp=18.0,
            current_humidity=75.0,
            outdoor_temp=-5.0,
            settings=settings,
            celsius_delta_to_ha_fn=lambda x: x,
            ha_temp_unit_str_fn=lambda: "°C",
        )

    # Now clear risk, long enough to release the boost
    with patch(
        "custom_components.roommind.managers.mold_manager.calculate_mold_risk",
        return_value=("ok", 60.0, 17.0),
    ):
        await mm.evaluate(
            area_id="living",
            area_name="Living Room",
            current_temp=21.0,
            current_humidity=50.0,
            outdoor_temp=5.0,
            settings=settings,
        )
    clock["t"] += RELEASE_S
    with (
        patch(
            "custom_components.roommind.managers.mold_manager.calculate_mold_risk",
            return_value=("ok", 60.0, 17.0),
        ),
        patch(
            "custom_components.roommind.managers.mold_manager.dismiss_mold_notification",
        ) as mock_dismiss,
    ):
        await mm.evaluate(
            area_id="living",
            area_name="Living Room",
            current_temp=21.0,
            current_humidity=50.0,
            outdoor_temp=5.0,
            settings=settings,
        )

    # dismiss called for both "risk" and "prevention"
    assert mock_dismiss.call_count == 2


# --- detection disabled skips ---


@pytest.mark.asyncio
async def test_detection_disabled_skips(mm):
    """mold_detection_enabled=False and mold_prevention_enabled=False returns early with no risk."""
    settings = {
        "mold_detection_enabled": False,
        "mold_prevention_enabled": False,
    }

    result = await mm.evaluate(
        area_id="living",
        area_name="Living Room",
        current_temp=18.0,
        current_humidity=90.0,
        outdoor_temp=-5.0,
        settings=settings,
    )

    assert result.risk_level == "ok"
    assert result.surface_rh is None
    assert result.prevention_active is False


# --- no humidity returns early ---


@pytest.mark.asyncio
async def test_no_humidity_returns_early(mm):
    """current_humidity=None returns early with default MoldResult."""
    settings = {
        "mold_detection_enabled": True,
        "mold_prevention_enabled": True,
    }

    result = await mm.evaluate(
        area_id="living",
        area_name="Living Room",
        current_temp=18.0,
        current_humidity=None,
        outdoor_temp=-5.0,
        settings=settings,
    )

    assert result.risk_level == "ok"
    assert result.surface_rh is None
    assert result.prevention_active is False


# --- f_Rsi plumbing ---


@pytest.mark.asyncio
async def test_evaluate_passes_default_f_rsi_when_unset(mm):
    """When mold_f_rsi is missing from settings, the manager uses the default
    (0.80) and forwards it to calculate_mold_risk as f_rsi.
    """
    settings = {"mold_detection_enabled": True}

    with patch(
        "custom_components.roommind.managers.mold_manager.calculate_mold_risk",
        return_value=("ok", 55.0, 18.0),
    ) as mock_calc:
        await mm.evaluate(
            area_id="living",
            area_name="Living Room",
            current_temp=20.0,
            current_humidity=50.0,
            outdoor_temp=10.0,
            settings=settings,
        )

    mock_calc.assert_called_once()
    args, kwargs = mock_calc.call_args
    assert kwargs["f_rsi"] == 0.80


@pytest.mark.asyncio
async def test_evaluate_passes_custom_f_rsi_from_settings(mm):
    """When mold_f_rsi is provided in settings, the manager forwards it."""
    settings = {
        "mold_detection_enabled": True,
        "mold_f_rsi": 0.65,
    }

    with patch(
        "custom_components.roommind.managers.mold_manager.calculate_mold_risk",
        return_value=("warning", 80.0, 14.0),
    ) as mock_calc:
        await mm.evaluate(
            area_id="living",
            area_name="Living Room",
            current_temp=20.0,
            current_humidity=70.0,
            outdoor_temp=-5.0,
            settings=settings,
        )

    mock_calc.assert_called_once()
    args, kwargs = mock_calc.call_args
    assert kwargs["f_rsi"] == 0.65


async def _evaluate(mm, risk, surface_rh, humidity, settings):
    with (
        patch(
            "custom_components.roommind.managers.mold_manager.calculate_mold_risk",
            return_value=(risk, surface_rh, 15.0),
        ),
        patch(
            "custom_components.roommind.managers.mold_manager.mold_prevention_delta",
            return_value=2.0,
        ),
        patch(
            "custom_components.roommind.managers.mold_manager.async_send_mold_notification",
            new_callable=AsyncMock,
        ),
        patch("custom_components.roommind.managers.mold_manager.dismiss_mold_notification"),
    ):
        return await mm.evaluate(
            area_id="living",
            area_name="Living Room",
            current_temp=20.0,
            current_humidity=humidity,
            outdoor_temp=5.0,
            settings=settings,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("humidity", [58.0, 72.0], ids=["room_rh_ok", "room_rh_over_threshold"])
async def test_prevention_holds_inside_the_hysteresis_band(mm, clock, humidity):
    """Raising the target lowers the surface RH: just below the warning the boost must stay,
    else it switches off, the wall cools and it switches on again every few minutes."""
    settings = _settings_prevention_notify(mold_prevention_notify_enabled=False)
    assert (await _evaluate(mm, "warning", 71.0, 60.0, settings)).prevention_delta == 2.0
    held = await _evaluate(mm, "ok", 67.0, humidity, settings)
    assert held.prevention_active is True
    assert held.prevention_delta == 2.0
    assert (await _evaluate(mm, "ok", 64.0, 55.0, settings)).prevention_active is True
    clock["t"] += RELEASE_S
    released = await _evaluate(mm, "ok", 64.0, 55.0, settings)
    assert released.prevention_active is False
    assert released.prevention_delta == 0.0


@pytest.mark.asyncio
async def test_a_short_dip_below_the_band_does_not_end_the_boost(mm, clock):
    """A heater warms the air in minutes and the estimated surface RH drops with it, while the
    wall lags; only a dip that lasts MOLD_PREVENTION_RELEASE_MINUTES ends the boost."""
    settings = _settings_prevention_notify(mold_prevention_notify_enabled=False)
    await _evaluate(mm, "warning", 71.0, 60.0, settings)
    for _ in range(3):
        clock["t"] += RELEASE_S / 2
        assert (await _evaluate(mm, "ok", 63.5, 54.0, settings)).prevention_active is True
        clock["t"] += 180
        assert (await _evaluate(mm, "warning", 70.4, 61.0, settings)).prevention_active is True
    assert not mm._clear_since


@pytest.mark.asyncio
async def test_no_prevention_inside_the_band_when_it_was_not_running(mm):
    settings = _settings_prevention_notify(mold_prevention_notify_enabled=False)
    result = await _evaluate(mm, "ok", 67.0, 60.0, settings)
    assert result.prevention_active is False
    assert result.prevention_delta == 0.0


@pytest.mark.asyncio
async def test_prevention_switched_off_in_settings_releases_at_once(mm):
    settings = _settings_prevention_notify(mold_prevention_notify_enabled=False)
    await _evaluate(mm, "warning", 71.0, 60.0, settings)
    result = await _evaluate(mm, "ok", 67.0, 60.0, {**settings, "mold_prevention_enabled": False})
    assert result.prevention_active is False
    assert result.prevention_delta == 0.0
