"""Shared base of the appliance entities (fan, switch, humidifier)."""

from __future__ import annotations

from typing import Any

from homeassistant.exceptions import HomeAssistantError

from roommind_sim.appliances import SimAppliance

from .entity import SimEntity


class SimApplianceEntity(SimEntity):
    def __init__(self, rt: Any, app: SimAppliance) -> None:
        super().__init__(rt, app.entity_id, app.spec.name)
        self.app = app

    @property
    def available(self) -> bool:
        return self.app.available

    @property
    def is_on(self) -> bool:
        return self.app.on

    def _command(self, service: str, data: dict[str, Any]) -> None:
        result = self.rt.world.appliance_call(self.entity_id, service, data, self.now)
        self.rt.log_command(self.entity_id, service, data, result.status)
        self.async_write_ha_state()
        if not result.ok:
            raise HomeAssistantError(f"{self.entity_id}: {result.reason}")

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._command("turn_off", {})
