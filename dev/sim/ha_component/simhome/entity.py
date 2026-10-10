"""Common entity base for simhome."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from homeassistant.helpers.entity import Entity

if TYPE_CHECKING:
    from .runtime import SimRuntime


class SimEntity(Entity):
    _attr_should_poll = False
    _attr_has_entity_name = False

    def __init__(self, runtime: SimRuntime, entity_id: str, name: str) -> None:
        self.rt = runtime
        self.entity_id = entity_id
        self._attr_unique_id = f"simhome_{entity_id}"
        self._attr_name = name
        runtime.entities[entity_id] = self

    @property
    def now(self) -> float:
        return time.time()
