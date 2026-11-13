"""Notification utilities for RoomMind.

Provides throttled notification sending to HA notify entities with
per-device home/away filtering and persistent-notification fallback.
"""

from __future__ import annotations

import logging
import time

from homeassistant.components.persistent_notification import (
    async_create,
    async_dismiss,
)
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

NOTIF_PREFIX = "roommind_mold_"


class NotificationThrottler:
    """Per-key in-memory throttling to prevent notification spam."""

    def __init__(self) -> None:
        self._last_sent: dict[str, float] = {}

    def should_send(self, key: str, cooldown_seconds: float) -> bool:
        """Return True if enough time has passed since the last send for *key*."""
        now = time.time()
        last = self._last_sent.get(key, 0.0)
        return (now - last) >= cooldown_seconds

    def record_sent(self, key: str) -> None:
        """Record that a notification was just sent for *key*."""
        self._last_sent[key] = time.time()

    def clear(self, key: str) -> None:
        """Clear throttle state for *key* (allows immediate re-send)."""
        self._last_sent.pop(key, None)


def _is_person_home(hass: HomeAssistant, person_entity: str) -> bool:
    """Check if a person entity is home (fail-safe: unknown/unavailable → home)."""
    state = hass.states.get(person_entity)
    if state is None or state.state in ("unavailable", "unknown"):
        return True  # fail-safe: treat as home
    return bool(state.state == "home")


async def async_send_mold_notification(
    hass: HomeAssistant,
    area_id: str,
    area_name: str,
    targets: list[dict],
    message: str,
    title: str,
    tag_suffix: str = "risk",
) -> None:
    """Send mold notification to configured targets.

    For each target dict ``{entity_id, person_entity, notify_when}``:
    - If ``notify_when == "home_only"`` and *person_entity* is set and the
      person is not home, the target is skipped.
    - Otherwise the notification goes to the notify entity via ``notify.send_message``,
      or to the legacy notify service of that name.

    If *targets* is empty, a persistent HA notification is created as fallback.

    Args:
        hass: Home Assistant instance.
        area_id: Room/area identifier (used for deduplication tags).
        area_name: Human-readable area name (for display in notifications).
        targets: List of notification target dicts.
        message: Notification body text.
        title: Notification title.
        tag_suffix: Suffix for deduplication tag (e.g. "risk", "prevention").
    """
    tag = f"{NOTIF_PREFIX}{area_id}_{tag_suffix}"
    notification_id = tag

    if not targets:
        # Fallback: persistent notification in HA sidebar
        async_create(hass, message, title=title, notification_id=notification_id)
        return

    sent_any = False
    for target in targets:
        entity_id = target.get("entity_id", "")
        if not entity_id:
            continue

        # Home/away filtering
        person_entity = target.get("person_entity", "")
        notify_when = target.get("notify_when", "always")
        if notify_when == "home_only" and person_entity:
            if not _is_person_home(hass, person_entity):
                _LOGGER.debug(
                    "Skipping mold notification to %s — person %s is away",
                    entity_id,
                    person_entity,
                )
                continue

        try:
            await _async_notify(hass, entity_id, message, title, tag)
            sent_any = True
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Failed to send mold notification to %s: %s", entity_id, err)

    if not sent_any:
        # All targets were skipped or failed → persistent fallback
        async_create(hass, message, title=title, notification_id=notification_id)


async def _async_notify(hass: HomeAssistant, target: str, message: str, title: str, tag: str) -> None:
    """Send to a notify entity, or to a legacy notify service typed in by hand.

    ``notify.send_message`` accepts only message and title and rejects ``data``
    (#502); a legacy service such as ``notify.mobile_app_<phone>`` has no state,
    and an entity service would only log it as missing. The legacy service takes
    ``data``, so the phone app replaces an older alert of the room instead of stacking it.
    """
    if hass.states.get(target) is not None:
        await hass.services.async_call(
            "notify", "send_message", {"entity_id": target, "message": message, "title": title}
        )
        return
    domain, _, service = target.partition(".")
    if domain != "notify" or not hass.services.has_service("notify", service):
        raise ValueError("no notify entity or service with this name")
    await hass.services.async_call(
        "notify",
        service,
        {"message": message, "title": title, "data": {"tag": tag, "group": "roommind"}},
    )


def dismiss_mold_notification(
    hass: HomeAssistant,
    area_id: str,
    tag_suffix: str = "risk",
) -> None:
    """Dismiss the persistent mold notification for a room."""
    notification_id = f"{NOTIF_PREFIX}{area_id}_{tag_suffix}"
    async_dismiss(hass, notification_id)
