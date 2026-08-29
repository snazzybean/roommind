"""Tests for the AC coil dry manager."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.roommind.managers.ac_coil_dry_manager import AcCoilDryManager
from custom_components.roommind.utils.device_utils import COIL_DRY_FAN_MODE_KEEP, COIL_DRY_STALE_SECONDS

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


async def _wet(mgr, monkeypatch_time, seconds=900.0, settings=None):
    """Helper: accumulate `seconds` of cooling, then go idle."""
    await process(mgr, mode="cooling", settings=settings)
    monkeypatch_time[0] += seconds
    return await process(mgr, mode="idle", settings=settings)


@pytest.mark.asyncio
async def test_run_starts_after_enough_cooling(monkeypatch):
    """15 min cooling clears the 10 min threshold -> blow phase starts."""
    import custom_components.roommind.managers.ac_coil_dry_manager as mod

    now = [0.0]
    monkeypatch.setattr(mod.time, "time", lambda: now[0])
    hass = build_hass()
    mgr = AcCoilDryManager(hass)

    result = await _wet(mgr, now)

    st = mgr.state_for(AC_EID)
    assert st.phase == "blow"
    assert st.phase_until == pytest.approx(900.0 + 20 * 60)
    assert result.controlled_eids == {AC_EID}
    assert result.active is True
    assert result.phase == "blow"

    calls = [c for c in hass.services.async_call.call_args_list if c[0][0] == "climate"]
    services = [c[0][1] for c in calls]
    assert "set_hvac_mode" in services
    hvac_call = next(c for c in calls if c[0][1] == "set_hvac_mode")
    assert hvac_call[0][2]["hvac_mode"] == "fan_only"
    fan_call = next(c for c in calls if c[0][1] == "set_fan_mode")
    assert fan_call[0][2]["fan_mode"] == "low"


@pytest.mark.asyncio
async def test_no_run_below_threshold(monkeypatch):
    """5 min cooling is below the 10 min default threshold."""
    import custom_components.roommind.managers.ac_coil_dry_manager as mod

    now = [0.0]
    monkeypatch.setattr(mod.time, "time", lambda: now[0])
    mgr = AcCoilDryManager(build_hass())

    result = await _wet(mgr, now, seconds=300.0)
    assert mgr.state_for(AC_EID).phase is None
    assert result.controlled_eids == set()


@pytest.mark.asyncio
async def test_no_run_when_disabled(monkeypatch):
    import custom_components.roommind.managers.ac_coil_dry_manager as mod

    now = [0.0]
    monkeypatch.setattr(mod.time, "time", lambda: now[0])
    mgr = AcCoilDryManager(build_hass())
    await _wet(mgr, now, settings={})
    assert mgr.state_for(AC_EID).phase is None


@pytest.mark.asyncio
async def test_no_run_when_compressor_min_run_active(monkeypatch):
    """forced_on means the device must keep running — nothing to dry yet."""
    import custom_components.roommind.managers.ac_coil_dry_manager as mod

    now = [0.0]
    monkeypatch.setattr(mod.time, "time", lambda: now[0])
    mgr = AcCoilDryManager(build_hass())

    await process(mgr, mode="cooling")
    now[0] += 900.0
    await process(mgr, mode="idle", forced_on={AC_EID})
    assert mgr.state_for(AC_EID).phase is None


@pytest.mark.asyncio
async def test_no_run_when_idle_action_is_fan_only(monkeypatch):
    """The device is parked in fan_only anyway — a bounded run is a no-op."""
    import custom_components.roommind.managers.ac_coil_dry_manager as mod

    now = [0.0]
    monkeypatch.setattr(mod.time, "time", lambda: now[0])
    mgr = AcCoilDryManager(build_hass())
    room = make_room(device={"idle_action": "fan_only"})

    await process(mgr, mode="cooling", room=room)
    now[0] += 900.0
    await process(mgr, mode="idle", room=room)
    assert mgr.state_for(AC_EID).phase is None


@pytest.mark.asyncio
async def test_run_starts_with_fan_only_idle_action_under_force_off(monkeypatch):
    """force_off normalises idle_action to off (#368), so the run IS needed."""
    import custom_components.roommind.managers.ac_coil_dry_manager as mod

    now = [0.0]
    monkeypatch.setattr(mod.time, "time", lambda: now[0])
    mgr = AcCoilDryManager(build_hass())
    room = make_room(device={"idle_action": "fan_only"})

    await process(mgr, mode="cooling", room=room)
    now[0] += 900.0
    await process(mgr, mode="idle", room=room, force_off=True)
    assert mgr.state_for(AC_EID).phase == "blow"


@pytest.mark.asyncio
async def test_no_run_when_device_lacks_target_mode(monkeypatch):
    """Device without fan_only support -> warn once, no run."""
    import custom_components.roommind.managers.ac_coil_dry_manager as mod

    now = [0.0]
    monkeypatch.setattr(mod.time, "time", lambda: now[0])
    mgr = AcCoilDryManager(build_hass(hvac_modes=["off", "cool"]))

    await _wet(mgr, now)
    assert mgr.state_for(AC_EID).phase is None


@pytest.mark.asyncio
async def test_dry_mode_requires_compressor_can_activate(monkeypatch):
    """dry runs the compressor, so min-off must allow it."""
    import custom_components.roommind.managers.ac_coil_dry_manager as mod

    now = [0.0]
    monkeypatch.setattr(mod.time, "time", lambda: now[0])
    mgr = AcCoilDryManager(build_hass())
    settings = {"coil_dry_enabled": True, "coil_dry_mode": "dry"}

    await process(mgr, mode="cooling", settings=settings)
    now[0] += 900.0
    await process(mgr, mode="idle", settings=settings, can_activate=lambda _e: False)
    assert mgr.state_for(AC_EID).phase is None


@pytest.mark.asyncio
async def test_dry_mode_marks_compressor_active_and_skips_ekf(monkeypatch):
    """dry keeps the compressor running: report it and stop EKF training."""
    import custom_components.roommind.managers.ac_coil_dry_manager as mod

    now = [0.0]
    monkeypatch.setattr(mod.time, "time", lambda: now[0])
    mgr = AcCoilDryManager(build_hass())
    settings = {"coil_dry_enabled": True, "coil_dry_mode": "dry"}

    result = await _wet(mgr, now, settings=settings)
    assert result.compressor_active_eids == {AC_EID}
    assert result.skip_ekf_training is True


@pytest.mark.asyncio
async def test_fan_only_mode_does_not_skip_ekf(monkeypatch):
    """A fan moving room air is thermally negligible — train as idle."""
    import custom_components.roommind.managers.ac_coil_dry_manager as mod

    now = [0.0]
    monkeypatch.setattr(mod.time, "time", lambda: now[0])
    mgr = AcCoilDryManager(build_hass())

    result = await _wet(mgr, now)
    assert result.skip_ekf_training is False
    assert result.compressor_active_eids == set()


@pytest.mark.asyncio
async def test_run_completes_and_resets_wetness(monkeypatch):
    """After the blow phase expires the device is released and dry."""
    import custom_components.roommind.managers.ac_coil_dry_manager as mod

    now = [0.0]
    monkeypatch.setattr(mod.time, "time", lambda: now[0])
    mgr = AcCoilDryManager(build_hass())

    await _wet(mgr, now)
    now[0] += 20 * 60 + 1
    result = await process(mgr, mode="idle")

    st = mgr.state_for(AC_EID)
    assert st.phase is None
    assert st.wet_seconds == 0.0
    assert result.controlled_eids == set()
    assert result.active is False


@pytest.mark.asyncio
async def test_drain_phase_precedes_blow(monkeypatch):
    """With drain_minutes > 0 the device stays off first, then blows."""
    import custom_components.roommind.managers.ac_coil_dry_manager as mod

    now = [0.0]
    monkeypatch.setattr(mod.time, "time", lambda: now[0])
    mgr = AcCoilDryManager(build_hass())
    settings = {"coil_dry_enabled": True, "coil_dry_drain_minutes": 3}

    result = await _wet(mgr, now, settings=settings)
    assert mgr.state_for(AC_EID).phase == "drain"
    assert result.controlled_eids == {AC_EID}
    assert result.phase == "drain"

    now[0] += 3 * 60 + 1
    await process(mgr, mode="idle", settings=settings)
    assert mgr.state_for(AC_EID).phase == "blow"


@pytest.mark.asyncio
async def test_setback_without_force_off_skips_drain(monkeypatch):
    """§5.3: idle_action="setback" without force_off never really turns the
    device off, so a DRAIN phase would test a false premise — a starting run
    skips straight to BLOW instead.
    """
    import custom_components.roommind.managers.ac_coil_dry_manager as mod

    now = [0.0]
    monkeypatch.setattr(mod.time, "time", lambda: now[0])
    mgr = AcCoilDryManager(build_hass())
    settings = {"coil_dry_enabled": True, "coil_dry_drain_minutes": 3}
    room = make_room(device={"idle_action": "setback"})

    await process(mgr, mode="cooling", room=room, settings=settings)
    now[0] += 900.0
    result = await process(mgr, mode="idle", room=room, settings=settings)

    assert mgr.state_for(AC_EID).phase == "blow"
    assert result.phase == "blow"


@pytest.mark.asyncio
async def test_setback_with_force_off_still_drains(monkeypatch):
    """force_off normalises idle_action to off (#368), so DRAIN is meaningful
    again even though the device's own configured idle_action is "setback".
    """
    import custom_components.roommind.managers.ac_coil_dry_manager as mod

    now = [0.0]
    monkeypatch.setattr(mod.time, "time", lambda: now[0])
    mgr = AcCoilDryManager(build_hass())
    settings = {"coil_dry_enabled": True, "coil_dry_drain_minutes": 3}
    room = make_room(device={"idle_action": "setback"})

    await process(mgr, mode="cooling", room=room, settings=settings)
    now[0] += 900.0
    result = await process(mgr, mode="idle", room=room, settings=settings, force_off=True)

    assert mgr.state_for(AC_EID).phase == "drain"
    assert result.phase == "drain"


@pytest.mark.asyncio
async def test_unsupported_fan_mode_is_skipped(monkeypatch):
    """Brand-specific fan names: skip set_fan_mode, keep the device's speed."""
    import custom_components.roommind.managers.ac_coil_dry_manager as mod

    now = [0.0]
    monkeypatch.setattr(mod.time, "time", lambda: now[0])
    hass = build_hass(fan_modes=["Hoch", "Mittel", "Niedrig"], fan_mode="Mittel")
    mgr = AcCoilDryManager(hass)

    await _wet(mgr, now)
    calls = [c for c in hass.services.async_call.call_args_list if c[0][1] == "set_fan_mode"]
    assert calls == []
    assert mgr.state_for(AC_EID).phase == "blow"
    assert mgr.state_for(AC_EID).fan_mode == ""


@pytest.mark.asyncio
async def test_drain_phase_reasserts_idle_each_cycle(monkeypatch):
    """Mid-drain (before phase_until), the device is held off again every cycle.

    The coordinator polls every 30s, so a multi-minute drain is many
    consecutive ``mode="idle"`` calls, not one. Without the re-assert, the
    device would only be forced off once at the start and could drift back
    on for the rest of the drain window.
    """
    import custom_components.roommind.managers.ac_coil_dry_manager as mod

    now = [0.0]
    monkeypatch.setattr(mod.time, "time", lambda: now[0])
    hass = build_hass()
    mgr = AcCoilDryManager(hass)
    settings = {"coil_dry_enabled": True, "coil_dry_drain_minutes": 3}

    def off_calls():
        return [
            c
            for c in hass.services.async_call.call_args_list
            if c[0][0] == "climate" and c[0][1] == "set_hvac_mode" and c[0][2].get("hvac_mode") == "off"
        ]

    await _wet(mgr, now, settings=settings)
    assert mgr.state_for(AC_EID).phase == "drain"
    off_calls_after_start = len(off_calls())

    now[0] += 60.0  # still well inside the 3 min drain window
    await process(mgr, mode="idle", settings=settings)

    assert mgr.state_for(AC_EID).phase == "drain"
    assert len(off_calls()) > off_calls_after_start


@pytest.mark.asyncio
async def test_fan_mode_keep_sends_no_fan_command(monkeypatch, caplog):
    """coil_dry_fan_mode="__keep__" means: don't touch the fan speed at all.

    Distinct from an unsupported fan_mode name: that path still looks up
    ``fan_modes`` and logs a "does not support" debug line. "keep" must return
    before any of that, so the log must stay silent about fan_mode support.
    """
    import logging

    import custom_components.roommind.managers.ac_coil_dry_manager as mod

    now = [0.0]
    monkeypatch.setattr(mod.time, "time", lambda: now[0])
    hass = build_hass()
    mgr = AcCoilDryManager(hass)
    room = make_room(device={"coil_dry_fan_mode": COIL_DRY_FAN_MODE_KEEP})

    with caplog.at_level(logging.DEBUG):
        await process(mgr, mode="cooling", room=room)
        now[0] += 900.0
        await process(mgr, mode="idle", room=room)

    calls = [c for c in hass.services.async_call.call_args_list if c[0][1] == "set_fan_mode"]
    assert calls == []
    assert mgr.state_for(AC_EID).phase == "blow"
    assert mgr.state_for(AC_EID).fan_mode == ""
    assert "does not support fan_mode" not in caplog.text


@pytest.mark.asyncio
async def test_no_run_while_still_cooling_even_with_wet_seconds_over_threshold(monkeypatch):
    """wet_seconds is level-based and can already be over threshold while the
    device is actively cooling again — a prior attempt was merely blocked
    (compressor min-run here), not reset. The mode guard must still refuse to
    start a drying run while ``mode == COOLING``: that would fight the very
    cooling demand that just resumed.
    """
    import custom_components.roommind.managers.ac_coil_dry_manager as mod

    now = [0.0]
    monkeypatch.setattr(mod.time, "time", lambda: now[0])
    mgr = AcCoilDryManager(build_hass())

    await process(mgr, mode="cooling")
    now[0] += 900.0
    # Blocked start attempt: wet_seconds (900s) clears the threshold, but
    # compressor_forced_on prevents the run — wet_seconds is carried over.
    await process(mgr, mode="idle", forced_on={AC_EID})
    assert mgr.state_for(AC_EID).wet_seconds == pytest.approx(900.0)
    assert mgr.state_for(AC_EID).phase is None

    # Cooling resumes with the leftover wet_seconds still over threshold.
    result = await process(mgr, mode="cooling")
    assert mgr.state_for(AC_EID).phase is None
    assert result.controlled_eids == set()


@pytest.mark.asyncio
async def test_no_run_during_heating_even_with_zero_threshold(monkeypatch):
    """``coil_dry_min_cooling_minutes=0`` would otherwise let a freshly-reset
    ``wet_seconds == 0`` clear the threshold check trivially. The explicit
    mode guard is what actually keeps a run from starting while the AC heats
    — the indoor coil is a warm condenser, not something to dry.
    """
    import custom_components.roommind.managers.ac_coil_dry_manager as mod

    now = [0.0]
    monkeypatch.setattr(mod.time, "time", lambda: now[0])
    mgr = AcCoilDryManager(build_hass())
    settings = {"coil_dry_enabled": True, "coil_dry_min_cooling_minutes": 0}

    result = await process(mgr, mode="heating", settings=settings)
    assert mgr.state_for(AC_EID).phase is None
    assert result.controlled_eids == set()


@pytest.mark.asyncio
async def test_no_run_when_not_commandable_even_with_wet_seconds_over_threshold(monkeypatch):
    """``commandable=False`` (climate_control_active off / startup guard) must
    block a start outright — contract #36 forbids RoomMind from sending any
    command at all, and a fresh drying run would send set_hvac_mode/set_fan_mode.
    """
    import custom_components.roommind.managers.ac_coil_dry_manager as mod

    now = [0.0]
    monkeypatch.setattr(mod.time, "time", lambda: now[0])
    hass = build_hass()
    mgr = AcCoilDryManager(hass)

    await process(mgr, mode="cooling")
    now[0] += 900.0
    # The idle transition itself flushes cooling_since into wet_seconds (that
    # happens unconditionally in _update_wetness) — commandable=False here
    # only needs to block the *start*, on this same call.
    result = await process(mgr, mode="idle", commandable=False)
    assert mgr.state_for(AC_EID).wet_seconds == pytest.approx(900.0)
    assert mgr.state_for(AC_EID).phase is None
    assert result.controlled_eids == set()
    assert hass.services.async_call.call_args_list == []


@pytest.mark.asyncio
async def test_dry_mode_flags_only_active_during_blow_not_drain(monkeypatch):
    """dry mode's compressor_active_eids/skip_ekf_training must stay off while
    draining (the device is genuinely off, no compressor running) and only
    come on once blow actually starts the compressor.
    """
    import custom_components.roommind.managers.ac_coil_dry_manager as mod

    now = [0.0]
    monkeypatch.setattr(mod.time, "time", lambda: now[0])
    mgr = AcCoilDryManager(build_hass())
    settings = {"coil_dry_enabled": True, "coil_dry_mode": "dry", "coil_dry_drain_minutes": 3}

    result = await _wet(mgr, now, settings=settings)
    assert mgr.state_for(AC_EID).phase == "drain"
    assert result.compressor_active_eids == set()
    assert result.skip_ekf_training is False

    now[0] += 3 * 60 + 1
    result = await process(mgr, mode="idle", settings=settings)
    assert mgr.state_for(AC_EID).phase == "blow"
    assert result.compressor_active_eids == {AC_EID}
    assert result.skip_ekf_training is True


@pytest.mark.asyncio
async def test_cooling_demand_aborts_and_restores_fan(monkeypatch):
    """Room warms up again: release the device and give the fan speed back."""
    import custom_components.roommind.managers.ac_coil_dry_manager as mod

    now = [0.0]
    monkeypatch.setattr(mod.time, "time", lambda: now[0])
    hass = build_hass(fan_mode="auto")
    mgr = AcCoilDryManager(hass)

    await _wet(mgr, now)
    assert mgr.state_for(AC_EID).prev_fan_mode == "auto"

    # Device now reports the coil dry fan speed
    hass.states.get.return_value.attributes["fan_mode"] = "low"
    hass.services.async_call.reset_mock()

    now[0] += 60.0
    result = await process(mgr, mode="cooling")

    st = mgr.state_for(AC_EID)
    assert st.phase is None
    assert st.prev_fan_mode is None
    assert result.controlled_eids == set()  # released for async_apply
    assert st.wet_seconds > 0  # coil is getting wet again

    restore = [c for c in hass.services.async_call.call_args_list if c[0][1] == "set_fan_mode"]
    assert len(restore) == 1
    assert restore[0][0][2]["fan_mode"] == "auto"


@pytest.mark.asyncio
async def test_completed_run_restores_fan(monkeypatch):
    import custom_components.roommind.managers.ac_coil_dry_manager as mod

    now = [0.0]
    monkeypatch.setattr(mod.time, "time", lambda: now[0])
    hass = build_hass(fan_mode="high")
    mgr = AcCoilDryManager(hass)

    await _wet(mgr, now)
    hass.states.get.return_value.attributes["fan_mode"] = "low"
    hass.services.async_call.reset_mock()

    now[0] += 20 * 60 + 1
    await process(mgr, mode="idle")

    restore = [c for c in hass.services.async_call.call_args_list if c[0][1] == "set_fan_mode"]
    assert restore[0][0][2]["fan_mode"] == "high"
    assert mgr.state_for(AC_EID).prev_fan_mode is None


@pytest.mark.asyncio
async def test_manual_fan_change_wins_over_restore(monkeypatch):
    """Someone turned the fan up during the run: do not overwrite them."""
    import custom_components.roommind.managers.ac_coil_dry_manager as mod

    now = [0.0]
    monkeypatch.setattr(mod.time, "time", lambda: now[0])
    hass = build_hass(fan_mode="auto")
    mgr = AcCoilDryManager(hass)

    await _wet(mgr, now)
    hass.states.get.return_value.attributes["fan_mode"] = "high"  # human intervened
    hass.services.async_call.reset_mock()

    now[0] += 20 * 60 + 1
    await process(mgr, mode="idle")

    assert [c for c in hass.services.async_call.call_args_list if c[0][1] == "set_fan_mode"] == []
    assert mgr.state_for(AC_EID).prev_fan_mode is None


@pytest.mark.asyncio
async def test_heating_demand_aborts_and_clears_wetness(monkeypatch):
    import custom_components.roommind.managers.ac_coil_dry_manager as mod

    now = [0.0]
    monkeypatch.setattr(mod.time, "time", lambda: now[0])
    hass = build_hass(fan_mode="auto")
    mgr = AcCoilDryManager(hass)

    await _wet(mgr, now)
    hass.states.get.return_value.attributes["fan_mode"] = "low"

    now[0] += 60.0
    result = await process(mgr, mode="heating")

    st = mgr.state_for(AC_EID)
    assert st.phase is None
    assert st.wet_seconds == 0.0
    assert result.controlled_eids == set()


@pytest.mark.asyncio
async def test_config_disabled_mid_run_aborts(monkeypatch):
    import custom_components.roommind.managers.ac_coil_dry_manager as mod

    now = [0.0]
    monkeypatch.setattr(mod.time, "time", lambda: now[0])
    mgr = AcCoilDryManager(build_hass())

    await _wet(mgr, now)
    now[0] += 60.0
    await process(mgr, mode="idle", settings={})
    assert mgr.state_for(AC_EID).phase is None


@pytest.mark.asyncio
async def test_not_commandable_ends_phase_without_commands(monkeypatch):
    """Contract from #36: send nothing. The restore stays pending."""
    import custom_components.roommind.managers.ac_coil_dry_manager as mod

    now = [0.0]
    monkeypatch.setattr(mod.time, "time", lambda: now[0])
    hass = build_hass(fan_mode="auto")
    mgr = AcCoilDryManager(hass)

    await _wet(mgr, now)
    hass.states.get.return_value.attributes["fan_mode"] = "low"
    hass.services.async_call.reset_mock()

    now[0] += 60.0
    await process(mgr, mode="idle", commandable=False)

    assert hass.services.async_call.call_args_list == []
    st = mgr.state_for(AC_EID)
    assert st.phase is None
    assert st.prev_fan_mode == "auto"  # pending restore


@pytest.mark.asyncio
async def test_pending_restore_runs_when_commandable_returns(monkeypatch):
    import custom_components.roommind.managers.ac_coil_dry_manager as mod

    now = [0.0]
    monkeypatch.setattr(mod.time, "time", lambda: now[0])
    hass = build_hass(fan_mode="auto")
    mgr = AcCoilDryManager(hass)

    await _wet(mgr, now)
    hass.states.get.return_value.attributes["fan_mode"] = "low"
    now[0] += 60.0
    await process(mgr, mode="idle", commandable=False)
    hass.services.async_call.reset_mock()

    now[0] += 60.0
    # Coil dry disabled here too: the restore must fire (and no run start)
    # regardless of config state — this is a separate combination from
    # test_pending_restore_blocks_new_run_when_wet_and_enabled below, which
    # covers the case where config is enabled and wet_seconds is still over
    # threshold (the pending-restore guard alone has to carry that one).
    await process(mgr, mode="idle", settings={})

    restore = [c for c in hass.services.async_call.call_args_list if c[0][1] == "set_fan_mode"]
    assert restore[0][0][2]["fan_mode"] == "auto"
    assert mgr.state_for(AC_EID).prev_fan_mode is None


@pytest.mark.asyncio
async def test_keep_fan_mode_means_no_restore_machinery(monkeypatch):
    """fan_mode="" -> no set_fan_mode at all, so nothing to remember."""
    import custom_components.roommind.managers.ac_coil_dry_manager as mod

    now = [0.0]
    monkeypatch.setattr(mod.time, "time", lambda: now[0])
    hass = build_hass(fan_mode="auto")
    mgr = AcCoilDryManager(hass)
    settings = {"coil_dry_enabled": True, "coil_dry_fan_mode": ""}

    await _wet(mgr, now, settings=settings)
    assert mgr.state_for(AC_EID).prev_fan_mode is None
    assert [c for c in hass.services.async_call.call_args_list if c[0][1] == "set_fan_mode"] == []


@pytest.mark.asyncio
async def test_device_without_fan_mode_attribute(monkeypatch):
    """Device reports no fan_mode -> nothing to restore, no crash."""
    import custom_components.roommind.managers.ac_coil_dry_manager as mod

    now = [0.0]
    monkeypatch.setattr(mod.time, "time", lambda: now[0])
    hass = build_hass(fan_mode=None)
    mgr = AcCoilDryManager(hass)

    await _wet(mgr, now)
    assert mgr.state_for(AC_EID).prev_fan_mode is None
    assert mgr.state_for(AC_EID).phase == "blow"


@pytest.mark.asyncio
async def test_no_restore_after_already_restored(monkeypatch):
    """Once prev_fan_mode is cleared, a later cycle must not resend a stale
    restore. _end_phase deliberately never clears st.fan_mode (needed for the
    same-cycle abort->restore comparison), and the mocked device attribute
    does not move on its own — so on a second cycle 'current == st.fan_mode'
    would spuriously match again. Only the prev_fan_mode guard prevents a
    second set_fan_mode(fan_mode=None) call.
    """
    import custom_components.roommind.managers.ac_coil_dry_manager as mod

    now = [0.0]
    monkeypatch.setattr(mod.time, "time", lambda: now[0])
    hass = build_hass(fan_mode="high")
    mgr = AcCoilDryManager(hass)

    await _wet(mgr, now)
    hass.states.get.return_value.attributes["fan_mode"] = "low"
    now[0] += 20 * 60 + 1
    await process(mgr, mode="idle")  # completes the run and restores to "high"
    assert mgr.state_for(AC_EID).prev_fan_mode is None

    hass.services.async_call.reset_mock()
    now[0] += 60.0
    await process(mgr, mode="idle")

    assert [c for c in hass.services.async_call.call_args_list if c[0][1] == "set_fan_mode"] == []


@pytest.mark.asyncio
async def test_pending_restore_blocks_new_run_when_wet_and_enabled(monkeypatch):
    """A pending restore must win over starting a fresh run, even when coil
    dry is enabled and wet_seconds still clears the threshold — otherwise
    _start_run would overwrite prev_fan_mode with the device's *current*
    (still drying) fan mode in the very same call, losing the user's real
    original setting for good.
    """
    import custom_components.roommind.managers.ac_coil_dry_manager as mod

    now = [0.0]
    monkeypatch.setattr(mod.time, "time", lambda: now[0])
    hass = build_hass(fan_mode="auto")
    mgr = AcCoilDryManager(hass)

    await _wet(mgr, now)
    hass.states.get.return_value.attributes["fan_mode"] = "low"
    now[0] += 60.0
    await process(mgr, mode="idle", commandable=False)
    assert mgr.state_for(AC_EID).prev_fan_mode == "auto"  # pending restore

    hass.services.async_call.reset_mock()
    now[0] += 60.0
    # Commandable again, coil dry still enabled, wet_seconds still over
    # threshold (the run never completed) — without the guard this would
    # start a fresh run instead of restoring.
    result = await process(mgr, mode="idle")

    st = mgr.state_for(AC_EID)
    restore = [c for c in hass.services.async_call.call_args_list if c[0][1] == "set_fan_mode"]
    assert len(restore) == 1
    assert restore[0][0][2]["fan_mode"] == "auto"
    assert st.prev_fan_mode is None
    assert st.phase is None  # no new run started in this cycle
    assert result.controlled_eids == set()

    # Accepted cost: the new run starts one cycle later instead.
    hass.services.async_call.reset_mock()
    now[0] += 30.0
    await process(mgr, mode="idle")
    assert mgr.state_for(AC_EID).phase == "blow"


@pytest.mark.asyncio
async def test_assert_drain_exception_does_not_propagate(monkeypatch, caplog):
    """async_idle_device raising (e.g. the device dropped off the network)
    must not crash the coordinator cycle — it is logged and swallowed, and
    the drain phase keeps running so the next cycle can retry.
    """
    import logging

    import custom_components.roommind.managers.ac_coil_dry_manager as mod

    now = [0.0]
    monkeypatch.setattr(mod.time, "time", lambda: now[0])
    hass = build_hass()
    mgr = AcCoilDryManager(hass)
    settings = {"coil_dry_enabled": True, "coil_dry_drain_minutes": 3}
    monkeypatch.setattr(mod, "async_idle_device", AsyncMock(side_effect=RuntimeError("boom")))

    with caplog.at_level(logging.WARNING):
        result = await _wet(mgr, now, settings=settings)

    assert mgr.state_for(AC_EID).phase == "drain"  # state machine still advanced
    assert result.controlled_eids == {AC_EID}
    assert "coil dry drain failed on 'climate.living_ac'" in caplog.text


@pytest.mark.asyncio
async def test_call_exception_does_not_propagate(monkeypatch, caplog):
    """A climate service call raising (e.g. device unreachable) must not
    crash the coordinator cycle — it is logged and swallowed, and the state
    machine advances into the blow phase regardless.
    """
    import logging

    import custom_components.roommind.managers.ac_coil_dry_manager as mod

    now = [0.0]
    monkeypatch.setattr(mod.time, "time", lambda: now[0])
    hass = build_hass()
    hass.services.async_call = AsyncMock(side_effect=RuntimeError("boom"))
    mgr = AcCoilDryManager(hass)

    with caplog.at_level(logging.WARNING):
        result = await _wet(mgr, now)  # default drain_minutes=0 -> straight to blow

    assert mgr.state_for(AC_EID).phase == "blow"  # state machine still advanced
    assert result.active is True
    assert "coil dry climate.set_hvac_mode failed on 'climate.living_ac'" in caplog.text


@pytest.mark.asyncio
async def test_state_roundtrip_and_resume(monkeypatch):
    """A run interrupted by a restart continues with its remaining time."""
    import custom_components.roommind.managers.ac_coil_dry_manager as mod

    now = [1000.0]
    monkeypatch.setattr(mod.time, "time", lambda: now[0])
    mgr = AcCoilDryManager(build_hass(fan_mode="auto"))

    await _wet(mgr, now)  # blow until 1900 + 1200 = 3100
    dumped = mgr.get_state()
    assert dumped[AC_EID]["phase"] == "blow"
    assert dumped[AC_EID]["prev_fan_mode"] == "auto"

    now[0] = 2500.0  # still inside the phase
    fresh = AcCoilDryManager(build_hass(fan_mode="low"))
    fresh.load_state(dumped)
    st = fresh.state_for(AC_EID)
    assert st.phase == "blow"
    assert st.phase_until == pytest.approx(3100.0)
    assert st.prev_fan_mode == "auto"
    # Every persisted field survives the round trip, not just the three above —
    # mode/fan_mode are distinct non-default values so a swap or a load_state
    # key typo (e.g. raw.get("moed")) cannot pass silently.
    assert st.wet_seconds == pytest.approx(900.0)
    assert st.mode == "fan_only"
    assert st.fan_mode == "low"
    assert st.expires_at == pytest.approx(9100.0)


@pytest.mark.asyncio
async def test_expired_phase_is_dropped_on_load(monkeypatch):
    """Restart after the phase would have ended: drop it, keep prev_fan_mode."""
    import custom_components.roommind.managers.ac_coil_dry_manager as mod

    monkeypatch.setattr(mod.time, "time", lambda: 9999.0)
    mgr = AcCoilDryManager(build_hass())
    mgr.load_state(
        {
            AC_EID: {
                "wet_seconds": 900.0,
                "expires_at": None,
                "phase": "blow",
                "phase_until": 3100.0,
                "mode": "fan_only",
                "fan_mode": "low",
                "prev_fan_mode": "auto",
            }
        }
    )
    st = mgr.state_for(AC_EID)
    assert st.phase is None
    assert st.phase_until is None
    assert st.prev_fan_mode == "auto"  # pending restore survives


@pytest.mark.asyncio
async def test_get_state_folds_in_ongoing_cooling(monkeypatch):
    """Cooling time so far must not be lost across a restart."""
    import custom_components.roommind.managers.ac_coil_dry_manager as mod

    now = [0.0]
    monkeypatch.setattr(mod.time, "time", lambda: now[0])
    mgr = AcCoilDryManager(build_hass())

    await process(mgr, mode="cooling")
    now[0] = 480.0
    dumped = mgr.get_state()
    assert dumped[AC_EID]["wet_seconds"] == pytest.approx(480.0)


@pytest.mark.asyncio
async def test_get_state_omits_empty_entries(monkeypatch):
    """Nothing worth remembering -> nothing written."""
    import custom_components.roommind.managers.ac_coil_dry_manager as mod

    monkeypatch.setattr(mod.time, "time", lambda: 100.0)
    mgr = AcCoilDryManager(build_hass())
    await process(mgr, mode="idle")
    assert mgr.get_state() == {}


@pytest.mark.asyncio
async def test_load_state_tolerates_garbage(monkeypatch):
    """Corrupt persisted data must never break startup."""
    import custom_components.roommind.managers.ac_coil_dry_manager as mod

    monkeypatch.setattr(mod.time, "time", lambda: 100.0)
    mgr = AcCoilDryManager(build_hass())
    mgr.load_state(
        {
            AC_EID: {"wet_seconds": "nonsense"},
            "climate.x": None,
            "climate.y": {"phase": "blow", "phase_until": "corrupt"},
            "climate.z": {"expires_at": "corrupt"},
        }
    )
    assert mgr.state_for(AC_EID).wet_seconds == 0.0
    assert mgr.state_for("climate.x") is None
    # A non-numeric phase_until must not crash the "still running?" comparison —
    # it has to be treated like a phase whose end can't be confirmed: discarded.
    st_y = mgr.state_for("climate.y")
    assert st_y.phase is None
    assert st_y.phase_until is None
    # Same for expires_at: a non-numeric value must not crash the "expired?"
    # comparison in _update_wetness (`now >= st.expires_at`) — discarded, not
    # coerced into a crash that would take the whole room's climate control
    # down with it (the per-room try in the coordinator would swallow it, but
    # the bad value would otherwise survive every restart via get_state()).
    assert mgr.state_for("climate.z").expires_at is None
    mgr.load_state({})
    mgr.load_state(None)


@pytest.mark.asyncio
async def test_dirty_flag(monkeypatch):
    import custom_components.roommind.managers.ac_coil_dry_manager as mod

    now = [0.0]
    monkeypatch.setattr(mod.time, "time", lambda: now[0])
    mgr = AcCoilDryManager(build_hass())
    assert mgr.state_dirty is False
    await process(mgr, mode="cooling")
    assert mgr.state_dirty is True
    mgr.state_dirty = False
    assert mgr.state_dirty is False


@pytest.mark.asyncio
async def test_prune_drops_unknown_entities(monkeypatch):
    import custom_components.roommind.managers.ac_coil_dry_manager as mod

    monkeypatch.setattr(mod.time, "time", lambda: 100.0)
    mgr = AcCoilDryManager(build_hass())
    await process(mgr, mode="cooling")
    assert mgr.state_for(AC_EID) is not None

    mgr.prune({"climate.somewhere_else"})
    assert mgr.state_for(AC_EID) is None


@pytest.mark.asyncio
async def test_remove_room_drops_that_areas_entities(monkeypatch):
    """State is keyed by entity_id, so remove_room resolves via the area map."""
    import custom_components.roommind.managers.ac_coil_dry_manager as mod

    monkeypatch.setattr(mod.time, "time", lambda: 100.0)
    mgr = AcCoilDryManager(build_hass())
    await process(mgr, mode="cooling")

    mgr.remove_room("other_room")
    assert mgr.state_for(AC_EID) is not None
    mgr.remove_room("living_room")
    assert mgr.state_for(AC_EID) is None
