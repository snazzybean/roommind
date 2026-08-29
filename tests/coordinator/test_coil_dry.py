"""Coil dry integration tests through the coordinator."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from .conftest import _create_coordinator, _make_store_mock, make_mock_states_get

AC_EID = "climate.living_ac"

AC_ROOM = {
    "area_id": "living_room",
    "thermostats": [],
    "acs": [AC_EID],
    "devices": [
        {
            "entity_id": AC_EID,
            "type": "ac",
            "role": "auto",
            "heating_system_type": "",
            "idle_action": "off",
            "idle_fan_mode": "low",
            "setpoint_mode": "proportional",
            "coil_dry": "inherit",
            "coil_dry_minutes": 0,
            "coil_dry_mode": "",
            "coil_dry_fan_mode": "",
        }
    ],
    "temperature_sensor": "sensor.living_room_temp",
    "climate_mode": "auto",
    "schedules": [],
    "comfort_heat": 21.0,
    "comfort_cool": 24.0,
    "eco_heat": 17.0,
    "eco_cool": 27.0,
    "climate_control_enabled": True,
}

COIL_DRY_SETTINGS = {
    "coil_dry_enabled": True,
    "coil_dry_min_cooling_minutes": 1,
    "coil_dry_minutes": 20,
    "outdoor_temp_sensor": "sensor.outdoor_temp",
    "outdoor_cooling_min": 10,
}

# With no schedule entity the resolver falls back to the comfort targets
# (heat=21.0, cool=24.0), so this temperature forces cooling.
COOLING_TEMP = 30.0
# Long enough to clear both the MPC min-run block (2 x 5 min) and
# coil_dry_min_cooling_minutes=1, so cycle 2 really lands in idle.
COOLING_RUN_SECONDS = 900.0
IDLE_TEMP = 22.5  # dead band between comfort_heat=21.0 and comfort_cool=24.0


def _ac_entity_state(state="cool", current_temperature=26.0, extra_attrs=None):
    """Build the ``extra=`` payload for the AC entity.

    ``make_mock_states_get`` expects ``(state_str, attrs_dict)`` tuples.
    """
    attrs = {
        "hvac_modes": ["off", "cool", "heat", "fan_only", "dry"],
        "fan_modes": ["auto", "low", "high"],
        "fan_mode": "auto",
        "min_temp": 16.0,
        "max_temp": 30.0,
        "temperature": 22.0,
        "current_temperature": current_temperature,
    }
    if extra_attrs:
        attrs.update(extra_attrs)
    return (state, attrs)


def _setup(hass, rooms, settings):
    store = _make_store_mock(rooms=rooms, settings=settings)
    hass.data = {"roommind": {"store": store}}
    hass.services.async_call = AsyncMock()
    return store


async def _run_cycle(coordinator, temp, **kwargs):
    """One coordinator cycle at the given room temperature."""
    coordinator.hass.states.get = make_mock_states_get(
        temp=None if temp is None else str(temp),
        outdoor_temp="28.0",
        extra={AC_EID: _ac_entity_state(**kwargs)},
    )
    data = await coordinator._async_update_data()
    return data["rooms"]["living_room"]


def _age_compressor_min_run(coordinator, group_id):
    """Let the group's min-run timer expire.

    CompressorGroupManager reads ``time.monotonic()``, which the frozen wall
    clock does not move, so the run time has to be aged explicitly.
    """
    state = coordinator._compressor_manager.get_state(group_id)
    state.compressor_on_since -= COOLING_RUN_SECONDS


@pytest.fixture
def frozen_time(monkeypatch):
    """Freeze the wall clock and hand back a mutable cursor.

    ``mod.time`` is the stdlib module, so this replaces ``time.time`` process
    wide for the duration of the test — which is what these tests want: the
    manager and the coordinator's min-run tracking must see the same clock.
    ``time.monotonic`` is untouched, see :func:`_age_compressor_min_run`.
    """
    import custom_components.roommind.managers.ac_coil_dry_manager as mod

    now = [1000.0]
    monkeypatch.setattr(mod.time, "time", lambda: now[0])
    return now


@pytest.mark.asyncio
async def test_coil_dry_starts_when_cooling_ends(hass, mock_config_entry, frozen_time):
    """Cooling long enough, then target reached -> coil dry active."""
    _setup(hass, {"living_room": dict(AC_ROOM)}, dict(COIL_DRY_SETTINGS))
    coordinator = _create_coordinator(hass, mock_config_entry)

    await _run_cycle(coordinator, COOLING_TEMP)  # cooling
    frozen_time[0] += COOLING_RUN_SECONDS
    rs = await _run_cycle(coordinator, IDLE_TEMP)  # target reached -> idle

    assert rs["coil_dry_active"] is True
    assert rs["coil_dry_phase"] == "blow"
    assert rs["coil_dry_entities"] == [AC_EID]
    assert rs["coil_dry_until"] == frozen_time[0] + 20 * 60
    assert rs["mode"] == "idle"  # mode stays idle, no fourth mode


@pytest.mark.asyncio
async def test_coil_dry_runs_during_window_pause(hass, mock_config_entry, frozen_time):
    """Window open pauses cooling — exactly when drying matters most."""
    room = {**AC_ROOM, "window_sensors": ["binary_sensor.living_window"]}
    _setup(hass, {"living_room": room}, dict(COIL_DRY_SETTINGS))
    coordinator = _create_coordinator(hass, mock_config_entry)

    await _run_cycle(coordinator, COOLING_TEMP)

    frozen_time[0] += COOLING_RUN_SECONDS
    coordinator.hass.states.get = make_mock_states_get(
        temp=str(COOLING_TEMP),
        outdoor_temp="28.0",
        window_sensors={"binary_sensor.living_window": "on"},
        extra={AC_EID: _ac_entity_state()},
    )
    data = await coordinator._async_update_data()

    rs = data["rooms"]["living_room"]
    assert rs["window_open"] is True
    assert rs["coil_dry_active"] is True


@pytest.mark.asyncio
async def test_no_coil_dry_when_climate_control_disabled(hass, mock_config_entry, frozen_time):
    """Contract from #36: no commands at all."""
    settings = {**COIL_DRY_SETTINGS, "climate_control_active": False}
    _setup(hass, {"living_room": dict(AC_ROOM)}, settings)
    coordinator = _create_coordinator(hass, mock_config_entry)

    await _run_cycle(coordinator, COOLING_TEMP)
    frozen_time[0] += COOLING_RUN_SECONDS
    rs = await _run_cycle(coordinator, IDLE_TEMP)

    assert rs["coil_dry_active"] is False


@pytest.mark.asyncio
async def test_compressor_off_since_still_tracked_during_coil_dry(hass, mock_config_entry, frozen_time):
    """REGRESSION GUARD: coil dry must not bypass compressor min-off.

    If the coil dry entity were merged into cycling_eids, the tracking loop
    would skip update_member() and compressor_off_since would stay None.
    """
    settings = {
        **COIL_DRY_SETTINGS,
        "compressor_groups": [
            {
                "id": "g1",
                "name": "Outdoor",
                "members": [AC_EID],
                "min_run_minutes": 1,
                "min_off_minutes": 5,
            },
        ],
    }
    _setup(hass, {"living_room": dict(AC_ROOM)}, settings)
    coordinator = _create_coordinator(hass, mock_config_entry)

    await _run_cycle(coordinator, COOLING_TEMP)
    frozen_time[0] += COOLING_RUN_SECONDS
    _age_compressor_min_run(coordinator, "g1")
    rs = await _run_cycle(coordinator, IDLE_TEMP)

    assert rs["coil_dry_active"] is True
    group_state = coordinator._compressor_manager.get_state("g1")
    assert group_state is not None
    assert group_state.active_members == set()
    assert group_state.compressor_off_since is not None


@pytest.mark.asyncio
async def test_coil_dry_state_is_persisted(hass, mock_config_entry, frozen_time):
    """State must reach the store so a restart can resume."""
    store = _setup(hass, {"living_room": dict(AC_ROOM)}, dict(COIL_DRY_SETTINGS))
    coordinator = _create_coordinator(hass, mock_config_entry)

    await _run_cycle(coordinator, COOLING_TEMP)
    frozen_time[0] += COOLING_RUN_SECONDS
    await _run_cycle(coordinator, IDLE_TEMP)

    saved = [call.args[0] for call in store.async_save_settings.call_args_list if call.args]
    coil_payloads = [p["coil_dry_state"] for p in saved if "coil_dry_state" in p]
    assert coil_payloads, f"coil_dry_state never persisted, got {saved}"
    assert AC_EID in coil_payloads[-1]
    assert coil_payloads[-1][AC_EID]["phase"] == "blow"


@pytest.mark.asyncio
async def test_coil_dry_state_is_loaded_on_first_cycle(hass, mock_config_entry, frozen_time):
    """A run in flight before a restart continues instead of restarting."""
    settings = {
        **COIL_DRY_SETTINGS,
        "coil_dry_state": {
            AC_EID: {
                "wet_seconds": 600.0,
                "expires_at": None,
                "phase": "blow",
                "phase_until": frozen_time[0] + 600.0,
                "mode": "fan_only",
                "fan_mode": "low",
                "prev_fan_mode": "auto",
            }
        },
    }
    _setup(hass, {"living_room": dict(AC_ROOM)}, settings)
    coordinator = _create_coordinator(hass, mock_config_entry)

    rs = await _run_cycle(coordinator, IDLE_TEMP)

    assert rs["coil_dry_active"] is True
    assert rs["coil_dry_until"] == frozen_time[0] + 600.0


@pytest.mark.asyncio
async def test_coil_dry_state_pruned_for_unconfigured_device(hass, mock_config_entry, frozen_time):
    """State for a device no longer in any room must not survive a cycle."""
    settings = {
        **COIL_DRY_SETTINGS,
        "coil_dry_state": {
            "climate.ghost_ac": {
                "wet_seconds": 600.0,
                "expires_at": None,
                "phase": None,
                "phase_until": None,
                "mode": "",
                "fan_mode": "",
                "prev_fan_mode": None,
            }
        },
    }
    _setup(hass, {"living_room": dict(AC_ROOM)}, settings)
    coordinator = _create_coordinator(hass, mock_config_entry)

    await _run_cycle(coordinator, IDLE_TEMP)

    assert coordinator._coil_dry_manager.state_for("climate.ghost_ac") is None


@pytest.mark.asyncio
async def test_dry_mode_skips_ekf_training(hass, mock_config_entry, frozen_time):
    """dry runs the compressor: training as idle would corrupt alpha."""
    settings = {**COIL_DRY_SETTINGS, "coil_dry_mode": "dry"}
    _setup(hass, {"living_room": dict(AC_ROOM)}, settings)
    coordinator = _create_coordinator(hass, mock_config_entry)
    coordinator._ekf_training.process = MagicMock()
    coordinator._ekf_training.clear = MagicMock()

    await _run_cycle(coordinator, COOLING_TEMP)
    frozen_time[0] += COOLING_RUN_SECONDS
    coordinator._ekf_training.process.reset_mock()
    coordinator._ekf_training.clear.reset_mock()
    rs = await _run_cycle(coordinator, IDLE_TEMP)

    assert rs["coil_dry_active"] is True
    assert coordinator._ekf_training.process.called is False
    assert coordinator._ekf_training.clear.called is True


@pytest.mark.asyncio
async def test_fan_only_mode_still_trains_ekf(hass, mock_config_entry, frozen_time):
    """Counterpart: the fan_only default is thermally idle, so training runs."""
    _setup(hass, {"living_room": dict(AC_ROOM)}, dict(COIL_DRY_SETTINGS))
    coordinator = _create_coordinator(hass, mock_config_entry)
    coordinator._ekf_training.process = MagicMock()

    await _run_cycle(coordinator, COOLING_TEMP)
    frozen_time[0] += COOLING_RUN_SECONDS
    coordinator._ekf_training.process.reset_mock()
    rs = await _run_cycle(coordinator, IDLE_TEMP)

    assert rs["coil_dry_active"] is True
    assert coordinator._ekf_training.process.called is True


@pytest.mark.asyncio
async def test_dry_mode_tracked_as_compressor_active(hass, mock_config_entry, frozen_time):
    """coil_dry_mode="dry" really runs the compressor -> stays an active member."""
    settings = {
        **COIL_DRY_SETTINGS,
        "coil_dry_mode": "dry",
        "compressor_groups": [
            {
                "id": "g1",
                "name": "Outdoor",
                "members": [AC_EID],
                "min_run_minutes": 1,
                "min_off_minutes": 5,
            },
        ],
    }
    _setup(hass, {"living_room": dict(AC_ROOM)}, settings)
    coordinator = _create_coordinator(hass, mock_config_entry)

    await _run_cycle(coordinator, COOLING_TEMP)
    frozen_time[0] += COOLING_RUN_SECONDS
    _age_compressor_min_run(coordinator, "g1")
    rs = await _run_cycle(coordinator, IDLE_TEMP)

    assert rs["coil_dry_active"] is True
    group_state = coordinator._compressor_manager.get_state("g1")
    assert group_state.active_members == {AC_EID}


@pytest.mark.asyncio
async def test_coil_dry_device_excluded_from_async_apply(hass, mock_config_entry, frozen_time):
    """The manager owns the device: async_apply must not command it."""
    _setup(hass, {"living_room": dict(AC_ROOM)}, dict(COIL_DRY_SETTINGS))
    coordinator = _create_coordinator(hass, mock_config_entry)

    await _run_cycle(coordinator, COOLING_TEMP)
    frozen_time[0] += COOLING_RUN_SECONDS

    captured: list[set[str]] = []
    from custom_components.roommind.control.mpc_controller import MPCController

    original = MPCController.async_apply

    async def _spy(self, *args, exclude_eids=None, **kwargs):
        captured.append(set(exclude_eids or set()))
        return await original(self, *args, exclude_eids=exclude_eids, **kwargs)

    MPCController.async_apply = _spy
    try:
        rs = await _run_cycle(coordinator, IDLE_TEMP)
    finally:
        MPCController.async_apply = original

    assert rs["coil_dry_active"] is True
    assert captured and AC_EID in captured[-1]


@pytest.mark.asyncio
async def test_managed_mode_display_stays_idle_during_coil_dry(hass, mock_config_entry, frozen_time):
    """Spec 9.2 claims no code change is needed here - lock that in.

    During the blow phase the device sits in fan_only.  _observe_device_action
    falls into its else branch and returns (None, 0.0), then _infer_device_mode
    finds no branch for fan_only and yields idle.

    Managed mode derives the commanded mode from device capability, not from a
    room temperature, so the window pause is what ends the cooling run here.
    """
    room = {
        **AC_ROOM,
        "temperature_sensor": "",  # managed mode
        "window_sensors": ["binary_sensor.living_window"],
    }
    _setup(hass, {"living_room": room}, dict(COIL_DRY_SETTINGS))
    coordinator = _create_coordinator(hass, mock_config_entry)

    await _run_cycle(coordinator, None, current_temperature=COOLING_TEMP)
    frozen_time[0] += COOLING_RUN_SECONDS

    coordinator.hass.states.get = make_mock_states_get(
        temp=None,
        outdoor_temp="28.0",
        window_sensors={"binary_sensor.living_window": "on"},
        extra={
            AC_EID: _ac_entity_state(
                state="fan_only",
                current_temperature=IDLE_TEMP,
                extra_attrs={"hvac_action": "fan"},
            )
        },
    )
    data = await coordinator._async_update_data()

    rs = data["rooms"]["living_room"]
    assert rs["coil_dry_active"] is True
    assert rs["coil_dry_phase"] == "blow"
    assert rs["mode"] == "idle"


@pytest.mark.asyncio
async def test_room_removal_clears_coil_dry_state(hass, mock_config_entry, frozen_time):
    """Deleting a room must not leave orphaned coil dry state behind."""
    _setup(hass, {"living_room": dict(AC_ROOM)}, dict(COIL_DRY_SETTINGS))
    coordinator = _create_coordinator(hass, mock_config_entry)

    await _run_cycle(coordinator, COOLING_TEMP)
    assert coordinator._coil_dry_manager.state_for(AC_EID) is not None

    coordinator.async_request_refresh = AsyncMock()
    coordinator._history_store = None
    mock_registry = MagicMock()
    mock_registry.entities.values.return_value = []
    with patch("homeassistant.helpers.entity_registry.async_get", return_value=mock_registry):
        await coordinator.async_room_removed("living_room")

    assert coordinator._coil_dry_manager.state_for(AC_EID) is None


@pytest.mark.asyncio
async def test_outdoor_room_reports_coil_dry_fields(hass, mock_config_entry, frozen_time):
    """The outdoor early-return dict lists every field explicitly."""
    room = {**AC_ROOM, "is_outdoor": True}
    _setup(hass, {"living_room": room}, dict(COIL_DRY_SETTINGS))
    coordinator = _create_coordinator(hass, mock_config_entry)

    rs = await _run_cycle(coordinator, COOLING_TEMP)

    assert rs["coil_dry_active"] is False
    assert rs["coil_dry_phase"] is None
    assert rs["coil_dry_until"] is None
    assert rs["coil_dry_entities"] == []
