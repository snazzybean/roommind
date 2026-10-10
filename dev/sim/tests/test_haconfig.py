"""HA config generation."""

from __future__ import annotations

import json
import os

import pytest
import yaml
from test_scenario import base

from roommind_sim.haconfig import build_schedule, write_ha_config
from roommind_sim.scenario import ScenarioError, load_scenario_dict


def _write(tmp_path, src_name="checkout_a"):
    scn = load_scenario_dict(base() | {"people": [{"id": "anna"}]})
    src = tmp_path / src_name
    (src / "custom_components" / "roommind").mkdir(parents=True, exist_ok=True)
    (src / "simhome").mkdir(exist_ok=True)
    cfg = tmp_path / "config"
    write_ha_config(
        cfg,
        scn,
        instance="main",
        port=8130,
        roommind_src=src / "custom_components" / "roommind",
        simhome_src=src / "simhome",
        trusted_cidrs=["127.0.0.1/32"],
    )
    return cfg, src


def test_configuration_without_http_and_default_config(tmp_path):
    cfg, _ = _write(tmp_path)
    conf = yaml.safe_load((cfg / "configuration.yaml").read_text())
    assert "http" not in conf and "default_config" not in conf
    assert "recorder" not in conf
    assert conf["homeassistant"]["time_zone"] == "Europe/Berlin"
    assert conf["homeassistant"]["auth_providers"][0]["allow_bypass_login"] is True
    assert conf["person"] == [{"id": "anna", "name": "anna", "device_trackers": ["device_tracker.anna_phone"]}]
    assert conf["schedule"]["wz_plan"]["monday"] == [{"from": "06:00:00", "to": "22:00:00"}]
    assert "saturday" not in conf["schedule"]["wz_plan"]
    http = json.loads((cfg / ".storage" / "http").read_text())
    assert http["data"]["stable"]["server_port"] == 8130
    assert http["data"]["pending"] is None


def test_symlinks_follow_the_calling_checkout(tmp_path):
    cfg, src = _write(tmp_path, "checkout_a")
    assert os.readlink(cfg / "custom_components" / "roommind") == str(src / "custom_components" / "roommind")
    cfg2, src2 = _write(tmp_path, "checkout_b")
    assert cfg2 == cfg
    assert os.readlink(cfg / "custom_components" / "simhome") == str(src2 / "simhome")


def test_onboarding_kept_once_written(tmp_path):
    cfg, _ = _write(tmp_path)
    marker = cfg / ".storage" / "onboarding"
    marker.write_text("custom")
    _write(tmp_path)
    assert marker.read_text() == "custom"


def test_schedule_shorthand_with_temperatures():
    sched = build_schedule(
        "schedule.x",
        {
            "daily": ["00:00-06:00@17"],
            "weekend": ["08:00-23:00@21.5/24", {"from": "23:00", "to": "24:00", "temperature": 18}],
        },
    )
    assert sched["monday"] == [{"from": "00:00:00", "to": "06:00:00", "data": {"temperature": 17.0}}]
    assert sched["sunday"][0]["data"] == {"heat_temperature": 21.5, "cool_temperature": 24.0}
    assert sched["sunday"][1] == {"from": "23:00:00", "to": "24:00:00", "data": {"temperature": 18}}


def test_schedule_bad_block():
    with pytest.raises(ScenarioError, match="invalid block"):
        build_schedule("x", {"daily": ["6 bis 22"]})
    with pytest.raises(ScenarioError, match="unknown day key"):
        build_schedule("x", {"montag": ["06:00-22:00"]})
