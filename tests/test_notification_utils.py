"""Tests for notification_utils.py — notification sending and throttling."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.roommind.utils.notification_utils import (
    NotificationThrottler,
    dismiss_mold_notification,
    async_send_mold_notification,
)


# --- NotificationThrottler ---

class TestNotificationThrottler:
    def test_allows_first_send(self):
        """First send for a key should always be allowed."""
        throttler = NotificationThrottler()
        assert throttler.should_send("test_key", cooldown_seconds=3600) is True

    def test_blocks_within_cooldown(self):
        """Should block if cooldown has not elapsed."""
        throttler = NotificationThrottler()
        throttler.record_sent("test_key")
        assert throttler.should_send("test_key", cooldown_seconds=3600) is False

    def test_allows_after_cooldown(self):
        """Should allow after cooldown has elapsed."""
        throttler = NotificationThrottler()
        throttler._last_sent["test_key"] = time.time() - 3601
        assert throttler.should_send("test_key", cooldown_seconds=3600) is True

    def test_independent_keys(self):
        """Different keys have independent cooldowns."""
        throttler = NotificationThrottler()
        throttler.record_sent("key_a")
        assert throttler.should_send("key_a", cooldown_seconds=3600) is False
        assert throttler.should_send("key_b", cooldown_seconds=3600) is True

    def test_clear_resets_throttle(self):
        """Clearing a key allows immediate re-send."""
        throttler = NotificationThrottler()
        throttler.record_sent("test_key")
        assert throttler.should_send("test_key", cooldown_seconds=3600) is False
        throttler.clear("test_key")
        assert throttler.should_send("test_key", cooldown_seconds=3600) is True

    def test_clear_nonexistent_key_safe(self):
        """Clearing a key that was never recorded should not error."""
        throttler = NotificationThrottler()
        throttler.clear("nonexistent")  # should not raise


# --- async_send_mold_notification ---

@pytest.mark.asyncio
async def test_send_notification_with_targets():
    """Should call notify.send_message for each target."""
    hass = MagicMock()
    hass.services.async_call = AsyncMock()

    targets = [
        {"entity_id": "notify.mobile_app_kevin", "person_entity": "", "notify_when": "always"},
        {"entity_id": "notify.mobile_app_lisa", "person_entity": "", "notify_when": "always"},
    ]

    await async_send_mold_notification(
        hass, "living_room", "Wohnzimmer", targets,
        message="Test mold alert", title="RoomMind: Test",
    )

    assert hass.services.async_call.call_count == 2
    for call in hass.services.async_call.call_args_list:
        assert call[0][0] == "notify"
        assert call[0][1] == "send_message"
        assert call[0][2]["message"] == "Test mold alert"
        assert call[0][2]["data"]["tag"] == "roommind_mold_living_room_risk"


@pytest.mark.asyncio
async def test_send_notification_home_only_skips_away():
    """Target with home_only should be skipped when person is away."""
    hass = MagicMock()
    hass.services.async_call = AsyncMock()

    person_state = MagicMock()
    person_state.state = "not_home"
    hass.states.get = MagicMock(return_value=person_state)

    targets = [
        {"entity_id": "notify.mobile_app_kevin", "person_entity": "person.kevin", "notify_when": "home_only"},
    ]

    with patch(
        "custom_components.roommind.utils.notification_utils.async_create"
    ) as mock_persistent:
        await async_send_mold_notification(
            hass, "living_room", "Wohnzimmer", targets,
            message="Test", title="Test",
        )

    # notify service should NOT be called
    hass.services.async_call.assert_not_called()
    # Fallback persistent notification should be created (all targets skipped)
    mock_persistent.assert_called_once()


@pytest.mark.asyncio
async def test_send_notification_home_only_sends_when_home():
    """Target with home_only should be sent when person is home."""
    hass = MagicMock()
    hass.services.async_call = AsyncMock()

    person_state = MagicMock()
    person_state.state = "home"
    hass.states.get = MagicMock(return_value=person_state)

    targets = [
        {"entity_id": "notify.mobile_app_kevin", "person_entity": "person.kevin", "notify_when": "home_only"},
    ]

    await async_send_mold_notification(
        hass, "living_room", "Wohnzimmer", targets,
        message="Test", title="Test",
    )

    hass.services.async_call.assert_called_once()


@pytest.mark.asyncio
async def test_send_notification_no_targets_persistent():
    """Empty targets list → fallback to persistent notification."""
    hass = MagicMock()

    with patch(
        "custom_components.roommind.utils.notification_utils.async_create"
    ) as mock_create:
        await async_send_mold_notification(
            hass, "living_room", "Wohnzimmer", [],
            message="Test mold alert", title="RoomMind: Test",
        )

    mock_create.assert_called_once_with(
        hass,
        "Test mold alert",
        title="RoomMind: Test",
        notification_id="roommind_mold_living_room_risk",
    )


@pytest.mark.asyncio
async def test_send_notification_person_unavailable_treated_as_home():
    """Person entity unavailable → treated as home (fail-safe)."""
    hass = MagicMock()
    hass.services.async_call = AsyncMock()

    person_state = MagicMock()
    person_state.state = "unavailable"
    hass.states.get = MagicMock(return_value=person_state)

    targets = [
        {"entity_id": "notify.mobile_app_kevin", "person_entity": "person.kevin", "notify_when": "home_only"},
    ]

    await async_send_mold_notification(
        hass, "living_room", "Wohnzimmer", targets,
        message="Test", title="Test",
    )

    # Should send because unavailable is treated as home
    hass.services.async_call.assert_called_once()


@pytest.mark.asyncio
async def test_send_notification_custom_tag_suffix():
    """Custom tag_suffix should be reflected in notification tag."""
    hass = MagicMock()
    hass.services.async_call = AsyncMock()

    targets = [
        {"entity_id": "notify.mobile_app_kevin", "person_entity": "", "notify_when": "always"},
    ]

    await async_send_mold_notification(
        hass, "bedroom", "Schlafzimmer", targets,
        message="Prevention active", title="RoomMind",
        tag_suffix="prevention",
    )

    call_data = hass.services.async_call.call_args[0][2]["data"]
    assert call_data["tag"] == "roommind_mold_bedroom_prevention"


# --- dismiss_mold_notification ---

def test_dismiss_notification():
    """Should dismiss persistent notification with correct ID."""
    hass = MagicMock()

    with patch(
        "custom_components.roommind.utils.notification_utils.async_dismiss"
    ) as mock_dismiss:
        dismiss_mold_notification(hass, "living_room", "risk")

    mock_dismiss.assert_called_once_with(hass, "roommind_mold_living_room_risk")


def test_dismiss_notification_prevention_suffix():
    """Should use correct suffix for prevention notifications."""
    hass = MagicMock()

    with patch(
        "custom_components.roommind.utils.notification_utils.async_dismiss"
    ) as mock_dismiss:
        dismiss_mold_notification(hass, "bedroom", "prevention")

    mock_dismiss.assert_called_once_with(hass, "roommind_mold_bedroom_prevention")


@pytest.mark.asyncio
async def test_send_notification_skips_target_with_empty_entity_id():
    """Target with empty entity_id should be skipped (no notify call)."""
    hass = MagicMock()
    hass.services.async_call = AsyncMock()

    targets = [{"entity_id": "", "person_entity": "", "notify_when": "always"}]

    with patch(
        "custom_components.roommind.utils.notification_utils.async_create"
    ) as mock_create:
        await async_send_mold_notification(
            hass, "living_room", "Wohnzimmer", targets,
            message="Test", title="Test",
        )

    hass.services.async_call.assert_not_called()
    mock_create.assert_called_once()


@pytest.mark.asyncio
async def test_send_notification_service_exception_triggers_fallback():
    """If notify service raises, warning is logged and fallback is used."""
    hass = MagicMock()
    hass.services.async_call = AsyncMock(side_effect=Exception("service unavailable"))

    targets = [{"entity_id": "notify.test", "person_entity": "", "notify_when": "always"}]

    with patch(
        "custom_components.roommind.utils.notification_utils.async_create"
    ) as mock_create:
        await async_send_mold_notification(
            hass, "living_room", "Wohnzimmer", targets,
            message="Test", title="Test",
        )

    mock_create.assert_called_once()
