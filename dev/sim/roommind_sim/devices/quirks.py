"""Device quirks reported in issues. Add a class + register it to model a new one."""

from __future__ import annotations

from collections import deque
from typing import Any

from .base import CommandResult, SimDevice

QUIRKS: dict[str, type[Quirk]] = {}


def register(name: str):  # noqa: ANN201
    def deco(cls: type[Quirk]) -> type[Quirk]:
        cls.name = name
        QUIRKS[name] = cls
        return cls

    return deco


def make_quirk(spec: dict[str, Any]) -> Quirk:
    kind = spec.get("type")
    if kind not in QUIRKS:
        raise ValueError(f"unknown quirk {kind!r} (known: {sorted(QUIRKS)})")
    return QUIRKS[kind]({k: v for k, v in spec.items() if k != "type"})


class Quirk:
    name = ""

    def __init__(self, params: dict[str, Any]) -> None:
        self.p = params

    def before_command(self, dev: SimDevice, service: str, data: dict[str, Any], now: float) -> CommandResult | None:
        return None

    def after_command(
        self, dev: SimDevice, service: str, data: dict[str, Any], now: float, result: CommandResult
    ) -> None:
        return None

    def on_step(self, dev: SimDevice, dt: float, now: float) -> None:
        return None

    def transform_attributes(self, dev: SimDevice, attrs: dict[str, Any], now: float) -> dict[str, Any]:
        return attrs

    def state_override(self, dev: SimDevice, now: float) -> str | None:
        return None

    def snapshot(self) -> dict[str, Any]:
        return {}

    def restore(self, data: dict[str, Any]) -> None:
        return None


def _temps(data: dict[str, Any]) -> list[float]:
    return [float(data[k]) for k in ("temperature", "target_temp_low", "target_temp_high") if data.get(k) is not None]


@register("reject_values")
class RejectValues(Quirk):
    """Device-side validation (#396 Dyson Kelvin range, #162 Sonoff rejects 0)."""

    def before_command(self, dev, service, data, now):  # noqa: ANN001, ANN201
        if service != "set_temperature":
            return None
        message = self.p.get("message", "value rejected by device")
        for value in _temps(data):
            if value in [float(v) for v in self.p.get("values", [])]:
                return CommandResult(False, message)
            kelvin = self.p.get("kelvin_range")
            if kelvin and not (kelvin[0] <= dev.to_c(value) + 273.15 <= kelvin[1]):
                return CommandResult(False, message)
        return None


@register("duty_cycle")
class DutyCycle(Quirk):
    """Radio duty-cycle budget (#317 Homematic): too many frames per hour get rejected."""

    def __init__(self, params: dict[str, Any]) -> None:
        super().__init__(params)
        self.sent: deque[float] = deque()

    def before_command(self, dev, service, data, now):  # noqa: ANN001, ANN201
        while self.sent and now - self.sent[0] > 3600:
            self.sent.popleft()
        if len(self.sent) >= int(self.p.get("budget_per_hour", 30)):
            return CommandResult(False, self.p.get("reject_message", "duty cycle exhausted"))
        self.sent.append(now)
        return None

    def snapshot(self):  # noqa: ANN201
        return {"sent": list(self.sent)}

    def restore(self, data):  # noqa: ANN001, ANN201
        self.sent = deque(data.get("sent", []))


@register("command_side_effect")
class CommandSideEffect(Quirk):
    """A command shortly after another has a side effect (#337 Midea turns off)."""

    def __init__(self, params: dict[str, Any]) -> None:
        super().__init__(params)
        self.last_after: float | None = None

    def after_command(self, dev, service, data, now, result):  # noqa: ANN001, ANN201
        if not result.ok:
            return
        if (
            service == self.p.get("then")
            and self.last_after is not None
            and now - self.last_after <= float(self.p.get("within_s", 2))
        ):
            if self.p.get("effect", "turn_off") == "turn_off":
                dev.force_mode("off")
        if service == self.p.get("after") or (
            service == "set_temperature" and data.get("hvac_mode") and self.p.get("after") == "set_hvac_mode"
        ):
            self.last_after = now


@register("state_lag")
class StateLag(Quirk):
    """Reported state trails commands by ``seconds`` (cloud polling, slow radios; #436)."""

    def __init__(self, params: dict[str, Any]) -> None:
        super().__init__(params)
        self.frozen: dict[str, Any] | None = None
        self.frozen_state: str | None = None
        self.until = 0.0
        self.pending = False

    def before_command(self, dev, service, data, now):  # noqa: ANN001, ANN201
        if self.frozen is None or now >= self.until:
            self.pending = True
            self._capture_next = (dev.state(now), dev.attributes(now))
        return None

    def after_command(self, dev, service, data, now, result):  # noqa: ANN001, ANN201
        if self.pending and result.ok and result.changed:
            self.frozen_state, self.frozen = self._capture_next
            self.until = now + float(self.p.get("seconds", 30))
        self.pending = False

    def transform_attributes(self, dev, attrs, now):  # noqa: ANN001, ANN201
        if self.frozen is not None and now < self.until:
            return {**self.frozen, "current_temperature": attrs.get("current_temperature")}
        self.frozen = None
        return attrs

    def state_override(self, dev, now):  # noqa: ANN001, ANN201
        if self.frozen is not None and now < self.until:
            return self.frozen_state
        return None


@register("no_state_feedback")
class NoStateFeedback(Quirk):
    """IR device (#416, #298): every frame beeps; optionally the state is unknown."""

    def after_command(self, dev, service, data, now, result):  # noqa: ANN001, ANN201
        if result.ok and self.p.get("beep_per_command", True):
            dev.counters.beeps += 1

    def transform_attributes(self, dev, attrs, now):  # noqa: ANN001, ANN201
        if not self.p.get("current_temperature", False):
            attrs = {**attrs, "current_temperature": None}
        if self.p.get("hvac_action", False) is False:
            attrs.pop("hvac_action", None)
        return attrs

    def state_override(self, dev, now):  # noqa: ANN001, ANN201
        return "unknown" if self.p.get("state") == "unknown" else None


@register("availability")
class Availability(Quirk):
    """Unavailable after HA start (#437, #181), offline when held off (#183), flapping."""

    def __init__(self, params: dict[str, Any]) -> None:
        super().__init__(params)
        self.off_since: float | None = None
        self.asleep = False

    def _down(self, dev: SimDevice, now: float) -> bool:
        after_start = float(self.p.get("unavailable_after_start_s", 0))
        if after_start and now - dev.boot_time < after_start:
            return True
        if self.asleep:
            return True
        flap = self.p.get("flap")
        if flap:
            every, dur = float(flap["every_s"]), float(flap["for_s"])
            return (now - dev.boot_time) % every > every - dur
        return False

    def on_step(self, dev, dt, now):  # noqa: ANN001, ANN201
        limit = self.p.get("offline_when_off_after_s")
        if limit:
            if dev.hvac_mode == "off":
                self.off_since = self.off_since if self.off_since is not None else now
                if now - self.off_since >= float(limit):
                    self.asleep = True
            else:
                self.off_since = None
        if self.asleep:
            checkin = float(self.p.get("checkin_s", 0) or 0)
            if checkin and self.off_since is not None and (now - self.off_since) % checkin < dt:
                self.asleep = False
                self.off_since = now
        dev.available = not self._down(dev, now)

    def snapshot(self):  # noqa: ANN201
        return {"off_since": self.off_since, "asleep": self.asleep}

    def restore(self, data):  # noqa: ANN001, ANN201
        self.off_since = data.get("off_since")
        self.asleep = data.get("asleep", False)


@register("rounding")
class Rounding(Quirk):
    """Device shows whole degrees (Ecobee, many ACs; #416 dedup, #396 cap)."""

    def transform_attributes(self, dev, attrs, now):  # noqa: ANN001, ANN201
        if not self.p.get("whole_degrees", True):
            return attrs
        out = dict(attrs)
        for key in ("temperature", "target_temp_low", "target_temp_high", "current_temperature"):
            if out.get(key) is not None:
                out[key] = float(round(out[key]))
        return out


@register("off_unsupported")
class OffUnsupported(Quirk):
    """Marker: the profile omits "off" from hvac_modes (#199); HA rejects the service."""
