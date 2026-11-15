"""Sensor platform for RoomMind."""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .coordinator import RoomMindCoordinator
from .utils.area_utils import rooms_with_area


def _create_room_entities(coordinator: RoomMindCoordinator, area_id: str) -> list[SensorEntity]:
    """Create the standard set of sensor entities for a room."""
    return [
        RoomMindTargetTemperatureSensor(coordinator, area_id),
        RoomMindModeSensor(coordinator, area_id),
    ]


def _create_global_entities(coordinator: RoomMindCoordinator) -> list[SensorEntity]:
    """Create the integration-wide sensors (tariff state)."""
    return [
        RoomMindEnergyRateSensor(coordinator),
        RoomMindEnergyPeriodSensor(coordinator),
        RoomMindEnergyNextChangeSensor(coordinator),
    ]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up RoomMind sensor entities from a config entry."""
    coordinator: RoomMindCoordinator = hass.data[DOMAIN][entry.entry_id]
    store = hass.data[DOMAIN]["store"]

    # Store the callback on the coordinator so dynamic entity creation works
    coordinator.async_add_entities = async_add_entities

    # Create entities for rooms that already exist in the store
    rooms = rooms_with_area(hass, store.get_rooms())
    entities: list[SensorEntity] = []
    if store.get_settings().get("tou_enabled", False):
        # Tariff sensors appear with the feature and stay (unknown) when it is off.
        entities.extend(_create_global_entities(coordinator))
        coordinator._tou_entities_added = True
    for area_id in rooms:
        entities.extend(_create_room_entities(coordinator, area_id))
        coordinator._entity_areas.add(area_id)
    if entities:
        async_add_entities(entities)


class _RoomMindBaseSensor(CoordinatorEntity, SensorEntity):
    """Base class for all RoomMind room sensors."""

    _attr_has_entity_name = True
    _data_key: str  # Key in the room state dict (e.g. "current_temp")

    def __init__(
        self,
        coordinator: RoomMindCoordinator,
        area_id: str,
        suffix: str,
        name_label: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._area_id = area_id
        self._attr_unique_id = f"{DOMAIN}_{area_id}_{suffix}"
        self._attr_name = f"{area_id} {name_label}"
        self.entity_id = f"sensor.{DOMAIN}_{area_id}_{suffix}"

    @property
    def native_value(self) -> float | str | None:
        """Return the sensor value from the coordinator data."""
        room = self.coordinator.data.get("rooms", {}).get(self._area_id)
        if room:
            val = room.get(self._data_key)
            return val if isinstance(val, (float, int, str)) else None
        return None


class RoomMindTargetTemperatureSensor(_RoomMindBaseSensor):
    """Sensor showing the target temperature for a RoomMind room."""

    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _data_key = "target_temp"

    def __init__(self, coordinator: RoomMindCoordinator, area_id: str) -> None:
        super().__init__(coordinator, area_id, "target_temp", "Target Temperature")


class RoomMindModeSensor(_RoomMindBaseSensor):
    """Sensor showing the current mode for a RoomMind room."""

    _data_key = "mode"

    def __init__(self, coordinator: RoomMindCoordinator, area_id: str) -> None:
        super().__init__(coordinator, area_id, "mode", "Mode")

    @property
    def native_value(self) -> str | None:
        """Return the current mode, defaulting to 'idle'."""
        room = self.coordinator.data.get("rooms", {}).get(self._area_id)
        if room:
            val = room.get("mode", "idle")
            return str(val) if val is not None else "idle"
        return "idle"


def _tou_snapshot(coordinator: RoomMindCoordinator) -> dict | None:
    """Return the latest Time-of-Use snapshot from coordinator data."""
    data = coordinator.data or {}
    snap = data.get("tou")
    return snap if isinstance(snap, dict) and snap.get("enabled") else None


class _RoomMindGlobalSensor(CoordinatorEntity, SensorEntity):
    """Base class for integration-wide (non-room) sensors."""

    def __init__(self, coordinator: RoomMindCoordinator, suffix: str, name: str) -> None:
        """Initialize the global sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}_{suffix}"
        self._attr_name = name
        self.entity_id = f"sensor.{DOMAIN}_{suffix}"


class RoomMindEnergyRateSensor(_RoomMindGlobalSensor):
    """Current electricity rate of the configured Time-of-Use source."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:currency-usd"

    def __init__(self, coordinator: RoomMindCoordinator) -> None:
        super().__init__(coordinator, "energy_rate", "RoomMind Energy Rate")

    @property
    def native_value(self) -> float | None:
        """Return the current rate, or None when no tariff source reports one."""
        snap = _tou_snapshot(self.coordinator)
        rate = snap.get("rate") if snap else None
        return float(rate) if isinstance(rate, (int, float)) else None

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return the source's rate unit (e.g. CAD/kWh)."""
        snap = _tou_snapshot(self.coordinator)
        unit = snap.get("rate_unit") if snap else None
        return str(unit) if unit else None


class RoomMindEnergyPeriodSensor(_RoomMindGlobalSensor):
    """Active tariff tier: peak, mid, off or ultra_low."""

    _attr_icon = "mdi:clock-fast"

    def __init__(self, coordinator: RoomMindCoordinator) -> None:
        super().__init__(coordinator, "energy_period", "RoomMind Energy Period")

    @property
    def native_value(self) -> str | None:
        """Return the current tier, or None while TOU is off or unresolved."""
        snap = _tou_snapshot(self.coordinator)
        tier = snap.get("tier") if snap else None
        if not isinstance(tier, str) or tier == "unknown":
            return None
        return tier


class RoomMindEnergyNextChangeSensor(_RoomMindGlobalSensor):
    """When the tariff tier changes next (pre-conditioning deadline)."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:clock-arrow-down"

    def __init__(self, coordinator: RoomMindCoordinator) -> None:
        super().__init__(coordinator, "energy_next_change", "RoomMind Energy Next Change")

    @property
    def native_value(self) -> datetime | None:
        """Return the next tier-change timestamp, or None."""
        snap = _tou_snapshot(self.coordinator)
        ts = snap.get("next_change") if snap else None
        if isinstance(ts, (int, float)) and ts > 0:
            value: datetime = dt_util.utc_from_timestamp(float(ts))
            return value
        return None

    @property
    def extra_state_attributes(self) -> dict:
        """Expose the tier assumed after the change."""
        snap = _tou_snapshot(self.coordinator)
        next_tier = snap.get("next_tier") if snap else None
        return {"next_tier": next_tier} if isinstance(next_tier, str) else {}
