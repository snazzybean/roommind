"""Setpoint changes made on a device itself (#259).

RoomMind writes a setpoint to every device it controls and sends it again when
the device reports something else, so a turn of the TRV dial or a press on the
AC remote is undone within one cycle. Rooms that opt in take such a change over
as an override instead.

State updates from Zigbee or cloud integrations carry no trace of who changed a
setpoint, not even the echo of RoomMind's own command. The tracker therefore
records every climate command RoomMind sends (``EVENT_CALL_SERVICE`` with the
RoomMind context) and judges by value: a reported setpoint that moved away from
the last one seen, is no value RoomMind sent and the device has not shown yet,
and did not come with a mode switch RoomMind sent was changed by someone else.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from homeassistant.const import ATTR_DOMAIN, ATTR_SERVICE, EVENT_CALL_SERVICE
from homeassistant.core import Event, HomeAssistant, callback

from ..const import (
    DEVICE_SETPOINT_ECHO_SECONDS,
    DEVICE_SETPOINT_GAP_SECONDS,
    DEVICE_SETPOINT_MODE_REPORT_SECONDS,
    DEVICE_SETPOINT_SETTLE_SECONDS,
    ROOMMIND_CONTEXT_ID,
)

SETPOINT_ATTRS = ("temperature", "target_temp_low", "target_temp_high")

_ATTR_SERVICE_DATA = "service_data"


def _as_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


_ANY_ON = "*on"  # turn_on: any mode but off


def _mode_switched_to(service: str, data: Mapping[str, Any], current: str | None) -> str | None:
    """The hvac mode a command switches the device to, None if it keeps the current one."""
    if service == "turn_off":
        return "off" if current != "off" else None
    if service == "turn_on":
        return _ANY_ON if current in (None, "off") else None
    mode = data.get("hvac_mode")
    return mode if mode is not None and mode != current else None


def _shows(mode: str, hvac_state: str) -> bool:
    return hvac_state != "off" if mode == _ANY_ON else hvac_state == mode


class _ModeSwitch:
    """A mode switch RoomMind sent, until the device shows it."""

    def __init__(self, at: float, mode: str) -> None:
        self.at = at
        self.mode = mode
        self.shown = False


class DeviceSetpointTracker:
    """Tells setpoint changes made on a device apart from RoomMind's own commands."""

    def __init__(self, now: Callable[[], float]) -> None:
        self._now = now
        # {entity_id: last mode switch RoomMind sent}
        self._switch: dict[str, _ModeSwitch] = {}
        # {(entity_id, attr): [(time, value), ...]} setpoints RoomMind sent and the device has not shown yet
        self._sent: dict[tuple[str, str], list[tuple[float, float]]] = {}
        # {(entity_id, attr): (value reported at the last observation, its time)}
        self._seen: dict[tuple[str, str], tuple[float, float]] = {}
        # {entity_id: (hvac state at the last observation, when it was first seen)}
        self._state: dict[str, tuple[str, float]] = {}

    def async_track(self, hass: HomeAssistant) -> Callable[[], None]:
        """Record every climate command RoomMind sends from now on; returns the unsubscribe."""

        @callback
        def _is_climate_call(event_data: Mapping[str, Any]) -> bool:
            return bool(event_data.get(ATTR_DOMAIN) == "climate")

        @callback
        def _record(event: Event) -> None:
            if event.context.parent_id != ROOMMIND_CONTEXT_ID:
                return
            data = event.data.get(_ATTR_SERVICE_DATA) or {}
            service = event.data.get(ATTR_SERVICE, "")
            eids = data.get("entity_id")
            for eid in [eids] if isinstance(eids, str) else list(eids or []):
                # Fired before the service runs, so the state is still the one the command changes
                state = hass.states.get(eid)
                self.note_command(eid, service, data, switch_to=_mode_switched_to(service, data, state and state.state))

        unsub: Callable[[], None] = hass.bus.async_listen(EVENT_CALL_SERVICE, _record, event_filter=_is_climate_call)
        return unsub

    def note_command(
        self, entity_id: str, service: str, data: Mapping[str, Any], *, switch_to: str | None = None
    ) -> None:
        """Remember a command RoomMind sent to *entity_id*; *switch_to* is the mode it switches to."""
        now = self._now()
        pending = self._switch.get(entity_id)
        # Resent every cycle while the device does not show it yet; the first send starts the wait
        if switch_to is not None and not (pending is not None and pending.mode == switch_to and not pending.shown):
            self._switch[entity_id] = _ModeSwitch(now, switch_to)
        if service != "set_temperature":
            return
        for attr in SETPOINT_ATTRS:
            value = _as_float(data.get(attr))
            if value is not None:
                recent = [s for s in self._sent.get((entity_id, attr), []) if now - s[0] < DEVICE_SETPOINT_ECHO_SECONDS]
                self._sent[(entity_id, attr)] = [*recent, (now, value)]

    def _settling(self, entity_id: str, hvac_state: str, now: float) -> bool:
        """True while a setpoint report may still be the device's answer to a mode switch RoomMind sent.

        Until the device shows the commanded mode (it may report the restored setpoint
        first), and for a short while after it does. A mode someone else picked on the
        device does not count, nor does a later report in RoomMind's mode.
        """
        last_state = self._state.get(entity_id)
        if last_state is None or last_state[0] != hvac_state:
            last_state = self._state[entity_id] = (hvac_state, now)
        switch = self._switch.get(entity_id)
        if switch is None or now - switch.at >= DEVICE_SETPOINT_SETTLE_SECONDS:
            return False
        if not switch.shown:
            if not _shows(switch.mode, hvac_state):
                return True
            switch.shown = True
        return _shows(switch.mode, hvac_state) and now - last_state[1] < DEVICE_SETPOINT_MODE_REPORT_SECONDS

    def observe(
        self,
        entity_id: str,
        hvac_state: str,
        attributes: Mapping[str, Any],
        tolerance: float,
        echo_tolerance: float,
    ) -> dict[str, tuple[float, float]]:
        """Fold in the device's reported state; returns ``{attr: (before, after)}`` changed on the device.

        Values are in the device's unit. *tolerance* is the smallest change that counts,
        *echo_tolerance* how far the device may round a value RoomMind sent.
        """
        now = self._now()
        settling = self._settling(entity_id, hvac_state, now)
        changes: dict[str, tuple[float, float]] = {}
        for attr in SETPOINT_ATTRS:
            value = _as_float(attributes.get(attr))
            if value is None:
                continue
            key = (entity_id, attr)
            last = self._seen.get(key)
            before = last[0] if last is not None and now - last[1] < DEVICE_SETPOINT_GAP_SECONDS else None
            self._seen[key] = (value, now)
            sent = [s for s in self._sent.get(key, []) if now - s[0] < DEVICE_SETPOINT_ECHO_SECONDS]
            echo = next((i for i in range(len(sent) - 1, -1, -1) if abs(value - sent[i][1]) <= echo_tolerance), None)
            # A shown send and everything sent before it can no longer explain a later value
            self._sent[key] = sent if echo is None else sent[echo + 1 :]
            if echo is not None or before is None or settling or abs(value - before) <= tolerance:
                continue
            changes[attr] = (before, value)
        return changes

    def forget_readings(self, entity_id: str) -> None:
        """Drop the last readings of a device that went unavailable: it may come back with factory values."""
        for attr in SETPOINT_ATTRS:
            self._seen.pop((entity_id, attr), None)

    def prune(self, keep: set[str]) -> None:
        """Forget devices no room uses any more."""
        self._switch = {eid: s for eid, s in self._switch.items() if eid in keep}
        self._state = {eid: s for eid, s in self._state.items() if eid in keep}
        self._sent = {key: s for key, s in self._sent.items() if key[0] in keep}
        self._seen = {key: v for key, v in self._seen.items() if key[0] in keep}
