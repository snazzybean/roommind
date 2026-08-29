"""Tests for the AC coil dry manager."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.roommind.managers.ac_coil_dry_manager import AcCoilDryManager
from custom_components.roommind.utils.device_utils import COIL_DRY_STALE_SECONDS

AC_EID = "climate.living_ac"


def build_hass(fan_mode="auto", fan_modes=None, hvac_modes=None, state="cool"):
    """Mock hass with one AC entity."""
    hass = MagicMock()
    hass.services.async_call = AsyncMock()
    ac_state = MagicMock()
    ac_state.state = state
    ac_state.attributes = {
        "hvac_modes": hvac_modes if hvac_modes is not None else ["off", "cool", "heat", "fan_only", "dry"],
        "fan_modes": fan_modes if fan_modes is not None else ["auto", "low", "medium", "high"],
        "fan_mode": fan_mode,
        "min_temp": 16.0,
        "max_temp": 30.0,
        "temperature": 22.0,
    }
    hass.states.get = MagicMock(return_value=ac_state)
    return hass


def make_room(**overrides):
    """Room with a single AC device."""
    dev = {
        "entity_id": AC_EID,
        "type": "ac",
        "role": "auto",
        "idle_action": "off",
        "idle_fan_mode": "low",
        "setpoint_mode": "proportional",
        "coil_dry": "inherit",
        "coil_dry_minutes": 0,
        "coil_dry_mode": "",
        "coil_dry_fan_mode": "",
    }
    dev.update(overrides.pop("device", {}))
    room = {"area_id": "living_room", "devices": [dev], "acs": [AC_EID], "thermostats": []}
    room.update(overrides)
    return room


ENABLED = {"coil_dry_enabled": True}


async def process(
    mgr,
    *,
    mode,
    room=None,
    settings=None,
    commandable=True,
    force_off=False,
    forced_on=None,
    forced_off=None,
    exclude=None,
    can_activate=None,
):
    """Call async_process_room with sensible test defaults."""
    return await mgr.async_process_room(
        area_id="living_room",
        room=room if room is not None else make_room(),
        settings=settings if settings is not None else dict(ENABLED),
        mode=mode,
        commandable=commandable,
        compressor_forced_on=forced_on or set(),
        compressor_forced_off=forced_off or set(),
        exclude_eids=exclude or set(),
        force_off=force_off,
        can_activate=can_activate or (lambda _eid: True),
    )


@pytest.mark.asyncio
async def test_accumulates_cooling_time(monkeypatch):
    """Cooling for 5 min then stopping accumulates 300 wet seconds."""
    import custom_components.roommind.managers.ac_coil_dry_manager as mod

    now = [1000.0]
    monkeypatch.setattr(mod.time, "time", lambda: now[0])
    mgr = AcCoilDryManager(build_hass())

    await process(mgr, mode="cooling")
    assert mgr.state_for(AC_EID).cooling_since == 1000.0

    now[0] = 1300.0
    await process(mgr, mode="idle")
    st = mgr.state_for(AC_EID)
    assert st.wet_seconds == pytest.approx(300.0)
    assert st.cooling_since is None
    assert st.expires_at == pytest.approx(1300.0 + COIL_DRY_STALE_SECONDS)


@pytest.mark.asyncio
async def test_still_cooling_does_not_reset_start_time(monkeypatch):
    """Consecutive cooling cycles must not push cooling_since forward.

    The coordinator polls every 30s, so a multi-minute cooling run is many
    consecutive ``mode="cooling"`` calls, not one. If the rising-edge guard
    were dropped and ``cooling_since`` got overwritten every cycle instead of
    only on the first one, the whole run would still end up here — but this
    test then folds a 90s run into 30s of ``wet_seconds`` instead of 90.
    """
    import custom_components.roommind.managers.ac_coil_dry_manager as mod

    now = [0.0]
    monkeypatch.setattr(mod.time, "time", lambda: now[0])
    mgr = AcCoilDryManager(build_hass())

    await process(mgr, mode="cooling")
    now[0] = 30.0
    await process(mgr, mode="cooling")
    now[0] = 60.0
    await process(mgr, mode="cooling")

    now[0] = 90.0
    await process(mgr, mode="idle")
    assert mgr.state_for(AC_EID).wet_seconds == pytest.approx(90.0)


@pytest.mark.asyncio
async def test_accumulates_across_bangbang_bursts(monkeypatch):
    """Three short cooling bursts sum up — that is the point in bang-bang mode."""
    import custom_components.roommind.managers.ac_coil_dry_manager as mod

    now = [0.0]
    monkeypatch.setattr(mod.time, "time", lambda: now[0])
    mgr = AcCoilDryManager(build_hass())

    for _ in range(3):
        await process(mgr, mode="cooling")
        now[0] += 120.0
        await process(mgr, mode="idle")
        now[0] += 60.0

    assert mgr.state_for(AC_EID).wet_seconds == pytest.approx(360.0)


@pytest.mark.asyncio
async def test_wetness_expires_after_stale_seconds(monkeypatch):
    """Idle for longer than the stale window clears the accumulator."""
    import custom_components.roommind.managers.ac_coil_dry_manager as mod

    now = [0.0]
    monkeypatch.setattr(mod.time, "time", lambda: now[0])
    mgr = AcCoilDryManager(build_hass())

    await process(mgr, mode="cooling")
    now[0] = 120.0
    # coil dry disabled -> no run starts, accumulator just sits there
    await process(mgr, mode="idle", settings={})
    assert mgr.state_for(AC_EID).wet_seconds == pytest.approx(120.0)

    now[0] = 120.0 + COIL_DRY_STALE_SECONDS + 1
    await process(mgr, mode="idle", settings={})
    assert mgr.state_for(AC_EID).wet_seconds == 0.0
    assert mgr.state_for(AC_EID).expires_at is None


@pytest.mark.asyncio
async def test_heating_clears_wetness(monkeypatch):
    """In heating mode the indoor coil is a warm condenser -> dry."""
    import custom_components.roommind.managers.ac_coil_dry_manager as mod

    now = [0.0]
    monkeypatch.setattr(mod.time, "time", lambda: now[0])
    mgr = AcCoilDryManager(build_hass())

    await process(mgr, mode="cooling")
    now[0] = 600.0
    await process(mgr, mode="heating")
    assert mgr.state_for(AC_EID).wet_seconds == 0.0
    assert mgr.state_for(AC_EID).cooling_since is None


@pytest.mark.asyncio
async def test_no_accumulation_when_not_commandable(monkeypatch):
    """Climate control disabled -> RoomMind is not cooling anything."""
    import custom_components.roommind.managers.ac_coil_dry_manager as mod

    monkeypatch.setattr(mod.time, "time", lambda: 500.0)
    mgr = AcCoilDryManager(build_hass())
    await process(mgr, mode="cooling", commandable=False)
    assert mgr.state_for(AC_EID).cooling_since is None


@pytest.mark.asyncio
async def test_no_accumulation_when_compressor_forced_off(monkeypatch):
    """A device blocked by min-off never cooled, so nothing got wet."""
    import custom_components.roommind.managers.ac_coil_dry_manager as mod

    monkeypatch.setattr(mod.time, "time", lambda: 500.0)
    mgr = AcCoilDryManager(build_hass())
    await process(mgr, mode="cooling", forced_off={AC_EID})
    assert mgr.state_for(AC_EID).cooling_since is None


@pytest.mark.asyncio
async def test_trv_devices_are_ignored(monkeypatch):
    """Only ACs have an evaporator coil."""
    import custom_components.roommind.managers.ac_coil_dry_manager as mod

    monkeypatch.setattr(mod.time, "time", lambda: 500.0)
    mgr = AcCoilDryManager(build_hass())
    room = {
        "area_id": "living_room",
        "devices": [{"entity_id": "climate.trv", "type": "trv", "role": "auto"}],
        "thermostats": ["climate.trv"],
        "acs": [],
    }
    await process(mgr, mode="cooling", room=room)
    assert mgr.state_for("climate.trv") is None


@pytest.mark.asyncio
async def test_result_is_empty_without_active_run(monkeypatch):
    import custom_components.roommind.managers.ac_coil_dry_manager as mod

    monkeypatch.setattr(mod.time, "time", lambda: 500.0)
    mgr = AcCoilDryManager(build_hass())
    result = await process(mgr, mode="cooling")
    assert result.controlled_eids == set()
    assert result.active is False
    assert result.skip_ekf_training is False
