"""Mold risk detection and prevention manager for RoomMind."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.core import HomeAssistant

from ..const import (
    DEFAULT_MOLD_COOLDOWN_MINUTES,
    DEFAULT_MOLD_F_RSI,
    DEFAULT_MOLD_HUMIDITY_THRESHOLD,
    DEFAULT_MOLD_SUSTAINED_MINUTES,
    MOLD_HYSTERESIS,
    MOLD_PREVENTION_RELEASE_MINUTES,
    MOLD_RISK_CRITICAL,
    MOLD_RISK_OK,
    MOLD_RISK_WARNING,
    MOLD_SURFACE_RH_WARNING,
)
from ..utils.mold_utils import calculate_mold_risk, mold_prevention_delta
from ..utils.notification_utils import (
    NotificationThrottler,
    async_send_mold_notification,
    dismiss_mold_notification,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class MoldResult:
    """Result of mold risk evaluation for a room."""

    risk_level: str = MOLD_RISK_OK
    surface_rh: float | None = None
    surface_temp: float | None = None
    prevention_active: bool = False
    prevention_delta: float = 0.0


class MoldManager:
    """Manages mold risk detection and prevention per room."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._risk_since: dict[str, float] = {}
        self._prevention_active: dict[str, bool] = {}
        self._clear_since: dict[str, float] = {}
        self._throttler = NotificationThrottler()

    async def evaluate(
        self,
        area_id: str,
        area_name: str,
        current_temp: float | None,
        current_humidity: float | None,
        outdoor_temp: float | None,
        settings: dict,
        celsius_delta_to_ha_fn: Callable[[float], float] | None = None,
        ha_temp_unit_str_fn: Callable[[], str] | None = None,
        *,
        can_heat: bool = True,
    ) -> MoldResult:
        """Evaluate mold risk and prevention for a room.

        Returns a MoldResult with risk level, surface RH, and prevention state.
        Prevention needs a room that can heat; the risk is reported either way.
        """
        result = MoldResult()

        if not (settings.get("mold_detection_enabled") or settings.get("mold_prevention_enabled")):
            return result

        if current_humidity is None or current_temp is None:
            return result

        risk_level, surface_rh, surface_temp = calculate_mold_risk(
            current_temp,
            current_humidity,
            outdoor_temp,
            f_rsi=settings.get("mold_f_rsi", DEFAULT_MOLD_F_RSI),
        )
        result.risk_level = risk_level
        result.surface_rh = surface_rh
        result.surface_temp = surface_temp

        threshold = settings.get(
            "mold_humidity_threshold",
            DEFAULT_MOLD_HUMIDITY_THRESHOLD,
        )

        now = time.time()
        is_risky = current_humidity >= threshold or risk_level in (MOLD_RISK_WARNING, MOLD_RISK_CRITICAL)
        sustained_minutes = settings.get(
            "mold_sustained_minutes",
            DEFAULT_MOLD_SUSTAINED_MINUTES,
        )

        if is_risky:
            if area_id not in self._risk_since:
                self._risk_since[area_id] = now

            sustained_seconds = now - self._risk_since[area_id]

            # Notify if sustained long enough
            if (
                settings.get("mold_detection_enabled")
                and settings.get("mold_notifications_enabled", True)
                and sustained_seconds >= sustained_minutes * 60
            ):
                cooldown = (
                    settings.get(
                        "mold_notification_cooldown",
                        DEFAULT_MOLD_COOLDOWN_MINUTES,
                    )
                    * 60
                )
                if self._throttler.should_send(
                    f"detect_{area_id}",
                    cooldown,
                ):
                    targets = settings.get("mold_notification_targets", [])
                    await async_send_mold_notification(
                        self.hass,
                        area_id,
                        area_name,
                        targets,
                        message=(
                            f"Mold risk in {area_name}: "
                            f"{current_humidity:.0f}% humidity in the room, "
                            f"about {surface_rh:.0f}% at the coldest spot of the wall"
                        ),
                        title="RoomMind: mold risk",
                        tag_suffix="risk",
                    )
                    self._throttler.record_sent(f"detect_{area_id}")

        else:
            # Risk cleared -- use hysteresis for deactivation
            if surface_rh is not None and surface_rh < (MOLD_SURFACE_RH_WARNING - MOLD_HYSTERESIS):
                self._risk_since.pop(area_id, None)
                self._throttler.clear(f"detect_{area_id}")
                self._throttler.clear(f"prevent_{area_id}")

        await self._apply_prevention(
            result,
            area_id,
            area_name,
            risk_level,
            surface_rh,
            settings,
            celsius_delta_to_ha_fn,
            ha_temp_unit_str_fn,
            can_heat,
        )
        return result

    async def _apply_prevention(
        self,
        result: MoldResult,
        area_id: str,
        area_name: str,
        risk_level: str,
        surface_rh: float | None,
        settings: dict,
        celsius_delta_to_ha_fn: Callable[[float], float] | None,
        ha_temp_unit_str_fn: Callable[[], str] | None,
        can_heat: bool,
    ) -> None:
        """Raise the target while the wall is at risk, with hysteresis on the way out.

        The boost itself lowers the surface RH; switching it off right below the warning let the
        wall cool back over it within minutes. A running boost holds until the surface RH has been
        MOLD_HYSTERESIS below the warning for MOLD_PREVENTION_RELEASE_MINUTES: the estimate follows
        the room air, which a heater warms in minutes while the wall lags behind.
        """
        enabled = bool(settings.get("mold_prevention_enabled")) and can_heat
        was_active = self._prevention_active.get(area_id, False)
        at_risk = risk_level in (MOLD_RISK_WARNING, MOLD_RISK_CRITICAL)
        in_band = surface_rh is not None and surface_rh >= MOLD_SURFACE_RH_WARNING - MOLD_HYSTERESIS
        wanted = enabled and (at_risk or (was_active and in_band))
        if was_active and enabled and not wanted:
            clear_since = self._clear_since.setdefault(area_id, time.time())
            wanted = time.time() - clear_since < MOLD_PREVENTION_RELEASE_MINUTES * 60
        else:
            self._clear_since.pop(area_id, None)
        if not wanted:
            if was_active:
                self._prevention_active[area_id] = False
                self._clear_since.pop(area_id, None)
                dismiss_mold_notification(self.hass, area_id, "risk")
                dismiss_mold_notification(self.hass, area_id, "prevention")
            return

        intensity = settings.get("mold_prevention_intensity", "medium")
        result.prevention_delta = mold_prevention_delta(intensity)
        result.prevention_active = True
        if was_active:
            return
        self._prevention_active[area_id] = True
        if (
            settings.get("mold_prevention_notify_enabled")
            and settings.get("mold_notifications_enabled", True)
            and celsius_delta_to_ha_fn is not None
            and ha_temp_unit_str_fn is not None
        ):
            await async_send_mold_notification(
                self.hass,
                area_id,
                area_name,
                settings.get("mold_prevention_notify_targets", []),
                message=(
                    f"Mold prevention in {area_name}: "
                    f"heating target raised by "
                    f"{celsius_delta_to_ha_fn(result.prevention_delta):.0f}{ha_temp_unit_str_fn()}"
                ),
                title="RoomMind: mold prevention",
                tag_suffix="prevention",
            )
            self._throttler.record_sent(f"prevent_{area_id}")

    def remove_room(self, area_id: str) -> None:
        """Clean up state for a removed room."""
        self._risk_since.pop(area_id, None)
        self._prevention_active.pop(area_id, None)
        self._clear_since.pop(area_id, None)
        self._throttler.clear(f"detect_{area_id}")
        self._throttler.clear(f"prevent_{area_id}")
