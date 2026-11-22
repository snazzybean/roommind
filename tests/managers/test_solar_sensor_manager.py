"""Tests for solar_sensor_manager.py: the per-room sun sensor (#303)."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from custom_components.roommind.const import (
    COVER_MAX_EFFECTIVENESS,
    SOLAR_SENSOR_STALE_S,
)
from custom_components.roommind.control.solar import compute_q_solar_norm, solar_azimuth
from custom_components.roommind.managers.cover_manager import compute_shading_factor
from custom_components.roommind.managers.solar_sensor_manager import (
    KIND_ILLUMINANCE,
    KIND_IRRADIANCE,
    KIND_PERCENT,
    POSITION_INSIDE,
    POSITION_OUTSIDE,
    SolarSensorManager,
    solar_sensor_kind,
)

LAT, LON = 52.5, 13.4
SENSOR = "sensor.room_sun"
# 2026-06-21 00:00 UTC, a long clear day
DAY0 = datetime(2026, 6, 21, tzinfo=UTC).timestamp()
STEP = 60.0
CLOSED = compute_shading_factor([0])


def _state(value, unit="W/m²", device_class="irradiance", reported=None):
    attrs = {"unit_of_measurement": unit}
    if device_class:
        attrs["device_class"] = device_class
    ts = datetime.fromtimestamp(reported, tz=UTC) if reported is not None else None
    return SimpleNamespace(state=str(value), attributes=attrs, last_reported=ts, last_updated=ts)


class _Hass:
    def __init__(self):
        self.config = SimpleNamespace(latitude=LAT, longitude=LON)
        self._states: dict = {}
        self.states = SimpleNamespace(get=self._states.get)

    def set(self, entity_id, state):
        self._states[entity_id] = state


def _q(ts):
    return compute_q_solar_norm(LAT, LON, ts)


def _east(ts):
    """A sensor on an east facade: twice GHI while the sun is in the east, nothing after noon."""
    return 2.0 if solar_azimuth(LAT, LON, ts) < 180.0 else 0.0


def _run(mgr, hass, start, hours, value_of, shading_of=lambda ts: 1.0, area="room", **state_kw):
    """Drive the manager for *hours*; value_of(ts, q_model, shading) is the sensor reading."""
    out = None
    ts = start
    end = start + hours * 3600
    while ts < end:
        q = _q(ts)
        sf = shading_of(ts)
        hass.set(SENSOR, _state(value_of(ts, q, sf), reported=ts, **state_kw))
        out = mgr.update(area, SENSOR, q, sf, ts)
        ts += STEP
    return out, ts


def _calibrated(value_of=lambda ts, q, sf: 1000.0 * q, **kw):
    hass = _Hass()
    mgr = SolarSensorManager(hass)
    _, ts = _run(mgr, hass, DAY0, 48, value_of, **kw)
    return mgr, hass, ts


@pytest.mark.parametrize(
    ("attrs", "kind"),
    [
        ({"device_class": "irradiance", "unit_of_measurement": "W/m²"}, KIND_IRRADIANCE),
        ({"unit_of_measurement": "W/m²"}, KIND_IRRADIANCE),
        ({"device_class": "illuminance", "unit_of_measurement": "lx"}, KIND_ILLUMINANCE),
        ({"unit_of_measurement": "lx"}, KIND_ILLUMINANCE),
        ({"unit_of_measurement": "%"}, KIND_PERCENT),
        ({"device_class": "humidity", "unit_of_measurement": "%"}, None),
        ({"device_class": "battery", "unit_of_measurement": "%"}, None),
        ({"device_class": "temperature", "unit_of_measurement": "°C"}, None),
        ({}, None),
    ],
)
def test_kind_from_device_class_and_unit(attrs, kind):
    assert solar_sensor_kind(SimpleNamespace(state="1", attributes=attrs)) == kind


def test_no_sensor_no_input():
    mgr = SolarSensorManager(_Hass())
    assert mgr.update("room", "", 0.5, 1.0, DAY0) is None
    assert mgr.status("room") is None


def test_weather_model_until_a_sunny_day_is_over():
    hass = _Hass()
    mgr = SolarSensorManager(hass)
    out, ts = _run(mgr, hass, DAY0, 38, lambda ts, q, sf: 800.0 * q)
    assert out is None
    # One day is not enough: its cloud nowcast error would stay in the scale
    assert mgr.status("room")["state"] == "learning"
    # The scale is fixed at dusk of the second day, never in daylight
    out, ts = _run(mgr, hass, ts, 10, lambda ts, q, sf: 800.0 * q)
    assert mgr.status("room")["state"] == "active"
    assert mgr.dirty


def test_too_little_sun_keeps_learning():
    hass = _Hass()
    mgr = SolarSensorManager(hass)
    # Overcast day: the model expects only a fifth of the sun
    ts = DAY0
    while ts < DAY0 + 86400:
        q = _q(ts) * 0.05
        hass.set(SENSOR, _state(1000 * q, reported=ts))
        assert mgr.update("room", SENSOR, q, 1.0, ts) is None
        ts += STEP
    assert mgr.status("room")["state"] == "learning"


@pytest.mark.parametrize(
    ("factor", "unit", "device_class"),
    [(1000.0, "W/m²", "irradiance"), (120_000.0, "lx", "illuminance"), (60.0, "%", None)],
)
def test_any_unit_ends_on_the_model_scale(factor, unit, device_class):
    mgr, hass, ts = _calibrated(lambda ts, q, sf: factor * q, unit=unit, device_class=device_class)
    noon = ts + 12 * 3600
    q = _q(noon)
    hass.set(SENSOR, _state(factor * q, unit=unit, device_class=device_class, reported=noon))
    out = mgr.update("room", SENSOR, q, 1.0, noon)
    assert out is not None and out.measured
    assert out.q_now == pytest.approx(q, rel=1e-6)
    assert out.q_effective == pytest.approx(q, rel=1e-6)


def test_measurement_is_the_input_and_clouds_show():
    mgr, hass, ts = _calibrated()
    noon = ts + 12 * 3600
    q = _q(noon)
    hass.set(SENSOR, _state(1000 * q * 0.3, reported=noon))  # a cloud the forecast does not know
    out = mgr.update("room", SENSOR, q, 1.0, noon)
    assert out.q_now == pytest.approx(0.3 * q, rel=1e-6)


def test_profile_learns_the_orientation_for_the_forecast():
    mgr, hass, ts = _calibrated(lambda ts, q, sf: 1000.0 * q * _east(ts))
    morning = ts + 7 * 3600
    q = _q(morning)
    hass.set(SENSOR, _state(1000 * q * _east(morning), reported=morning))
    out = mgr.update("room", SENSOR, q, 1.0, morning)
    # Normalized to the day: the east room gets about twice the model in the morning
    f = out.factors(morning, 12 * 12, 5.0)
    assert f[0] > 1.5
    # Afternoon (7 h later): the sun is behind the house
    assert f[7 * 12] < 0.2


def test_deviation_fades_back_to_the_profile():
    mgr, hass, ts = _calibrated()
    noon = ts + 12 * 3600
    # An hour under a cloud the forecast does not know
    _run(mgr, hass, noon - 3600, 1, lambda ts, q, sf: 300.0 * q)
    out = mgr.update("room", SENSOR, _q(noon), 1.0, noon)
    f = out.factors(noon, 12 * 8, 5.0)
    assert f[0] < 0.5
    assert f[-1] == pytest.approx(1.0, abs=0.1)
    assert all(a <= b + 1e-9 for a, b in zip(f, f[1:], strict=False))


def test_closed_covers_never_teach_the_forecast():
    """RoomMind closing a cover must not lower the sun it expects (shutters would open again)."""
    mgr, hass, ts = _calibrated()
    before = list(mgr._rooms["room"].profile)
    noon = ts + 12 * 3600
    # Sensor behind the cover: drops to the shading share while the cover is down
    out, _ = _run(mgr, hass, noon - 2 * 3600, 2, lambda ts, q, sf: 1000.0 * q * sf, shading_of=lambda ts: CLOSED)
    assert mgr._rooms["room"].profile == before
    f = out.factors(noon, 12, 5.0)
    assert min(f) > 0.9


def test_unknown_position_uses_the_model_while_shaded():
    mgr, hass, ts = _calibrated()
    t = ts + 12 * 3600
    q = _q(t)
    hass.set(SENSOR, _state(1000 * q * CLOSED, reported=t))
    out = mgr.update("room", SENSOR, q, CLOSED, t)
    assert mgr.status("room")["position"] is None
    assert not out.measured
    assert out.q_effective == pytest.approx(out.q_now * CLOSED)
    assert out.q_now == pytest.approx(q, rel=0.05)


def test_sensor_behind_the_cover_is_recognized_and_not_shaded_twice():
    mgr, hass, ts = _calibrated()
    noon = ts + 12 * 3600
    out, _ = _run(mgr, hass, noon - 2 * 3600, 2, lambda ts, q, sf: 1000.0 * q * sf, shading_of=lambda ts: CLOSED)
    assert mgr.status("room")["position"] == POSITION_INSIDE
    q = _q(noon)
    assert out.q_effective == pytest.approx(q * CLOSED, rel=0.05)
    # The unshaded input stays the sun outside, for the cover logic
    assert out.q_now == pytest.approx(q, rel=0.05)


def test_sensor_outside_is_recognized_and_shaded_once():
    mgr, hass, ts = _calibrated()
    noon = ts + 12 * 3600
    out, _ = _run(mgr, hass, noon - 2 * 3600, 2, lambda ts, q, sf: 1000.0 * q, shading_of=lambda ts: CLOSED)
    assert mgr.status("room")["position"] == POSITION_OUTSIDE
    q = _q(noon)
    assert out.measured
    assert out.q_effective == pytest.approx(q * CLOSED, rel=0.05)


def test_unavailable_falls_back_without_a_jump():
    mgr, hass, ts = _calibrated()
    t = ts + 10 * 3600
    _run(mgr, hass, t - 1800, 0.5, lambda ts, q, sf: 700.0 * q)
    q = _q(t)
    hass.set(SENSOR, _state(700 * q, reported=t))
    live = mgr.update("room", SENSOR, q, 1.0, t)
    hass.set(SENSOR, SimpleNamespace(state="unavailable", attributes={}, last_reported=None, last_updated=None))
    fallback = mgr.update("room", SENSOR, q, 1.0, t + 30)
    assert not fallback.measured
    assert mgr.status("room")["state"] == "unavailable"
    assert fallback.q_now == pytest.approx(live.q_now, rel=0.1)


def test_a_hanging_sensor_counts_as_unavailable_in_daylight():
    mgr, hass, ts = _calibrated()
    t = ts + 12 * 3600
    hass.set(SENSOR, _state(900, reported=t - SOLAR_SENSOR_STALE_S - 60))
    out = mgr.update("room", SENSOR, _q(t), 1.0, t)
    assert not out.measured


def test_lamp_light_at_night_is_no_sun():
    mgr, hass, ts = _calibrated()
    t = ts + 23 * 3600
    assert _q(t) == 0.0
    hass.set(SENSOR, _state(300, reported=t))
    out = mgr.update("room", SENSOR, 0.0, 1.0, t)
    assert out.q_now == 0.0 and out.q_effective == 0.0


def test_a_saturating_sensor_reads_at_least_the_model():
    cap = 450.0  # e.g. a lux sensor at its ceiling, in W/m² here

    def reading(ts, q, sf):
        return min(1000.0 * q, cap)

    hass = _Hass()
    mgr = SolarSensorManager(hass)
    _, ts = _run(mgr, hass, DAY0, 48, reading)
    noon = ts + 12 * 3600
    q = _q(noon)
    hass.set(SENSOR, _state(cap, reported=noon))
    out = mgr.update("room", SENSOR, q, 1.0, noon)
    assert not out.measured
    assert out.q_now >= cap / mgr._rooms["room"].scale


def test_state_round_trip_and_a_new_entity_starts_over():
    mgr, hass, ts = _calibrated(lambda ts, q, sf: 1000.0 * q * _east(ts))
    data = mgr.get_state()
    other = SolarSensorManager(hass)
    other.load_state(data)
    assert other._rooms["room"].scale == pytest.approx(mgr._rooms["room"].scale)
    assert other._rooms["room"].profile == pytest.approx(mgr._rooms["room"].profile, abs=1e-3)
    assert other.status("room")["state"] == "active"
    t = ts + 3600
    hass.set("sensor.other", _state(5, reported=t))
    assert other.update("room", "sensor.other", _q(t), 1.0, t) is None
    assert other.status("room")["state"] == "learning"


def test_unreadable_state_is_dropped():
    mgr = SolarSensorManager(_Hass())
    mgr.load_state({"room": {"kind": "irradiance"}, "ok": {"entity_id": SENSOR, "scale": None}})
    assert mgr.status("room") is None
    assert mgr.status("ok")["state"] == "learning"


def test_removed_sensor_and_room_drop_their_state():
    mgr, hass, ts = _calibrated()
    mgr.dirty = False
    assert mgr.update("room", "", 0.5, 1.0, ts) is None
    assert mgr.status("room") is None and mgr.dirty
    mgr2, _, _ = _calibrated()
    mgr2.prune(set())
    assert mgr2.status("room") is None


def test_an_unknown_unit_never_activates():
    hass = _Hass()
    mgr = SolarSensorManager(hass)
    _run(mgr, hass, DAY0, 24, lambda ts, q, sf: 50.0, unit="°C", device_class="temperature")
    assert mgr.status("room")["state"] == "unsupported"


def test_full_shading_factor_matches_the_cover_model():
    assert CLOSED == pytest.approx(1.0 - COVER_MAX_EFFECTIVENESS)


def test_a_sensor_that_appears_late_keeps_its_learning():
    hass = _Hass()
    mgr = SolarSensorManager(hass)
    assert solar_sensor_kind(None) is None
    # Before the entity has a state (HA still starting)
    assert mgr.update("room", SENSOR, 0.0, 1.0, DAY0) is None
    assert mgr.status("room")["kind"] is None
    _run(mgr, hass, DAY0 + 60, 48, lambda ts, q, sf: 1000.0 * q)
    assert mgr.status("room") == {"kind": KIND_IRRADIANCE, "state": "active", "position": None}


@pytest.mark.parametrize("value", ["abc", "-5", "nan"])
def test_an_unusable_reading_falls_back(value):
    mgr, hass, ts = _calibrated()
    t = ts + 12 * 3600
    hass.set(SENSOR, _state(value, reported=t))
    assert not mgr.update("room", SENSOR, _q(t), 1.0, t).measured


def test_a_calibration_in_progress_survives_a_restart():
    hass = _Hass()
    mgr = SolarSensorManager(hass)
    _, ts = _run(mgr, hass, DAY0, 38, lambda ts, q, sf: 800.0 * q)
    other = SolarSensorManager(hass)
    other.load_state(mgr.get_state())
    assert sum(other._rooms["room"].cal_model) == pytest.approx(sum(mgr._rooms["room"].cal_model))
    _run(other, hass, ts, 10, lambda ts, q, sf: 800.0 * q)
    assert other.status("room")["state"] == "active"


def test_the_position_turns_when_the_evidence_does():
    mgr, hass, ts = _calibrated()
    noon = ts + 12 * 3600
    # Half-open covers and an unlearned direction tell nothing
    _run(mgr, hass, noon - 3600, 1, lambda ts, q, sf: 1000.0 * q, shading_of=lambda ts: 0.85)
    assert mgr.status("room")["position"] is None
    _run(mgr, hass, noon - 3 * 3600, 2, lambda ts, q, sf: 1000.0 * q * sf, shading_of=lambda ts: CLOSED)
    assert mgr.status("room")["position"] == POSITION_INSIDE
    # A spell in between keeps the call
    _run(mgr, hass, noon - 3600, 1, lambda ts, q, sf: 1000.0 * q * 0.9, shading_of=lambda ts: CLOSED)
    assert mgr.status("room")["position"] == POSITION_INSIDE
    # Long shaded spells outside: the old evidence fades and the call turns
    for day in range(3):
        _run(mgr, hass, noon + day * 86400 - 3 * 3600, 6, lambda ts, q, sf: 1000.0 * q, shading_of=lambda ts: CLOSED)
    assert mgr.status("room")["position"] == POSITION_OUTSIDE


def test_position_needs_a_learned_direction():
    mgr, hass, ts = _calibrated()
    st = mgr._rooms["room"]
    st.weight = [0.0] * len(st.weight)
    t = ts + 12 * 3600
    _run(mgr, hass, t, 1, lambda ts, q, sf: 1000.0 * q * sf, shading_of=lambda ts: CLOSED)
    assert mgr.status("room")["position"] is None


def test_a_room_shaded_most_of_the_day_does_not_calibrate_on_the_rest():
    hass = _Hass()
    mgr = SolarSensorManager(hass)
    # Covers down from 08:00 UTC every day: only the early morning is seen open
    _run(
        mgr,
        hass,
        DAY0,
        48,
        lambda ts, q, sf: 1000.0 * q,
        shading_of=lambda ts: 1.0 if (ts - DAY0) % 86400 < 8 * 3600 else CLOSED,
    )
    assert mgr.status("room")["state"] == "learning"


def test_a_reading_far_above_the_model_is_clamped():
    mgr, hass, ts = _calibrated()
    t = ts + 12 * 3600
    q = _q(t)
    hass.set(SENSOR, _state(1000 * q * 50, reported=t))
    out = mgr.update("room", SENSOR, q, 1.0, t)
    assert out.q_now == pytest.approx(4.0 * q)


def test_a_cover_that_lets_more_light_through_than_modelled_still_counts_as_inside():
    """Open slats: the reading drops to 80 % where RoomMind's shading factor says 15 %."""
    mgr, hass, ts = _calibrated()
    noon = ts + 12 * 3600
    _run(mgr, hass, noon - 2 * 3600, 2, lambda ts, q, sf: 1000.0 * q * 0.8, shading_of=lambda ts: CLOSED)
    assert mgr.status("room")["position"] == POSITION_INSIDE


def test_winter_calibrates_on_the_short_sun_path():
    """December: few azimuth bins with sun at all; the calibration needs a share of them, not a fixed count."""
    hass = _Hass()
    mgr = SolarSensorManager(hass)
    dec = datetime(2026, 12, 21, tzinfo=UTC).timestamp()
    _run(mgr, hass, dec, 24 * 4, lambda ts, q, sf: 1000.0 * q)
    assert mgr.status("room")["state"] == "active"


def test_the_clamp_follows_clear_sky_not_the_cloud_forecast():
    """Forecast overcast, sun out: the reading is what the room gets."""
    mgr, hass, ts = _calibrated()
    t = ts + 12 * 3600
    clear = _q(t)
    hass.set(SENSOR, _state(1000 * clear, reported=t))
    out = mgr.update("room", SENSOR, clear * 0.2, 1.0, t)
    assert out.q_now == pytest.approx(clear, rel=1e-6)


def test_a_sliver_of_a_second_day_does_not_count():
    """Day one in full, then only minutes of the next: one day's nowcast error would set the scale alone."""
    hass = _Hass()
    mgr = SolarSensorManager(hass)
    _, ts = _run(mgr, hass, DAY0, 24, lambda ts, q, sf: 1000.0 * q)
    noon = ts + 12 * 3600
    _run(mgr, hass, noon, 0.1, lambda ts, q, sf: 1000.0 * q)
    hass.set(SENSOR, _state(0, reported=ts + 86000))
    mgr.update("room", SENSOR, 0.0, 1.0, ts + 86000)
    assert mgr.status("room")["state"] == "learning"


@pytest.mark.parametrize(("lat", "lon"), [(-33.9, 151.2), (21.3, -157.8)])
def test_a_sun_day_across_utc_midnight_counts_once(lat, lon):
    """Sydney and Honolulu see their sun around UTC midnight: one local day is one calibration day."""
    hass = _Hass()
    hass.config = SimpleNamespace(latitude=lat, longitude=lon)
    mgr = SolarSensorManager(hass)
    # From local midnight over one whole local day, a flat sensor capped below the noon sun
    start = DAY0 - lon / 15 * 3600
    ts = start
    while ts < start + 86400:
        q = compute_q_solar_norm(lat, lon, ts)
        hass.set(SENSOR, _state(min(1000.0 * q, 300.0), reported=ts))
        mgr.update("room", SENSOR, q, 1.0, ts)
        ts += STEP
    st = mgr._rooms["room"]
    assert len(st.cal_days) == 1
    assert len(st.peak_days) == 1
    assert st.scale is None
