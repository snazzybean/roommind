"""Tests for the short temperature series the dashboard cards draw."""

from custom_components.roommind.managers.recent_temps import RECENT_STEP_S, RECENT_WINDOW_S, RecentTemps


def test_adds_one_point_per_step_and_drops_old_ones():
    rt = RecentTemps()
    t0 = 1_000_000.0
    rt.add("a", t0, 20.123, 21.0)
    rt.add("a", t0 + 30, 20.2, 21.0)
    rt.add("a", t0 + RECENT_STEP_S, 20.3, None)
    assert rt.get("a") == [[int(t0), 20.12, 21.0], [int(t0 + RECENT_STEP_S), 20.3, None]]

    rt.add("a", t0 + RECENT_WINDOW_S + RECENT_STEP_S, 19.0, 18.0)
    assert [p[0] for p in rt.get("a")] == [int(t0 + RECENT_STEP_S), int(t0 + RECENT_WINDOW_S + RECENT_STEP_S)]


def test_missing_temperature_is_skipped():
    rt = RecentTemps()
    rt.add("a", 1.0, None, 21.0)
    assert rt.get("a") == []
    assert rt.get("unknown") == []


def test_seed_reads_csv_strings_within_the_window():
    rt = RecentTemps()
    now = 2_000_000.0
    rows = [
        {"timestamp": str(now - RECENT_WINDOW_S - 60), "room_temp": "18.0", "heat_target": "17"},
        {"timestamp": str(now - 3600), "room_temp": "19.5", "heat_target": "", "target_temp": "20"},
        {"timestamp": str(now - 3500), "room_temp": "19.6", "heat_target": "21"},
        {"timestamp": str(now - 3000), "room_temp": "", "heat_target": "21"},
        {"timestamp": "broken", "room_temp": "19.0"},
        {"timestamp": str(now - 1800), "room_temp": "19.9", "heat_target": "21"},
    ]
    assert rt.needs_seed("a")
    rt.seed("a", rows, now)
    assert not rt.needs_seed("a")
    assert rt.get("a") == [[int(now - 3600), 19.5, 20.0], [int(now - 1800), 19.9, 21.0]]


def test_seed_keeps_points_recorded_before_it():
    rt = RecentTemps()
    now = 3_000_000.0
    rt.add("a", now, 21.0, 21.0)
    rt.seed(
        "a",
        [{"timestamp": str(now - 600), "room_temp": "20.5"}, {"timestamp": str(now - 100), "room_temp": "20.9"}],
        now,
    )
    assert rt.get("a") == [[int(now - 600), 20.5, None], [int(now), 21.0, 21.0]]


def test_seed_without_rows_keeps_room_empty():
    rt = RecentTemps()
    rt.seed("a", [], 1.0)
    assert rt.get("a") == []
    assert not rt.needs_seed("a")


def test_forget_clears_series_and_seed_flag():
    rt = RecentTemps()
    rt.seed("a", [], 1.0)
    rt.add("a", 1.0, 20.0, 21.0)
    rt.forget("a")
    assert rt.get("a") == []
    assert rt.needs_seed("a")
