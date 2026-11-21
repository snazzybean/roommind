"""Tests for ExternalHeatManager (unmanaged heat sources: stoves, fireplaces)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from homeassistant.core import State

from custom_components.roommind.const import MAX_SENSOR_STALENESS
from custom_components.roommind.managers.external_heat_manager import (
    ExternalHeatManager,
    ExternalHeatThresholds,
)

ROOM = "living_room"
STOVE_TEMP = "sensor.stove_temp"
TIME_PATH = "custom_components.roommind.managers.external_heat_manager.time"

THRESHOLDS = ExternalHeatThresholds(delta_on=3.0, delta_off=1.5, power_threshold=50.0, cooldown_minutes=120)


def temp_state(entity_id: str, value: str, unit: str = "°C") -> State:
    """Build a temperature sensor state as Home Assistant would expose it.

    Args:
        entity_id: entity id of the sensor.
        value: state string, a number or "unavailable"/"unknown".
        unit: unit_of_measurement attribute, "°C" or "°F".
    """
    return State(entity_id, value, {"unit_of_measurement": unit, "device_class": "temperature"})


def power_state(entity_id: str, value: str, unit: str = "W") -> State:
    """Build a power sensor state.

    Args:
        entity_id: entity id of the sensor.
        value: state string, a number or "unavailable".
        unit: unit_of_measurement attribute, "W" or "kW".
    """
    return State(entity_id, value, {"unit_of_measurement": unit, "device_class": "power"})


def stove_at(value: str) -> dict[str, State | None]:
    """Return the source states for the single stove temperature sensor at ``value`` degrees C.

    Args:
        value: the sensor state string.
    """
    return {STOVE_TEMP: temp_state(STOVE_TEMP, value)}


class TestThresholds:
    def test_defaults_from_room_without_fields(self):
        """A room without the external heat fields gets the documented defaults."""
        thresholds = ExternalHeatThresholds.from_room({})
        assert thresholds == ExternalHeatThresholds(
            delta_on=3.0, delta_off=1.5, power_threshold=50.0, cooldown_minutes=120
        )

    def test_values_from_room(self):
        """Configured room values override the defaults."""
        thresholds = ExternalHeatThresholds.from_room(
            {
                "external_heat_delta_on": 4.0,
                "external_heat_delta_off": 2.0,
                "external_heat_power_threshold": 100.0,
                "external_heat_cooldown": 30,
            }
        )
        assert thresholds == ExternalHeatThresholds(
            delta_on=4.0, delta_off=2.0, power_threshold=100.0, cooldown_minutes=30
        )


class TestTemperatureDetection:
    def test_inactive_by_default(self):
        """An unknown room is not active and has no end time."""
        mgr = ExternalHeatManager()
        assert mgr.is_active(ROOM) is False
        assert mgr.active_until(ROOM) is None

    def test_below_delta_on_stays_off(self):
        """A stove sensor less than delta_on above the room does not activate."""
        mgr = ExternalHeatManager()
        assert mgr.update(ROOM, stove_at("22.9"), 20.0, THRESHOLDS) is False

    def test_at_delta_on_activates(self):
        """Reaching delta_on above the room activates the source."""
        mgr = ExternalHeatManager()
        assert mgr.update(ROOM, stove_at("23.0"), 20.0, THRESHOLDS) is True
        assert mgr.is_active(ROOM) is True
        assert mgr.active_until(ROOM) is None  # burning, no cooldown end yet

    def test_hysteresis_keeps_active_between_thresholds(self):
        """Once active, a delta between delta_off and delta_on keeps it active."""
        mgr = ExternalHeatManager()
        mgr.update(ROOM, stove_at("24.0"), 20.0, THRESHOLDS)
        assert mgr.update(ROOM, stove_at("22.0"), 20.0, THRESHOLDS) is True

    def test_between_thresholds_does_not_activate_from_off(self):
        """From off, a delta between delta_off and delta_on is not enough."""
        mgr = ExternalHeatManager()
        assert mgr.update(ROOM, stove_at("22.0"), 20.0, THRESHOLDS) is False

    def test_fahrenheit_sensor_is_converted(self):
        """A sensor reporting in F is converted to C before comparing."""
        mgr = ExternalHeatManager()
        # 75.2 F = 24.0 C, 4 C above the room
        states = {STOVE_TEMP: temp_state(STOVE_TEMP, "75.2", unit="°F")}
        assert mgr.update(ROOM, states, 20.0, THRESHOLDS) is True

    def test_room_temp_unknown_keeps_previous_state(self):
        """Without a room temperature the temperature sensors cannot tell: their last vote holds."""
        mgr = ExternalHeatManager()
        mgr.update(ROOM, stove_at("25.0"), 20.0, THRESHOLDS)
        assert mgr.update(ROOM, stove_at("25.0"), None, THRESHOLDS) is True

    @pytest.mark.parametrize("dropout", ["unavailable", "unknown", None])
    def test_dropout_keeps_last_vote(self, dropout):
        """A sensor that drops out briefly keeps its last vote, like a window sensor."""
        mgr = ExternalHeatManager()
        mgr.update(ROOM, stove_at("25.0"), 20.0, THRESHOLDS)
        states = {STOVE_TEMP: None if dropout is None else temp_state(STOVE_TEMP, dropout)}
        assert mgr.update(ROOM, states, 20.0, THRESHOLDS) is True
        assert mgr.active_until(ROOM) is None  # still burning, not cooling down

    def test_long_dropout_counts_as_out_then_cools_down(self, caplog):
        """After MAX_SENSOR_STALENESS a dead sensor counts as out: the cooldown runs, the room is released."""
        mgr = ExternalHeatManager()
        with patch(TIME_PATH) as mock_time:
            mock_time.time.return_value = 1000.0
            mgr.update(ROOM, stove_at("25.0"), 20.0, THRESHOLDS)
            mock_time.time.return_value = 1010.0
            assert mgr.update(ROOM, stove_at("unavailable"), 20.0, THRESHOLDS) is True

            mock_time.time.return_value = 1010.0 + MAX_SENSOR_STALENESS
            assert mgr.update(ROOM, stove_at("unavailable"), 20.0, THRESHOLDS) is True
            assert mgr.active_until(ROOM) == pytest.approx(1010.0 + MAX_SENSOR_STALENESS + 120 * 60)
            assert any("unreadable" in r.getMessage() for r in caplog.records)

            mock_time.time.return_value = 1010.0 + MAX_SENSOR_STALENESS + 120 * 60
            assert mgr.update(ROOM, stove_at("unavailable"), 20.0, THRESHOLDS) is False

    def test_unavailable_on_first_observation_is_off(self):
        """With no reading ever, the source counts as out: the room heats normally."""
        mgr = ExternalHeatManager()
        assert mgr.update(ROOM, stove_at("unknown"), 20.0, THRESHOLDS) is False
        assert mgr.update(ROOM, {STOVE_TEMP: None}, 20.0, THRESHOLDS) is False

    def test_non_numeric_sensor_cannot_tell(self):
        """A sensor whose state is not a number does not vote."""
        mgr = ExternalHeatManager()
        assert mgr.update(ROOM, stove_at("hot"), 20.0, THRESHOLDS) is False

    def test_sensor_without_unit_but_temperature_class(self):
        """A temperature sensor without a unit is read in degrees C."""
        mgr = ExternalHeatManager()
        states = {STOVE_TEMP: State(STOVE_TEMP, "26.0", {"device_class": "temperature"})}
        assert mgr.update(ROOM, states, 20.0, THRESHOLDS) is True

    def test_any_source_on_is_enough(self):
        """With several entities, one reporting on activates the source."""
        mgr = ExternalHeatManager()
        states = {
            STOVE_TEMP: temp_state(STOVE_TEMP, "20.5"),
            "sensor.fireplace_temp": temp_state("sensor.fireplace_temp", "26.0"),
        }
        assert mgr.update(ROOM, states, 20.0, THRESHOLDS) is True

    def test_one_entity_on_wins_over_others_off(self):
        """A switch on wins over a cold temperature sensor."""
        mgr = ExternalHeatManager()
        states = {STOVE_TEMP: temp_state(STOVE_TEMP, "20.0"), "switch.stove_plug": State("switch.stove_plug", "on")}
        assert mgr.update(ROOM, states, 20.0, THRESHOLDS) is True

    def test_dropout_of_one_entity_keeps_its_vote_next_to_others(self):
        """The burning sensor drops out while another reads off: its last vote still holds."""
        mgr = ExternalHeatManager()
        states = {
            STOVE_TEMP: temp_state(STOVE_TEMP, "26.0"),
            "binary_sensor.stove": State("binary_sensor.stove", "off"),
        }
        assert mgr.update(ROOM, states, 20.0, THRESHOLDS) is True
        states[STOVE_TEMP] = temp_state(STOVE_TEMP, "unavailable")
        assert mgr.update(ROOM, states, 20.0, THRESHOLDS) is True

    def test_removed_entity_no_longer_votes(self):
        """An entity taken out of the room config forgets its last vote at once."""
        mgr = ExternalHeatManager()
        no_cooldown = ExternalHeatThresholds(delta_on=3.0, delta_off=1.5, power_threshold=50.0, cooldown_minutes=0)
        mgr.update(ROOM, {"switch.stove_plug": State("switch.stove_plug", "on")}, 20.0, no_cooldown)
        assert mgr.update(ROOM, {STOVE_TEMP: temp_state(STOVE_TEMP, "unavailable")}, 20.0, no_cooldown) is False

    def test_rooms_are_independent(self):
        """A stove in one room does not pause another."""
        mgr = ExternalHeatManager()
        mgr.update(ROOM, stove_at("26.0"), 20.0, THRESHOLDS)
        assert mgr.update("bedroom", stove_at("20.0"), 20.0, THRESHOLDS) is False
        assert mgr.is_active(ROOM) is True


class TestOtherEntityKinds:
    @pytest.mark.parametrize(
        ("entity_id", "value", "expected"),
        [
            ("binary_sensor.stove", "on", True),
            ("binary_sensor.stove", "off", False),
            ("switch.stove_plug", "on", True),
            ("input_boolean.stove_lit", "on", True),
            ("input_boolean.stove_lit", "off", False),
        ],
    )
    def test_on_off_entities(self, entity_id, value, expected):
        """binary_sensor, switch and input_boolean are on when their state is on."""
        mgr = ExternalHeatManager()
        states = {entity_id: State(entity_id, value)}
        assert mgr.update(ROOM, states, 20.0, THRESHOLDS) is expected

    @pytest.mark.parametrize(
        ("value", "unit", "expected"),
        [
            ("40", "W", False),
            ("60", "W", True),
            ("0.04", "kW", False),
            ("1.2", "kW", True),
        ],
    )
    def test_power_sensor(self, value, unit, expected):
        """A power sensor is on above power_threshold watts, kW converted."""
        mgr = ExternalHeatManager()
        states = {"sensor.stove_power": power_state("sensor.stove_power", value, unit)}
        assert mgr.update(ROOM, states, 20.0, THRESHOLDS) is expected

    def test_power_sensor_works_without_room_temp(self):
        """Power and on/off entities do not need the room temperature."""
        mgr = ExternalHeatManager()
        states = {"sensor.stove_power": power_state("sensor.stove_power", "500")}
        assert mgr.update(ROOM, states, None, THRESHOLDS) is True

    def test_unsupported_entity_is_ignored_and_warned_once(self, caplog):
        """A numeric sensor of another kind does not vote and is logged once."""
        mgr = ExternalHeatManager()
        states = {"sensor.stove_humidity": State("sensor.stove_humidity", "40", {"unit_of_measurement": "%"})}
        assert mgr.update(ROOM, states, 20.0, THRESHOLDS) is False
        mgr.update(ROOM, states, 20.0, THRESHOLDS)
        warnings = [r for r in caplog.records if "sensor.stove_humidity" in r.getMessage()]
        assert len(warnings) == 1


class TestCooldown:
    def test_cooldown_after_switch_off(self):
        """After the source goes off the room stays disturbed for cooldown minutes."""
        mgr = ExternalHeatManager()
        with patch(TIME_PATH) as mock_time:
            mock_time.time.return_value = 1000.0
            mgr.update(ROOM, stove_at("25.0"), 20.0, THRESHOLDS)

            mock_time.time.return_value = 2000.0
            assert mgr.update(ROOM, stove_at("20.5"), 20.0, THRESHOLDS) is True
            assert mgr.active_until(ROOM) == pytest.approx(2000.0 + 120 * 60)

            mock_time.time.return_value = 2000.0 + 120 * 60 - 1
            assert mgr.update(ROOM, stove_at("20.5"), 20.0, THRESHOLDS) is True

            mock_time.time.return_value = 2000.0 + 120 * 60
            assert mgr.update(ROOM, stove_at("20.5"), 20.0, THRESHOLDS) is False
            assert mgr.is_active(ROOM) is False
            assert mgr.active_until(ROOM) is None

    def test_relight_during_cooldown_cancels_it(self):
        """Lighting the source again during the cooldown clears the end time."""
        mgr = ExternalHeatManager()
        with patch(TIME_PATH) as mock_time:
            mock_time.time.return_value = 1000.0
            mgr.update(ROOM, stove_at("25.0"), 20.0, THRESHOLDS)
            mock_time.time.return_value = 2000.0
            mgr.update(ROOM, stove_at("20.5"), 20.0, THRESHOLDS)

            mock_time.time.return_value = 3000.0
            assert mgr.update(ROOM, stove_at("25.0"), 20.0, THRESHOLDS) is True
            assert mgr.active_until(ROOM) is None

    def test_zero_cooldown_releases_immediately(self):
        """With cooldown 0 the room is released as soon as the source is off."""
        mgr = ExternalHeatManager()
        no_cooldown = ExternalHeatThresholds(delta_on=3.0, delta_off=1.5, power_threshold=50.0, cooldown_minutes=0)
        mgr.update(ROOM, stove_at("25.0"), 20.0, no_cooldown)
        assert mgr.update(ROOM, stove_at("20.5"), 20.0, no_cooldown) is False

    def test_remove_room_clears_state(self):
        """remove_room forgets the room entirely."""
        mgr = ExternalHeatManager()
        mgr.update(ROOM, stove_at("25.0"), 20.0, THRESHOLDS)
        mgr.remove_room(ROOM)
        assert mgr.is_active(ROOM) is False
        mgr.remove_room("never_seen")  # no error

    def test_remove_room_forgets_last_votes_and_warnings(self, caplog):
        """After remove_room an unreadable sensor no longer holds a vote and warns again."""
        mgr = ExternalHeatManager()
        humidity = {"sensor.stove_humidity": State("sensor.stove_humidity", "40", {"unit_of_measurement": "%"})}
        mgr.update(ROOM, humidity, 20.0, THRESHOLDS)
        mgr.update(ROOM, stove_at("25.0"), 20.0, THRESHOLDS)
        mgr.remove_room(ROOM)
        assert mgr.update(ROOM, stove_at("unavailable"), 20.0, THRESHOLDS) is False
        mgr.update(ROOM, humidity, 20.0, THRESHOLDS)
        assert len([r for r in caplog.records if "sensor.stove_humidity" in r.getMessage()]) == 2

    def test_cooldown_change_applies_to_a_running_cooldown(self):
        """Shortening the cooldown in the panel releases the room on the next cycle."""
        mgr = ExternalHeatManager()
        short = ExternalHeatThresholds(delta_on=3.0, delta_off=1.5, power_threshold=50.0, cooldown_minutes=10)
        with patch(TIME_PATH) as mock_time:
            mock_time.time.return_value = 1000.0
            mgr.update(ROOM, stove_at("25.0"), 20.0, THRESHOLDS)
            mock_time.time.return_value = 2000.0
            assert mgr.update(ROOM, stove_at("20.0"), 20.0, THRESHOLDS) is True
            mock_time.time.return_value = 2000.0 + 11 * 60
            assert mgr.update(ROOM, stove_at("20.0"), 20.0, short) is False
