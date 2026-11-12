"""Tests for the heat source orchestrator."""

from __future__ import annotations

from unittest.mock import MagicMock

from custom_components.roommind.const import (
    DEFAULT_HEAT_SOURCE_AC_MIN_OUTDOOR,
    DEFAULT_HEAT_SOURCE_OUTDOOR_THRESHOLD,
    DEFAULT_HEAT_SOURCE_PRIMARY_DELTA,
    HEAT_SOURCE_SECONDARY_POWER_SCALE,
    MODE_COOLING,
    MODE_HEATING,
    MODE_IDLE,
)
from custom_components.roommind.managers.heat_source_orchestrator import (
    HeatSourcePlan,
    evaluate_heat_sources,
)


def _make_hass(ac_modes: list[str] | None = None) -> MagicMock:
    """Create a mock hass with AC entity that supports given modes."""
    hass = MagicMock()
    if ac_modes is not None:
        ac_state = MagicMock()
        ac_state.attributes = {"hvac_modes": ac_modes}
        hass.states.get = MagicMock(return_value=ac_state)
    else:
        hass.states.get = MagicMock(return_value=None)
    return hass


def _make_room(
    thermostats: list[str] | None = None,
    acs: list[str] | None = None,
    orchestration: bool = True,
    primary_delta: float = DEFAULT_HEAT_SOURCE_PRIMARY_DELTA,
    outdoor_threshold: float = DEFAULT_HEAT_SOURCE_OUTDOOR_THRESHOLD,
    ac_min_outdoor: float = DEFAULT_HEAT_SOURCE_AC_MIN_OUTDOOR,
) -> dict:
    trv_list = thermostats if thermostats is not None else ["climate.trv_1"]
    ac_list = acs if acs is not None else ["climate.ac_1"]
    devices = [{"entity_id": eid, "type": "trv", "role": "auto", "heating_system_type": ""} for eid in trv_list] + [
        {"entity_id": eid, "type": "ac", "role": "auto", "heating_system_type": ""} for eid in ac_list
    ]
    return {
        "area_id": "test_room",
        "thermostats": trv_list,
        "acs": ac_list,
        "devices": devices,
        "heat_source_orchestration": orchestration,
        "heat_source_primary_delta": primary_delta,
        "heat_source_outdoor_threshold": outdoor_threshold,
        "heat_source_ac_min_outdoor": ac_min_outdoor,
    }


class TestEvaluateHeatSources:
    """Tests for evaluate_heat_sources()."""

    def test_returns_none_for_non_heating_mode(self):
        """Non-heating modes should not produce a plan."""
        hass = _make_hass(["heat", "cool"])
        room = _make_room()
        result = evaluate_heat_sources(room, MODE_COOLING, 0.6, 20.0, 22.0, 10.0, "none", hass)
        assert result is None

        result = evaluate_heat_sources(room, MODE_IDLE, 0.0, 20.0, 22.0, 10.0, "none", hass)
        assert result is None

    def test_returns_none_when_disabled(self):
        """Orchestration disabled should return None."""
        hass = _make_hass(["heat", "cool"])
        room = _make_room(orchestration=False)
        result = evaluate_heat_sources(room, MODE_HEATING, 0.6, 20.0, 22.0, 10.0, "none", hass)
        assert result is None

    def test_returns_none_without_both_device_types(self):
        """Without both thermostats and ACs, no orchestration."""
        hass = _make_hass(["heat", "cool"])
        room_no_ac = _make_room(acs=[])
        result = evaluate_heat_sources(room_no_ac, MODE_HEATING, 0.6, 20.0, 22.0, 10.0, "none", hass)
        assert result is None

        room_no_trv = _make_room(thermostats=[])
        result = evaluate_heat_sources(room_no_trv, MODE_HEATING, 0.6, 20.0, 22.0, 10.0, "none", hass)
        assert result is None

    def test_returns_none_when_temps_missing(self):
        """Missing current_temp or target_temp should return None."""
        hass = _make_hass(["heat", "cool"])
        room = _make_room()
        assert evaluate_heat_sources(room, MODE_HEATING, 0.6, None, 22.0, 10.0, "none", hass) is None
        assert evaluate_heat_sources(room, MODE_HEATING, 0.6, 20.0, None, 10.0, "none", hass) is None

    def test_small_gap_secondary_only(self):
        """Small temperature gap should only use secondary (AC)."""
        hass = _make_hass(["heat", "cool"])
        room = _make_room(primary_delta=1.5)
        # delta_t = 0.5°C, well below threshold
        result = evaluate_heat_sources(room, MODE_HEATING, 0.6, 20.5, 21.0, 10.0, "none", hass)

        assert isinstance(result, HeatSourcePlan)
        assert result.active_sources == "secondary"

        # TRV should be inactive
        trv_cmds = [c for c in result.commands if c.device_type == "thermostat"]
        assert len(trv_cmds) == 1
        assert not trv_cmds[0].active
        assert trv_cmds[0].power_fraction == 0.0

        # AC should be active
        ac_cmds = [c for c in result.commands if c.device_type == "ac"]
        assert len(ac_cmds) == 1
        assert ac_cmds[0].active
        assert ac_cmds[0].power_fraction == 0.6

    def test_large_gap_both_sources(self):
        """Large temperature gap should activate both sources."""
        hass = _make_hass(["heat", "cool"])
        room = _make_room(primary_delta=1.5)
        # delta_t = 4.0°C > 1.5 * 2.0 = 3.0 + hysteresis
        result = evaluate_heat_sources(room, MODE_HEATING, 0.8, 17.0, 21.0, 10.0, "none", hass)

        assert isinstance(result, HeatSourcePlan)
        assert result.active_sources == "both"

        trv_cmds = [c for c in result.commands if c.device_type == "thermostat"]
        ac_cmds = [c for c in result.commands if c.device_type == "ac"]
        assert trv_cmds[0].active
        assert trv_cmds[0].power_fraction == 0.8
        assert ac_cmds[0].active
        assert ac_cmds[0].power_fraction == round(0.8 * HEAT_SOURCE_SECONDARY_POWER_SCALE, 2)

    def test_medium_gap_cold_weather_prefers_primary(self):
        """Medium gap + cold weather should prefer primary (boiler)."""
        hass = _make_hass(["heat", "cool"])
        room = _make_room(primary_delta=1.5, outdoor_threshold=5.0)
        # delta_t = 2.0°C, outdoor = -5°C (cold)
        result = evaluate_heat_sources(room, MODE_HEATING, 0.7, 19.0, 21.0, -5.0, "none", hass)

        assert isinstance(result, HeatSourcePlan)
        assert result.active_sources == "primary"

        trv_cmds = [c for c in result.commands if c.device_type == "thermostat"]
        ac_cmds = [c for c in result.commands if c.device_type == "ac"]
        assert trv_cmds[0].active
        assert not ac_cmds[0].active

    def test_medium_gap_mild_weather_prefers_secondary(self):
        """Medium gap + mild weather should prefer secondary (AC/heat pump)."""
        hass = _make_hass(["heat", "cool"])
        room = _make_room(primary_delta=1.5, outdoor_threshold=5.0)
        # delta_t = 2.0°C, outdoor = 12°C (mild)
        result = evaluate_heat_sources(room, MODE_HEATING, 0.7, 19.0, 21.0, 12.0, "none", hass)

        assert isinstance(result, HeatSourcePlan)
        assert result.active_sources == "secondary"

        ac_cmds = [c for c in result.commands if c.device_type == "ac"]
        trv_cmds = [c for c in result.commands if c.device_type == "thermostat"]
        assert ac_cmds[0].active
        assert not trv_cmds[0].active

    def test_extreme_cold_disables_ac(self):
        """Extreme cold outdoor temp should disable AC heating entirely."""
        hass = _make_hass(["heat", "cool"])
        room = _make_room(ac_min_outdoor=-15.0)
        # outdoor = -20°C, below AC min
        result = evaluate_heat_sources(room, MODE_HEATING, 0.8, 17.0, 21.0, -20.0, "none", hass)

        assert isinstance(result, HeatSourcePlan)
        # AC disabled, only primary available
        assert result.active_sources == "primary"
        ac_cmds = [c for c in result.commands if c.device_type == "ac"]
        assert len(ac_cmds) == 0  # ACs removed from plan entirely

    def test_hysteresis_stays_on_both(self):
        """When previously on 'both', should stay on 'both' until delta drops below threshold - hysteresis."""
        hass = _make_hass(["heat", "cool"])
        room = _make_room(primary_delta=1.5)
        # delta_t = 1.6°C, above primary_delta - hysteresis (1.5 - 0.3 = 1.2)
        result = evaluate_heat_sources(room, MODE_HEATING, 0.6, 19.4, 21.0, 0.0, "both", hass)

        assert isinstance(result, HeatSourcePlan)
        assert result.active_sources == "both"

    def test_hysteresis_switches_from_both_to_secondary(self):
        """When previously on 'both' and delta drops well below threshold, switch to secondary."""
        hass = _make_hass(["heat", "cool"])
        room = _make_room(primary_delta=1.5)
        # delta_t = 1.0°C, below primary_delta - hysteresis (1.5 - 0.3 = 1.2)
        result = evaluate_heat_sources(room, MODE_HEATING, 0.6, 20.0, 21.0, 10.0, "both", hass)

        assert isinstance(result, HeatSourcePlan)
        assert result.active_sources == "secondary"

    def test_ac_without_heat_mode_excluded(self):
        """ACs that don't support heating should be excluded from heat orchestration."""
        hass = MagicMock()
        # AC only supports cool mode
        ac_state = MagicMock()
        ac_state.attributes = {"hvac_modes": ["cool"]}
        hass.states.get = MagicMock(return_value=ac_state)

        room = _make_room()
        result = evaluate_heat_sources(room, MODE_HEATING, 0.6, 20.0, 22.0, 10.0, "none", hass)

        assert isinstance(result, HeatSourcePlan)
        # AC can't heat, falls back to primary only
        assert result.active_sources == "primary"

    def test_a_run_starting_at_the_target_goes_to_the_preferred_source(self):
        """The controller heats from idle at or above the target only by the room's own run
        rules (UFH drift bypass on a predicted dip): parking every device showed heating
        while nothing ran. The outdoor rule picks the source (as the controller's run rules
        do), and the run keeps it at the target."""
        hass = _make_hass(["heat", "cool"])
        room = _make_room()
        for outdoor, expected in ((0.0, "primary"), (10.0, "secondary"), (None, "primary")):
            previous = "none"
            for temp in (21.0, 21.2, 21.1, 21.0):
                result = evaluate_heat_sources(room, MODE_HEATING, 0.6, temp, 21.0, outdoor, previous, hass)
                assert isinstance(result, HeatSourcePlan)
                assert result.active_sources == expected, (outdoor, temp)
                previous = result.active_sources
        cold = evaluate_heat_sources(room, MODE_HEATING, 0.6, 20.9, 21.0, 0.0, "primary", hass)
        assert [c.entity_id for c in cold.commands if c.active] == ["climate.trv_1"]

    def test_a_run_starting_at_the_target_takes_the_ac_when_the_primary_is_unavailable(self):
        hass = MagicMock()
        ac_state = MagicMock()
        ac_state.state = "heat"
        ac_state.attributes = {"hvac_modes": ["heat", "cool"]}
        trv_state = MagicMock()
        trv_state.state = "unavailable"
        hass.states.get = MagicMock(side_effect=lambda eid: trv_state if eid == "climate.trv_1" else ac_state)
        result = evaluate_heat_sources(_make_room(), MODE_HEATING, 0.6, 21.0, 21.0, 0.0, "none", hass)
        assert result.active_sources == "secondary"

    def test_running_sources_stay_on_at_the_target(self):
        """The controller keeps a run going at the target (min run, holding power); the
        orchestrator must not park the devices then, or the AC switches every cycle."""
        hass = _make_hass(["heat", "cool"])
        room = _make_room()
        previous = "secondary"
        for temp in (20.7, 21.0, 20.9, 21.1):
            result = evaluate_heat_sources(room, MODE_HEATING, 0.3, temp, 21.0, 10.0, previous, hass)
            assert result.active_sources == "secondary", temp
            previous = result.active_sources
        for outdoor in (0.0, 10.0):
            primary = evaluate_heat_sources(room, MODE_HEATING, 0.3, 21.1, 21.0, outdoor, "primary", hass)
            assert primary.active_sources == "primary", outdoor
        cold = evaluate_heat_sources(room, MODE_HEATING, 0.3, 21.1, 21.0, 0.0, "secondary", hass)
        assert cold.active_sources == "secondary"

    def test_both_falls_back_to_the_preferred_source_at_the_target(self):
        hass = _make_hass(["heat", "cool"])
        room = _make_room()
        mild = evaluate_heat_sources(room, MODE_HEATING, 0.3, 21.0, 21.0, 10.0, "both", hass)
        cold = evaluate_heat_sources(room, MODE_HEATING, 0.3, 21.0, 21.0, 0.0, "both", hass)
        assert (mild.active_sources, cold.active_sources) == ("secondary", "primary")

    def test_multiple_devices_per_type(self):
        """Multiple thermostats and ACs should all get commands."""
        hass = _make_hass(["heat", "cool"])
        room = _make_room(
            thermostats=["climate.trv_1", "climate.trv_2"],
            acs=["climate.ac_1", "climate.ac_2"],
        )
        result = evaluate_heat_sources(room, MODE_HEATING, 0.6, 20.0, 21.0, 10.0, "none", hass)

        assert isinstance(result, HeatSourcePlan)
        assert len(result.commands) == 4

    def test_outdoor_temp_none_handled_gracefully(self):
        """When outdoor_temp is None, AC min check and weather routing should be skipped."""
        hass = _make_hass(["heat", "cool"])
        room = _make_room()
        # Small gap, outdoor None
        result = evaluate_heat_sources(room, MODE_HEATING, 0.6, 20.5, 21.0, None, "none", hass)

        assert isinstance(result, HeatSourcePlan)
        assert result.active_sources == "secondary"  # small gap, no weather override

    def test_hysteresis_from_primary_stays(self):
        """When previously on 'primary', should stay if delta still above threshold - hysteresis."""
        hass = _make_hass(["heat", "cool"])
        room = _make_room(primary_delta=1.5)
        # delta_t = 1.4°C, above 1.5 - 0.3 = 1.2 (stays primary)
        result = evaluate_heat_sources(room, MODE_HEATING, 0.7, 19.6, 21.0, -5.0, "primary", hass)

        assert isinstance(result, HeatSourcePlan)
        assert result.active_sources == "primary"

    def test_unavailable_ac_excluded_from_plan(self):
        """An unavailable AC (unplugged/offline) should not be selected for heating."""
        hass = MagicMock()

        def mock_states_get(eid):
            if "ac" in eid:
                state = MagicMock()
                state.state = "unavailable"
                state.attributes = {"hvac_modes": ["heat", "cool"]}
                return state
            # TRV is available
            state = MagicMock()
            state.state = "heat"
            state.attributes = {}
            return state

        hass.states.get = mock_states_get

        room = _make_room()
        # Small gap would normally select secondary (AC), but AC is unavailable
        result = evaluate_heat_sources(room, MODE_HEATING, 0.6, 20.5, 21.0, 10.0, "none", hass)

        assert isinstance(result, HeatSourcePlan)
        # AC unavailable → fallback to primary (TRV)
        assert result.active_sources == "primary"
        ac_cmds = [c for c in result.commands if c.device_type == "ac"]
        assert len(ac_cmds) == 0

    def test_unavailable_trv_excluded_from_plan(self):
        """An unavailable TRV should not be selected for heating."""
        hass = MagicMock()

        def mock_states_get(eid):
            if "ac" in eid:
                state = MagicMock()
                state.state = "cool"
                state.attributes = {"hvac_modes": ["heat", "cool"]}
                return state
            # TRV is unavailable
            state = MagicMock()
            state.state = "unavailable"
            state.attributes = {}
            return state

        hass.states.get = mock_states_get

        room = _make_room()
        # Large gap would normally select "both", but TRV unavailable
        result = evaluate_heat_sources(room, MODE_HEATING, 0.8, 17.0, 21.0, -5.0, "none", hass)

        assert isinstance(result, HeatSourcePlan)
        # TRV unavailable → only secondary available
        assert result.active_sources == "secondary"
        trv_cmds = [c for c in result.commands if c.device_type == "thermostat"]
        assert len(trv_cmds) == 0

    def test_small_gap_cold_weather_prefers_primary(self):
        """Small gap + cold outdoor should prefer primary (boiler), not AC."""
        hass = _make_hass(["heat", "cool"])
        room = _make_room(primary_delta=1.5, outdoor_threshold=5.0)
        # delta_t = 0.5°C (small), outdoor = 0°C (cold, below 5°C threshold)
        result = evaluate_heat_sources(room, MODE_HEATING, 0.6, 20.5, 21.0, 0.0, "none", hass)

        assert isinstance(result, HeatSourcePlan)
        assert result.active_sources == "primary"

        trv_cmds = [c for c in result.commands if c.device_type == "thermostat"]
        ac_cmds = [c for c in result.commands if c.device_type == "ac"]
        assert trv_cmds[0].active
        assert trv_cmds[0].power_fraction == 0.6
        assert not ac_cmds[0].active
        assert ac_cmds[0].power_fraction == 0.0

    def test_escalation_from_primary_to_both(self):
        """From 'primary' state, growing gap should escalate to 'both'."""
        hass = _make_hass(["heat", "cool"])
        room = _make_room(primary_delta=1.5)
        # large_gap_threshold = 1.5 * 2.0 = 3.0, + hysteresis 0.3 = 3.3
        # delta_t = 4.0 > 3.3, previous = "primary"
        result = evaluate_heat_sources(room, MODE_HEATING, 0.8, 17.0, 21.0, -5.0, "primary", hass)

        assert isinstance(result, HeatSourcePlan)
        assert result.active_sources == "both"

    def test_both_drops_to_primary_in_cold_weather(self):
        """When on 'both' and gap drops below threshold in cold weather, prefer boiler."""
        hass = _make_hass(["heat", "cool"])
        room = _make_room(primary_delta=1.5, outdoor_threshold=5.0)
        # delta_t = 1.0 < primary_delta - hysteresis (1.2), outdoor = 0°C (cold)
        result = evaluate_heat_sources(room, MODE_HEATING, 0.6, 20.0, 21.0, 0.0, "both", hass)

        assert isinstance(result, HeatSourcePlan)
        assert result.active_sources == "primary"


class TestPriceAwareSourceChoice:
    """Rooms with heat_source_price_aware follow the electricity price level (#84, #257, #314)."""

    def test_expensive_electricity_prefers_the_primary_source_on_a_mild_day(self):
        hass = _make_hass(["heat", "cool", "off"])
        # Mild outdoor: the outdoor rule alone would pick the AC
        result = evaluate_heat_sources(_make_room(), MODE_HEATING, 0.5, 20.5, 21.0, 12.0, "none", hass, "expensive")
        assert result.active_sources == "primary"
        assert "electricity expensive" in result.reason

    def test_cheap_electricity_prefers_the_ac_on_a_cold_day(self):
        hass = _make_hass(["heat", "cool", "off"])
        result = evaluate_heat_sources(_make_room(), MODE_HEATING, 0.5, 20.5, 21.0, 0.0, "none", hass, "cheap")
        assert result.active_sources == "secondary"

    def test_large_gap_and_ac_minimum_outdoor_still_win(self):
        hass = _make_hass(["heat", "cool", "off"])
        both = evaluate_heat_sources(_make_room(), MODE_HEATING, 1.0, 16.0, 21.0, 12.0, "none", hass, "expensive")
        assert both.active_sources == "both"
        frozen = evaluate_heat_sources(_make_room(), MODE_HEATING, 0.5, 20.5, 21.0, -20.0, "none", hass, "cheap")
        assert frozen.active_sources == "primary"

    def test_normal_or_unknown_level_keeps_the_outdoor_rule(self):
        hass = _make_hass(["heat", "cool", "off"])
        for level in ("normal", None):
            result = evaluate_heat_sources(_make_room(), MODE_HEATING, 0.5, 20.5, 21.0, 12.0, "none", hass, level)
            assert result.active_sources == "secondary"
