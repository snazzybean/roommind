"""Covers with travel time and tilt."""

from __future__ import annotations

from typing import Any

from homeassistant.components.cover import CoverDeviceClass, CoverEntity, CoverEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from roommind_sim.covers import SimCover

from .const import DOMAIN
from .entity import SimEntity


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback) -> None:
    rt = hass.data[DOMAIN]
    add([SimCoverEntity(rt, c) for c in rt.world.covers.values()])


class SimCoverEntity(SimEntity, CoverEntity):
    def __init__(self, rt: Any, cover: SimCover) -> None:
        super().__init__(rt, cover.entity_id, cover.spec.name)
        self.cover = cover
        self._attr_device_class = CoverDeviceClass.BLIND if cover.has_tilt else CoverDeviceClass.SHUTTER
        features = CoverEntityFeature(0)
        if not cover.tilt_only:
            features |= (
                CoverEntityFeature.OPEN
                | CoverEntityFeature.CLOSE
                | CoverEntityFeature.SET_POSITION
                | CoverEntityFeature.STOP
            )
        if cover.has_tilt:
            features |= (
                CoverEntityFeature.OPEN_TILT | CoverEntityFeature.CLOSE_TILT | CoverEntityFeature.SET_TILT_POSITION
            )
        self._attr_supported_features = features

    @property
    def available(self) -> bool:
        return self.cover.available

    @property
    def current_cover_position(self) -> int | None:
        return None if self.cover.tilt_only else round(self.cover.position)

    @property
    def current_cover_tilt_position(self) -> int | None:
        return round(self.cover.tilt) if self.cover.has_tilt else None

    @property
    def is_closed(self) -> bool:
        if self.cover.tilt_only:
            return self.cover.tilt < 1
        return self.cover.position < 1

    @property
    def is_opening(self) -> bool:
        return self.cover.moving == "opening"

    @property
    def is_closing(self) -> bool:
        return self.cover.moving == "closing"

    def _cmd(self, service: str, data: dict[str, Any]) -> None:
        ok = self.rt.world.cover_call(self.entity_id, service, data)
        self.rt.log_command(self.entity_id, service, data, "accepted" if ok else "rejected")
        self.async_write_ha_state()

    async def async_open_cover(self, **kwargs: Any) -> None:
        self._cmd("open_cover", {})

    async def async_close_cover(self, **kwargs: Any) -> None:
        self._cmd("close_cover", {})

    async def async_stop_cover(self, **kwargs: Any) -> None:
        self._cmd("stop_cover", {})

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        self._cmd("set_cover_position", {"position": kwargs["position"]})

    async def async_open_cover_tilt(self, **kwargs: Any) -> None:
        self._cmd("open_cover_tilt", {})

    async def async_close_cover_tilt(self, **kwargs: Any) -> None:
        self._cmd("close_cover_tilt", {})

    async def async_set_cover_tilt_position(self, **kwargs: Any) -> None:
        self._cmd("set_cover_tilt_position", {"tilt_position": kwargs["tilt_position"]})
