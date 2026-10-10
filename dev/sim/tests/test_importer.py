"""Diagnostics import: v1 exports work with assumptions, v2 exports seed state."""

from __future__ import annotations

import json

import pytest
import yaml

from roommind_sim.importer.diag import ImportError_, import_diagnostics, ws_keys
from roommind_sim.scenario import load_scenario_dict

ROOM_CFG = {
    "area_id": "living_room",
    "devices": [{"entity_id": "climate.living_room_trv", "type": "trv", "heating_system_type": "radiator"}],
    "thermostats": ["climate.living_room_trv"],
    "acs": [],
    "temperature_sensor": "sensor.living_room_temp",
    "window_sensors": ["binary_sensor.living_room_window"],
    "schedules": [{"entity_id": "schedule.heating"}],
    "climate_mode": "heat_only",
    "comfort_temp": 21.0,
    "override_until": None,
}
DEVICE_STATE = {
    "entity_id": "climate.living_room_trv",
    "type": "trv",
    "ha_state": "heat",
    "hvac_modes": ["off", "heat"],
    "temperature": 22.0,
    "min_temp": 5,
    "max_temp": 30,
}


def v1_export() -> dict:
    return {
        "data": {
            "integration": {"version": "1.6.0", "domain": "roommind", "ha_temp_unit": "°C"},
            "settings": {
                "outdoor_temp_sensor": "sensor.outdoor",
                "presence_persons": ["person.someone"],
                "valve_last_actuation": {},
            },
            "rooms": {
                "living_room": {
                    "config": ROOM_CFG,
                    "live": {"current_temp": 19.5, "override_active": False},
                    "device_states": [DEVICE_STATE],
                    "model": {"alpha": 0.02},
                }
            },
            "outdoor": {"temp": 4.0},
            "recent_history": {"living_room": [{"ts": "1768172400", "room_temp": "19.4", "outdoor_temp": "4.0"}]},
            "presence": {"person_states": {"person.someone": "not_home"}},
        }
    }


def v2_export() -> dict:
    data = v1_export()["data"]
    data["schema_version"] = 2
    data["integration"] |= {"time_zone": "Europe/Vienna", "latitude": 48, "longitude": 16, "unit_system": "metric"}
    room = data["rooms"]["living_room"]
    room["model_state"] = {"x": [19.5, 0.03, 2.0, 4.0, 0.1, 0.3], "P": [[1.0]], "n_updates": 900}
    room["schedule_blocks"] = {
        "schedule.heating": {
            "monday": [
                {"from": {"__type": "time", "isoformat": "06:00:00"}, "to": "22:00:00", "data": {"temperature": 21}}
            ]
        }
    }
    data["history_48h"] = {
        "living_room": [
            {"timestamp": str(1768172400 + 180 * i), "room_temp": "19.5", "outdoor_temp": "4.0", "mode": "idle"}
            for i in range(50)
        ]
    }
    return data


def _import(tmp_path, export, **kw):  # noqa: ANN001, ANN003
    src = tmp_path / "diag.json"
    src.write_text(json.dumps(export))
    path = import_diagnostics(src, out_root=tmp_path / "imports", name="t", **kw)
    data = yaml.safe_load(path.read_text())
    return data, load_scenario_dict(data)


def test_v1_export_imports_with_assumptions(tmp_path):
    data, scn = _import(tmp_path, v1_export())
    assert scn.location.time_zone == "Europe/Berlin"
    assert any("location" in a for a in data["assumptions"])
    assert any("EKF state not exported" in a for a in data["assumptions"])
    assert any("06:00-22:00 daily assumed" in a for a in data["assumptions"])
    dev = scn.rooms["living_room"].devices[0]
    assert dev.profile == "generic_trv" and dev.params["initial_mode"] == "heat"
    assert "valve_last_actuation" not in data["roommind"]["settings"]
    assert "override_until" not in data["roommind"]["rooms"]["living_room"]
    assert scn.people[0].plan["presence"]["weekday"] == ["away@00:00"]
    assert "thermal_data" not in data["seed_data"] and "history_dir" in data["seed_data"]


def test_v2_export_seeds_ekf_history_and_schedule(tmp_path):
    data, scn = _import(tmp_path, v2_export())
    assert scn.location.time_zone == "Europe/Vienna"
    seed = data["seed_data"]
    assert json.loads(open(seed["thermal_data"]).read())["living_room"]["n_updates"] == 900
    assert (tmp_path / "imports" / "t" / "history" / "living_room_detail.csv").exists()
    assert data["helpers"]["schedule"]["schedule.heating"]["monday"][0] == {
        "from": "06:00:00",
        "to": "22:00:00",
        "data": {"temperature": 21},
    }
    assert data["weather"]["anchor_temperature"] == 4.0
    assert scn.start == 1768172400 + 180 * 49


def test_replay_needs_history_and_writes_csvs(tmp_path):
    export = v1_export()
    export["data"]["recent_history"] = {}
    with pytest.raises(ImportError_, match="replay needs history"):
        _import(tmp_path, export, mode="replay")
    data, scn = _import(tmp_path, v2_export(), mode="replay")
    assert scn.replay["rooms"]["living_room"].endswith("replay-living_room.csv")
    assert scn.duration == 180 * 49
    assert data["weather"]["csv"].endswith("outdoor.csv")


def test_ws_keys_come_from_roommind_schema():
    keys = ws_keys("roommind/rooms/save")
    assert {"devices", "temperature_sensor", "climate_mode"} <= keys
    assert "override_until" not in keys
