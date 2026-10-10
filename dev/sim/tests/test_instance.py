"""Instance directories and port leases."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from roommind_sim import instance as inst_mod


def test_parallel_runs_of_one_scenario_get_distinct_dirs(tmp_path, monkeypatch):
    monkeypatch.setenv("ROOMMIND_SIM_HOME", str(tmp_path))
    with ThreadPoolExecutor(8) as pool:
        dirs = list(pool.map(lambda _i: inst_mod.Instance.run("same").dir, range(8)))
    assert len(set(dirs)) == 8


def test_port_leases(tmp_path, monkeypatch):
    monkeypatch.setenv("ROOMMIND_SIM_HOME", str(tmp_path))
    a = inst_mod.allocate_port("run-a", batch=True)
    b = inst_mod.allocate_port("run-b", batch=True)
    assert a != b and a in inst_mod.BATCH_PORTS
    inst_mod.release_port("run-a")
    assert inst_mod.allocate_port("live-x") in inst_mod.LIVE_PORTS
    assert inst_mod.allocate_port("live-x") == inst_mod.allocate_port("live-x")  # stable
