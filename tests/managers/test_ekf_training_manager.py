"""Tests for EkfTrainingManager."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.roommind.const import EKF_UPDATE_MIN_DT
from custom_components.roommind.managers.ekf_training_manager import EkfTrainingManager


@pytest.fixture
def model_manager():
    mm = MagicMock()
    mm.update = MagicMock()
    mm.update_window_open = MagicMock()
    return mm


@pytest.fixture
def mgr(model_manager):
    m = EkfTrainingManager(model_manager)
    m._synced.update({"r1", "room1"})
    m._current.update({"r1", "room1"})
    return m


class TestFlush:
    def test_flush_with_accumulated_data_calls_update(self, mgr, model_manager):
        """Flush with accumulated data should call model_manager.update."""
        mgr._accumulated_dt["room1"] = 5.0
        mgr._accumulated_mode["room1"] = "heat"
        mgr._accumulated_pf["room1"] = 0.8
        mgr.flush(
            "room1",
            current_temp=20.0,
            T_outdoor=5.0,
            can_heat=True,
            can_cool=False,
            q_solar=0.0,
        )
        model_manager.update.assert_called_once_with(
            "room1",
            20.0,
            5.0,
            "heat",
            5.0,
            can_heat=True,
            can_cool=False,
            power_fraction=0.8,
            q_solar=0.0,
            q_residual=0.0,
            q_occupancy=0.0,
            q_rebound=None,
            q_power=0.0,
        )
        assert "room1" not in mgr._accumulated_dt
        assert "room1" not in mgr._accumulated_mode
        assert "room1" not in mgr._accumulated_pf

    def test_flush_without_accumulated_data_no_update(self, mgr, model_manager):
        """Flush with no accumulated data should not call update."""
        mgr.flush(
            "room1",
            current_temp=20.0,
            T_outdoor=5.0,
            can_heat=True,
            can_cool=False,
            q_solar=0.0,
        )
        model_manager.update.assert_not_called()

    def test_flush_zero_dt_no_update(self, mgr, model_manager):
        """Flush with accumulated_dt=0 should not call update."""
        mgr._accumulated_dt["room1"] = 0.0
        mgr._accumulated_mode["room1"] = "heat"
        mgr.flush(
            "room1",
            current_temp=20.0,
            T_outdoor=5.0,
            can_heat=True,
            can_cool=False,
            q_solar=0.0,
        )
        model_manager.update.assert_not_called()

    def test_flush_applies_shading_to_solar(self, mgr, model_manager):
        """q_solar passed to update should be multiplied by shading_factor."""
        mgr._accumulated_dt["room1"] = 3.0
        mgr._accumulated_mode["room1"] = "idle"
        mgr._accumulated_pf["room1"] = 1.0
        mgr.flush(
            "room1",
            current_temp=20.0,
            T_outdoor=5.0,
            can_heat=True,
            can_cool=False,
            q_solar=100.0,
            shading_factor=0.5,
        )
        _, kwargs = model_manager.update.call_args
        assert kwargs["q_solar"] == pytest.approx(50.0)


class TestProcess:
    COMMON = dict(
        current_temp=20.0,
        T_outdoor=5.0,
        q_residual=0.0,
        shading_factor=1.0,
        q_solar=0.0,
        can_heat=True,
        can_cool=False,
        dt_minutes=0.5,
    )

    def test_window_open_flushes_and_calls_update_window(self, mgr, model_manager):
        """Window open should flush + call update_window_open with learn_k_window=True."""
        mgr._accumulated_dt["r1"] = 3.0
        mgr._accumulated_mode["r1"] = "heat"
        mgr._accumulated_pf["r1"] = 1.0
        mgr.process(
            "r1",
            **self.COMMON,
            ekf_mode="heat",
            ekf_pf=1.0,
            window_open=True,
            raw_open=False,
        )
        model_manager.update.assert_called_once()  # flush
        model_manager.update_window_open.assert_called_once()
        _, kwargs = model_manager.update_window_open.call_args
        assert kwargs["learn_k_window"] is True
        assert "r1" not in mgr._accumulated_dt

    def test_window_open_no_learn_with_residual(self, mgr, model_manager):
        """Window open with q_residual > 0 → learn_k_window=False."""
        mgr.process(
            "r1",
            **{**self.COMMON, "q_residual": 0.5},
            ekf_mode="heat",
            ekf_pf=1.0,
            window_open=True,
            raw_open=False,
        )
        _, kwargs = model_manager.update_window_open.call_args
        assert kwargs["learn_k_window"] is False

    def test_raw_open_flushes_and_calls_update_window(self, mgr, model_manager):
        """raw_open (within delay) should also flush + update_window_open."""
        mgr.process(
            "r1",
            **self.COMMON,
            ekf_mode="heat",
            ekf_pf=1.0,
            window_open=False,
            raw_open=True,
        )
        model_manager.update_window_open.assert_called_once()

    def test_none_mode_flushes_only(self, mgr, model_manager):
        """ekf_mode=None should flush but NOT call update_window_open."""
        mgr._accumulated_dt["r1"] = 3.0
        mgr._accumulated_mode["r1"] = "heat"
        mgr._accumulated_pf["r1"] = 1.0
        mgr.process(
            "r1",
            **self.COMMON,
            ekf_mode=None,
            ekf_pf=0.0,
            window_open=False,
            raw_open=False,
        )
        model_manager.update.assert_called_once()
        model_manager.update_window_open.assert_not_called()
        assert "r1" not in mgr._accumulated_dt

    def test_accumulation_below_threshold(self, mgr, model_manager):
        """Process below EKF_UPDATE_MIN_DT should accumulate, not update."""
        mgr.process(
            "r1",
            **{**self.COMMON, "dt_minutes": 0.1},
            ekf_mode="heat",
            ekf_pf=1.0,
            window_open=False,
            raw_open=False,
        )
        model_manager.update.assert_not_called()
        assert mgr._accumulated_dt["r1"] == pytest.approx(0.1)
        assert mgr._accumulated_mode["r1"] == "heat"

    def test_accumulation_crosses_threshold_triggers_update(self, mgr, model_manager):
        """Accumulating past threshold should trigger model update."""
        mgr._accumulated_dt["r1"] = EKF_UPDATE_MIN_DT - 0.1
        mgr._accumulated_mode["r1"] = "heat"
        mgr._accumulated_pf["r1"] = 1.0
        mgr.process(
            "r1",
            **{**self.COMMON, "dt_minutes": 0.2},
            ekf_mode="heat",
            ekf_pf=1.0,
            window_open=False,
            raw_open=False,
        )
        model_manager.update.assert_called_once()
        assert mgr._accumulated_dt["r1"] == 0.0

    def test_mode_transition_flushes_before_accumulating(self, mgr, model_manager):
        """Switching from heat to cool should flush heat data first."""
        mgr._accumulated_dt["r1"] = 3.0
        mgr._accumulated_mode["r1"] = "heat"
        mgr._accumulated_pf["r1"] = 0.8
        mgr.process(
            "r1",
            **{**self.COMMON, "dt_minutes": 0.5},
            ekf_mode="cool",
            ekf_pf=0.6,
            window_open=False,
            raw_open=False,
        )
        first_call = model_manager.update.call_args_list[0]
        assert first_call.args[3] == "heat"
        assert mgr._accumulated_mode["r1"] == "cool"

    def test_power_fraction_weighted_average(self, mgr, model_manager):
        """Power fraction should be weighted by dt_minutes."""
        mgr._accumulated_dt["r1"] = 1.0
        mgr._accumulated_mode["r1"] = "heat"
        mgr._accumulated_pf["r1"] = 0.5
        mgr.process(
            "r1",
            **{**self.COMMON, "dt_minutes": 1.0},
            ekf_mode="heat",
            ekf_pf=1.0,
            window_open=False,
            raw_open=False,
        )
        # (0.5 * 1.0 + 1.0 * 1.0) / 2.0 = 0.75
        assert mgr._accumulated_pf["r1"] == pytest.approx(0.75)

    def test_last_temps_always_updated(self, mgr, model_manager):
        """last_temps should be updated on every process call."""
        mgr.process(
            "r1",
            **{**self.COMMON, "current_temp": 22.5},
            ekf_mode="heat",
            ekf_pf=1.0,
            window_open=False,
            raw_open=False,
        )
        assert mgr.last_temps["r1"] == 22.5

    def test_occupancy_passed_through(self, mgr, model_manager):
        """q_occupancy should be passed to model_manager.update."""
        mgr._accumulated_dt["r1"] = EKF_UPDATE_MIN_DT
        mgr._accumulated_mode["r1"] = "heat"
        mgr._accumulated_pf["r1"] = 1.0
        mgr.process(
            "r1",
            **{**self.COMMON, "dt_minutes": 1.0},
            ekf_mode="heat",
            ekf_pf=1.0,
            window_open=False,
            raw_open=False,
            q_occupancy=0.5,
        )
        _, kwargs = model_manager.update.call_args
        assert kwargs["q_occupancy"] == 0.5


class TestClearAndRemove:
    def test_clear_removes_accumulated_state(self, mgr):
        mgr._accumulated_dt["r1"] = 5.0
        mgr._accumulated_mode["r1"] = "heat"
        mgr._accumulated_pf["r1"] = 0.8
        mgr.clear("r1")
        assert "r1" not in mgr._accumulated_dt
        assert "r1" not in mgr._accumulated_mode
        assert "r1" not in mgr._accumulated_pf

    def test_clear_preserves_last_temps(self, mgr):
        mgr.last_temps["r1"] = 20.0
        mgr.clear("r1")
        assert mgr.last_temps["r1"] == 20.0

    def test_remove_room_clears_everything(self, mgr):
        mgr._accumulated_dt["r1"] = 5.0
        mgr._accumulated_mode["r1"] = "heat"
        mgr._accumulated_pf["r1"] = 0.8
        mgr.last_temps["r1"] = 20.0
        mgr.remove_room("r1")
        assert "r1" not in mgr._accumulated_dt
        assert "r1" not in mgr.last_temps

    def test_clear_nonexistent_room_no_error(self, mgr):
        mgr.clear("nonexistent")

    def test_remove_nonexistent_room_no_error(self, mgr):
        mgr.remove_room("nonexistent")


def test_rebound_is_averaged_over_the_batch():
    """The EKF gets the dt-weighted mean charge of a batch, not the value at flush time."""
    model_manager = MagicMock()
    mgr = EkfTrainingManager(model_manager)
    mgr._synced.add("room1")
    common = dict(
        T_outdoor=30.0,
        ekf_mode="idle",
        ekf_pf=0.0,
        window_open=False,
        raw_open=False,
        q_residual=0.0,
        shading_factor=1.0,
        q_solar=0.0,
        can_heat=False,
        can_cool=True,
        dt_minutes=1.5,
    )
    mgr.process("room1", current_temp=24.0, q_rebound=0.6, **common)
    model_manager.update.assert_not_called()
    mgr.process("room1", current_temp=24.2, q_rebound=0.2, **common)
    assert model_manager.update.call_args.kwargs["q_rebound"] == pytest.approx(0.4)


def test_rebound_none_drops_the_batch_mean():
    model_manager = MagicMock()
    mgr = EkfTrainingManager(model_manager)
    mgr._synced.add("room1")
    common = dict(
        T_outdoor=30.0,
        ekf_mode="idle",
        ekf_pf=0.0,
        window_open=False,
        raw_open=False,
        q_residual=0.0,
        shading_factor=1.0,
        q_solar=0.0,
        can_heat=False,
        can_cool=True,
        dt_minutes=1.5,
    )
    mgr.process("room1", current_temp=24.0, q_rebound=0.6, **common)
    mgr.process("room1", current_temp=24.2, q_rebound=None, **common)
    assert model_manager.update.call_args.kwargs["q_rebound"] is None


class TestResyncAfterGap:
    """A stale model temperature (restart, skipped cycles) must not be learned as a jump (#478)."""

    COMMON = dict(
        T_outdoor=10.0,
        ekf_mode="idle",
        ekf_pf=0.0,
        window_open=False,
        raw_open=False,
        q_residual=0.0,
        shading_factor=1.0,
        q_solar=0.0,
        can_heat=True,
        can_cool=False,
        dt_minutes=0.5,
    )

    def test_first_cycle_after_start_syncs_instead_of_learning(self, model_manager):
        mgr = EkfTrainingManager(model_manager)
        mgr.process("r1", current_temp=20.2, **self.COMMON)
        model_manager.sync_temperature.assert_called_once_with("r1", 20.2)
        model_manager.update.assert_not_called()
        assert "r1" not in mgr._accumulated_dt

    def test_learning_resumes_after_the_sync(self, model_manager):
        mgr = EkfTrainingManager(model_manager)
        for _ in range(int(EKF_UPDATE_MIN_DT / 0.5) + 1):
            mgr.process("r1", current_temp=20.2, **self.COMMON)
        model_manager.sync_temperature.assert_called_once()
        model_manager.update.assert_called_once()
        assert model_manager.update.call_args.args[4] == pytest.approx(EKF_UPDATE_MIN_DT)

    def test_skipped_cycles_resync(self, mgr, model_manager):
        """Training paused (sensor gone, learning off): the next cycle syncs again."""
        mgr.clear("r1")
        mgr.process("r1", current_temp=18.0, **self.COMMON)
        model_manager.sync_temperature.assert_called_once_with("r1", 18.0)

    def test_skipped_training_without_resync_keeps_learning(self, mgr, model_manager):
        """A compressor hold resumes without a resync, as before #478."""
        mgr.clear("r1", resync=False)
        mgr.process("r1", current_temp=18.0, **self.COMMON)
        model_manager.sync_temperature.assert_not_called()
        assert mgr._accumulated_dt["r1"] == pytest.approx(0.5)

    def test_unobservable_mode_resyncs_afterwards(self, mgr, model_manager):
        mgr.process("r1", current_temp=20.0, **{**self.COMMON, "ekf_mode": None})
        mgr.process("r1", current_temp=19.0, **self.COMMON)
        model_manager.sync_temperature.assert_called_once_with("r1", 19.0)

    def test_window_after_gap_tracks_temperature_without_learning_k_window(self, model_manager):
        mgr = EkfTrainingManager(model_manager)
        mgr.process("r1", current_temp=18.0, **{**self.COMMON, "window_open": True})
        assert model_manager.update_window_open.call_args.kwargs["learn_k_window"] is False
        mgr.process("r1", current_temp=17.8, **{**self.COMMON, "window_open": True})
        assert model_manager.update_window_open.call_args.kwargs["learn_k_window"] is True

    def test_window_after_a_pause_without_resync_does_not_learn_k_window(self, mgr, model_manager):
        mgr.clear("r1", resync=False)
        mgr.process("r1", current_temp=18.0, **{**self.COMMON, "window_open": True})
        assert model_manager.update_window_open.call_args.kwargs["learn_k_window"] is False

    def test_window_keeps_the_room_synced(self, mgr, model_manager):
        mgr.process("r1", current_temp=18.0, **{**self.COMMON, "window_open": True})
        mgr.process("r1", current_temp=18.5, **self.COMMON)
        model_manager.sync_temperature.assert_not_called()

    def test_synced_room_keeps_learning(self, mgr, model_manager):
        mgr.process("r1", current_temp=20.0, **self.COMMON)
        model_manager.sync_temperature.assert_not_called()
        assert mgr._accumulated_dt["r1"] == pytest.approx(0.5)


def test_sync_temperature_keeps_the_learned_parameters():
    from custom_components.roommind.control.thermal_model import RoomModelManager, ThermalEKF

    est = ThermalEKF()
    for _ in range(20):
        est.update(21.0, 10.0, "idle", 3.0)
    params = list(est._x[1:])
    mm = RoomModelManager()
    mm._estimators["r1"] = est
    mm.sync_temperature("r1", 18.5)
    assert est._x[0] == 18.5
    assert est._x[1:] == params
    n = est._n_updates
    est.update(18.5, 10.0, "idle", 3.0)
    assert est._n_updates == n + 1


def test_sync_temperature_initializes_a_new_estimator():
    from custom_components.roommind.control.thermal_model import RoomModelManager

    mm = RoomModelManager()
    mm.sync_temperature("new", 19.0)
    est = mm.get_estimator("new")
    assert est._x[0] == 19.0
    assert est._initialized


def test_restart_after_an_outage_keeps_the_learned_heat_loss():
    """Real EKF: a restored model 2 K above the room must not learn that as heat loss (#478)."""
    from custom_components.roommind.control.thermal_model import RoomModelManager

    common = dict(
        T_outdoor=5.0,
        ekf_mode="idle",
        ekf_pf=0.0,
        window_open=False,
        raw_open=False,
        q_residual=0.0,
        shading_factor=1.0,
        q_solar=0.0,
        can_heat=True,
        can_cool=False,
        dt_minutes=0.5,
    )
    alpha = 0.015
    mm = RoomModelManager()
    mgr = EkfTrainingManager(mm)
    temp = 21.0
    for _ in range(6000):
        temp -= alpha * (temp - 5.0) * 0.5 / 60
        if temp < 19.0:
            temp = 21.0
            mgr.clear("r1")
        mgr.process("r1", current_temp=round(temp, 3), **common)
    learned = mm.get_model("r1").U

    restored = RoomModelManager.from_dict(mm.to_dict())
    restored.get_estimator("r1")._x[0] = temp + 2.0
    mgr = EkfTrainingManager(restored)
    for _ in range(60):
        temp -= alpha * (temp - 5.0) * 0.5 / 60
        mgr.process("r1", current_temp=round(temp, 3), **common)
    assert restored.get_model("r1").U == pytest.approx(learned, rel=0.15)


def _power_common(**overrides):
    common = dict(
        T_outdoor=5.0,
        ekf_mode="idle",
        ekf_pf=0.0,
        window_open=False,
        raw_open=False,
        q_residual=0.0,
        shading_factor=1.0,
        q_solar=0.0,
        can_heat=True,
        can_cool=False,
        dt_minutes=1.5,
    )
    common.update(overrides)
    return common


def test_power_is_averaged_over_the_batch(mgr, model_manager):
    """A device switching within a batch counts with its share of the time."""
    mgr.process("room1", current_temp=20.0, q_power=0.4, **_power_common())
    model_manager.update.assert_not_called()
    mgr.process("room1", current_temp=20.1, q_power=0.0, **_power_common())
    assert model_manager.update.call_args.kwargs["q_power"] == pytest.approx(0.2)


def test_power_batch_mean_goes_with_a_mode_change_flush(mgr, model_manager):
    mgr.process("room1", current_temp=20.0, q_power=0.3, **_power_common())
    mgr.process("room1", current_temp=20.1, q_power=0.9, **_power_common(ekf_mode="heating", ekf_pf=1.0))
    # the idle batch is flushed with its own mean, not the new reading
    assert model_manager.update.call_args.kwargs["q_power"] == pytest.approx(0.3)
    mgr.clear("room1")
    assert "room1" not in mgr._accumulated_power
