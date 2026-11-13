"""Tests for the CSV-based history store."""

from __future__ import annotations

import csv
import os
import time

import pytest

from custom_components.roommind.utils.history_store import DETAIL_FIELDS, HistoryStore


@pytest.fixture
def history_dir(tmp_path):
    return str(tmp_path / "history")


def test_write_and_read(history_dir):
    """Write one record and read it back."""
    store = HistoryStore(history_dir)
    store.record(
        "living_room",
        {
            "room_temp": 21.0,
            "outdoor_temp": 5.0,
            "target_temp": 21.0,
            "mode": "idle",
            "predicted_temp": 21.1,
        },
    )
    rows = store.read_detail("living_room")
    assert len(rows) == 1
    assert rows[0]["room_temp"] == "21.0"


def test_multiple_rooms(history_dir):
    """Each room has separate CSV files."""
    store = HistoryStore(history_dir)
    store.record(
        "room_a",
        {"room_temp": 20.0, "outdoor_temp": 5.0, "target_temp": 21.0, "mode": "heating", "predicted_temp": 20.5},
    )
    store.record(
        "room_b",
        {"room_temp": 25.0, "outdoor_temp": 30.0, "target_temp": 23.0, "mode": "cooling", "predicted_temp": 24.0},
    )
    assert len(store.read_detail("room_a")) == 1
    assert len(store.read_detail("room_b")) == 1


def test_creates_directory(history_dir):
    """Directory is created on first write."""
    store = HistoryStore(history_dir)
    store.record(
        "test_room",
        {"room_temp": 20.0, "outdoor_temp": 5.0, "target_temp": 21.0, "mode": "idle", "predicted_temp": 20.0},
    )
    assert os.path.isdir(history_dir)


def test_read_empty_room(history_dir):
    """Reading nonexistent room returns empty list."""
    store = HistoryStore(history_dir)
    rows = store.read_detail("nonexistent")
    assert rows == []


def test_remove_room(history_dir):
    """remove_room deletes all files for that room."""
    store = HistoryStore(history_dir)
    store.record(
        "room_a", {"room_temp": 20.0, "outdoor_temp": 5.0, "target_temp": 21.0, "mode": "idle", "predicted_temp": 20.0}
    )
    store.remove_room("room_a")
    assert store.read_detail("room_a") == []


def test_multiple_records(history_dir):
    """Multiple records are stored and read back."""
    store = HistoryStore(history_dir)
    base = time.time()
    for i in range(10):
        store.record(
            "room_a",
            {
                "room_temp": 20.0 + i * 0.1,
                "outdoor_temp": 5.0,
                "target_temp": 21.0,
                "mode": "heating",
                "predicted_temp": 20.0 + i * 0.1,
            },
            timestamp=base + i * 60,
        )
    detail_rows = store.read_detail("room_a")
    assert len(detail_rows) == 10


def test_window_open_in_csv(history_dir):
    """window_open field is written and read correctly."""
    store = HistoryStore(history_dir)
    store.record(
        "room_a",
        {
            "room_temp": 20.0,
            "outdoor_temp": 5.0,
            "target_temp": 21.0,
            "mode": "idle",
            "predicted_temp": 20.0,
            "window_open": True,
        },
    )
    store.record(
        "room_a",
        {
            "room_temp": 20.0,
            "outdoor_temp": 5.0,
            "target_temp": 21.0,
            "mode": "idle",
            "predicted_temp": 20.0,
            "window_open": False,
        },
    )
    rows = store.read_detail("room_a")
    assert len(rows) == 2
    assert rows[0]["window_open"] == "True"
    assert rows[1]["window_open"] == "False"


def test_downsample_preserves_window_open(history_dir):
    """_downsample takes first window_open value from each bucket."""
    store = HistoryStore(history_dir)
    rows = [
        {
            "timestamp": "1000",
            "room_temp": "20.0",
            "outdoor_temp": "5.0",
            "target_temp": "21.0",
            "mode": "idle",
            "predicted_temp": "20.0",
            "window_open": "True",
        },
        {
            "timestamp": "1060",
            "room_temp": "20.0",
            "outdoor_temp": "5.0",
            "target_temp": "21.0",
            "mode": "idle",
            "predicted_temp": "20.0",
            "window_open": "True",
        },
        {
            "timestamp": "1500",
            "room_temp": "21.0",
            "outdoor_temp": "5.0",
            "target_temp": "21.0",
            "mode": "heating",
            "predicted_temp": "21.0",
            "window_open": "False",
        },
    ]
    result = store._downsample(rows, bucket_seconds=300)
    # Two buckets: 0-300s (ts 1000, 1060) and 300-600s (ts 1500)
    assert len(result) == 2
    assert result[0]["window_open"] == "True"
    assert result[1]["window_open"] == "False"


def test_rotate_moves_old_to_history(history_dir):
    """Rotation moves old detail rows to history file."""
    store = HistoryStore(history_dir)
    now = time.time()
    # Write rows that are "old" (> 48h ago)
    old_ts = now - 50 * 3600  # 50 hours ago
    for i in range(5):
        store.record(
            "room_a",
            {
                "room_temp": 20.0 + i * 0.1,
                "outdoor_temp": 5.0,
                "target_temp": 21.0,
                "mode": "heating",
                "predicted_temp": 20.0,
            },
            timestamp=old_ts + i * 60,
        )
    # Write some recent rows
    for i in range(3):
        store.record(
            "room_a",
            {
                "room_temp": 21.0,
                "outdoor_temp": 5.0,
                "target_temp": 21.0,
                "mode": "idle",
                "predicted_temp": 21.0,
            },
            timestamp=now + i * 60,
        )

    store.rotate("room_a")

    detail = store.read_detail("room_a")
    history = store.read_history("room_a")
    assert len(detail) == 3  # only recent rows remain
    assert len(history) >= 1  # old rows downsampled to history


# ---------------------------------------------------------------------------
# Timestamp-based filtering
# ---------------------------------------------------------------------------


def test_read_detail_with_start_ts(history_dir):
    """start_ts filters out rows before the given timestamp."""
    store = HistoryStore(history_dir)
    for i in range(5):
        store.record(
            "room_a",
            {
                "room_temp": 20.0,
                "outdoor_temp": 5.0,
                "target_temp": 21.0,
                "mode": "idle",
                "predicted_temp": 20.0,
            },
            timestamp=1000.0 + i * 100,
        )

    rows = store.read_detail("room_a", start_ts=1200.0)
    assert len(rows) == 3  # ts 1200, 1300, 1400


def test_read_detail_with_end_ts(history_dir):
    """end_ts filters out rows after the given timestamp."""
    store = HistoryStore(history_dir)
    for i in range(5):
        store.record(
            "room_a",
            {
                "room_temp": 20.0,
                "outdoor_temp": 5.0,
                "target_temp": 21.0,
                "mode": "idle",
                "predicted_temp": 20.0,
            },
            timestamp=1000.0 + i * 100,
        )

    rows = store.read_detail("room_a", end_ts=1200.0)
    assert len(rows) == 3  # ts 1000, 1100, 1200


def test_read_detail_with_start_and_end_ts(history_dir):
    """Both start_ts and end_ts filter rows to a range."""
    store = HistoryStore(history_dir)
    for i in range(5):
        store.record(
            "room_a",
            {
                "room_temp": 20.0,
                "outdoor_temp": 5.0,
                "target_temp": 21.0,
                "mode": "idle",
                "predicted_temp": 20.0,
            },
            timestamp=1000.0 + i * 100,
        )

    rows = store.read_detail("room_a", start_ts=1100.0, end_ts=1300.0)
    assert len(rows) == 3  # ts 1100, 1200, 1300


def test_read_detail_start_ts_overrides_max_age(history_dir):
    """start_ts takes precedence over max_age."""
    store = HistoryStore(history_dir)
    # Write rows: 2 old, 3 recent
    for i in range(5):
        store.record(
            "room_a",
            {
                "room_temp": 20.0,
                "outdoor_temp": 5.0,
                "target_temp": 21.0,
                "mode": "idle",
                "predicted_temp": 20.0,
            },
            timestamp=1000.0 + i * 100,
        )

    # start_ts=1200 should override max_age and return rows from 1200+
    rows = store.read_detail("room_a", start_ts=1200.0, max_age=99999999)
    assert len(rows) == 3


# ---------------------------------------------------------------------------
# Corrupt timestamp handling
# ---------------------------------------------------------------------------


def test_read_detail_skips_corrupt_timestamps(history_dir):
    """Rows with non-numeric timestamps are silently skipped."""
    store = HistoryStore(history_dir)
    store.record(
        "room_a",
        {"room_temp": 20.0, "outdoor_temp": 5.0, "target_temp": 21.0, "mode": "idle", "predicted_temp": 20.0},
        timestamp=1000.0,
    )

    # Manually write a corrupt row
    path = store._detail_path("room_a")
    with open(path, "a") as f:
        f.write("bad_ts,20.0,5.0,21.0,idle,20.0,,,,,\n")

    store.record(
        "room_a",
        {"room_temp": 21.0, "outdoor_temp": 5.0, "target_temp": 21.0, "mode": "idle", "predicted_temp": 21.0},
        timestamp=2000.0,
    )

    # With filtering (max_age triggers timestamp parsing)
    rows = store.read_detail("room_a", start_ts=500.0)
    # Should have 2 valid rows, corrupt one skipped
    assert len(rows) == 2


def test_rotate_skips_corrupt_timestamps(history_dir):
    """Rotate silently skips rows with corrupt timestamps."""
    store = HistoryStore(history_dir)
    now = time.time()
    store.record(
        "room_a",
        {"room_temp": 20.0, "outdoor_temp": 5.0, "target_temp": 21.0, "mode": "idle", "predicted_temp": 20.0},
        timestamp=now,
    )

    # Write a corrupt row
    path = store._detail_path("room_a")
    with open(path, "a") as f:
        f.write("not_a_number,20.0,5.0,21.0,idle,20.0,,,,,\n")

    # Should not raise
    store.rotate("room_a")
    rows = store.read_detail("room_a")
    assert len(rows) == 1  # only the valid row survives
    assert rows[0]["room_temp"] == "20.0"


# ---------------------------------------------------------------------------
# Downsample edge cases
# ---------------------------------------------------------------------------


def test_downsample_empty(history_dir):
    """Empty input returns empty output."""
    store = HistoryStore(history_dir)
    assert store._downsample([], bucket_seconds=300) == []


def test_downsample_non_numeric_values(history_dir):
    """Non-numeric field values produce empty string in output."""
    store = HistoryStore(history_dir)
    rows = [
        {
            "timestamp": "1000",
            "room_temp": "abc",
            "outdoor_temp": "5.0",
            "target_temp": "21.0",
            "mode": "idle",
            "predicted_temp": "20.0",
            "window_open": "",
            "heating_power": "",
            "solar_irradiance": "",
        },
    ]
    result = store._downsample(rows, bucket_seconds=300)
    assert len(result) == 1
    assert result[0]["room_temp"] == ""  # non-numeric → empty
    assert result[0]["outdoor_temp"] == 5.0


# ---------------------------------------------------------------------------
# _safe_ts edge cases
# ---------------------------------------------------------------------------


def test_safe_ts_valid():
    """Valid timestamp returns float."""
    assert HistoryStore._safe_ts({"timestamp": "1234.5"}) == 1234.5


def test_safe_ts_missing_key():
    """Missing timestamp key returns 0.0."""
    assert HistoryStore._safe_ts({}) == 0.0


def test_safe_ts_non_numeric():
    """Non-numeric timestamp returns 0.0."""
    assert HistoryStore._safe_ts({"timestamp": "abc"}) == 0.0


def test_safe_ts_none_value():
    """None timestamp returns 0.0."""
    assert HistoryStore._safe_ts({"timestamp": None}) == 0.0


def test_rotate_trims_old_history(history_dir):
    """rotate() should trim history records older than HISTORY_MAX_AGE."""
    import time as _time

    from custom_components.roommind.utils.history_store import HISTORY_MAX_AGE

    store = HistoryStore(history_dir)
    # Write one very old record directly into history
    old_ts = _time.time() - HISTORY_MAX_AGE - 1000
    store._append_history("room1", [{"timestamp": str(old_ts), "room_temp": "20.0"}])
    assert len(store.read_history("room1")) == 1
    store.rotate("room1")
    assert len(store.read_history("room1")) == 0


# ---------------------------------------------------------------------------
# device_setpoint field
# ---------------------------------------------------------------------------


def test_device_setpoint_in_csv(history_dir):
    """device_setpoint is written to CSV and read back correctly."""
    store = HistoryStore(history_dir)
    store.record(
        "room_a",
        {
            "room_temp": 20.0,
            "outdoor_temp": 5.0,
            "target_temp": 21.0,
            "mode": "heating",
            "predicted_temp": 20.5,
            "device_setpoint": 24.5,
        },
    )
    rows = store.read_detail("room_a")
    assert len(rows) == 1
    assert rows[0]["device_setpoint"] == "24.5"


def test_device_setpoint_missing_defaults_empty(history_dir):
    """Missing device_setpoint defaults to empty string in CSV."""
    store = HistoryStore(history_dir)
    store.record(
        "room_a",
        {
            "room_temp": 20.0,
            "outdoor_temp": 5.0,
            "target_temp": 21.0,
            "mode": "idle",
            "predicted_temp": 20.0,
        },
    )
    rows = store.read_detail("room_a")
    assert len(rows) == 1
    assert rows[0]["device_setpoint"] == ""


def test_migrate_header_rewrites_old_format(history_dir):
    """CSV with outdated header is rewritten with current DETAIL_FIELDS."""
    from custom_components.roommind.utils.history_store import DETAIL_FIELDS

    store = HistoryStore(history_dir)
    os.makedirs(history_dir, exist_ok=True)
    path = store._detail_path("room_a")

    old_fields = ["timestamp", "room_temp", "outdoor_temp", "target_temp", "mode"]
    import csv

    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=old_fields)
        writer.writeheader()
        writer.writerow(
            {"timestamp": "1000", "room_temp": "20.0", "outdoor_temp": "5.0", "target_temp": "21.0", "mode": "heating"}
        )

    store.record(
        "room_a",
        {"room_temp": 22.0, "outdoor_temp": 6.0, "target_temp": 21.0, "mode": "idle", "predicted_temp": 21.5},
        timestamp=2000.0,
    )

    rows = store.read_detail("room_a")
    assert len(rows) == 2
    assert rows[0]["room_temp"] == "20.0"
    assert rows[0].get("predicted_temp") == ""
    assert rows[1]["room_temp"] == "22.0"

    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == DETAIL_FIELDS


def test_migrate_header_noop_when_current(history_dir):
    """CSV with current header is not rewritten."""
    store = HistoryStore(history_dir)
    store.record(
        "room_a",
        {"room_temp": 20.0, "outdoor_temp": 5.0, "target_temp": 21.0, "mode": "idle", "predicted_temp": 20.0},
        timestamp=1000.0,
    )
    store.record(
        "room_a",
        {"room_temp": 21.0, "outdoor_temp": 5.0, "target_temp": 21.0, "mode": "idle", "predicted_temp": 21.0},
        timestamp=2000.0,
    )
    rows = store.read_detail("room_a")
    assert len(rows) == 2


def test_migrate_header_handles_corrupt_file(history_dir):
    """Migration silently handles corrupt CSV files."""
    store = HistoryStore(history_dir)
    os.makedirs(history_dir, exist_ok=True)
    path = store._detail_path("room_a")

    with open(path, "w") as f:
        f.write("\x00\x00\x00invalid csv content\n")

    store.record(
        "room_a",
        {"room_temp": 20.0, "outdoor_temp": 5.0, "target_temp": 21.0, "mode": "idle", "predicted_temp": 20.0},
        timestamp=1000.0,
    )
    rows = store.read_detail("room_a")
    assert len(rows) >= 1


def test_read_detail_with_max_age(history_dir):
    """max_age filters out rows older than the specified seconds."""
    store = HistoryStore(history_dir)
    now = time.time()
    store.record(
        "room_a",
        {"room_temp": 20.0, "outdoor_temp": 5.0, "target_temp": 21.0, "mode": "idle", "predicted_temp": 20.0},
        timestamp=now - 7200,
    )
    store.record(
        "room_a",
        {"room_temp": 21.0, "outdoor_temp": 5.0, "target_temp": 21.0, "mode": "idle", "predicted_temp": 21.0},
        timestamp=now - 1800,
    )
    store.record(
        "room_a",
        {"room_temp": 22.0, "outdoor_temp": 5.0, "target_temp": 21.0, "mode": "idle", "predicted_temp": 22.0},
        timestamp=now - 60,
    )

    rows = store.read_detail("room_a", max_age=3600)
    assert len(rows) == 2
    assert rows[0]["room_temp"] == "21.0"
    assert rows[1]["room_temp"] == "22.0"


def test_downsample_takes_first_device_setpoint(history_dir):
    """_downsample takes first device_setpoint value from each bucket (not averaged)."""
    store = HistoryStore(history_dir)
    rows = [
        {
            "timestamp": "1000",
            "room_temp": "20.0",
            "outdoor_temp": "5.0",
            "target_temp": "21.0",
            "mode": "heating",
            "predicted_temp": "20.0",
            "window_open": "",
            "heating_power": "80",
            "solar_irradiance": "",
            "blind_position": "",
            "device_setpoint": "24.0",
        },
        {
            "timestamp": "1060",
            "room_temp": "20.0",
            "outdoor_temp": "5.0",
            "target_temp": "21.0",
            "mode": "heating",
            "predicted_temp": "20.0",
            "window_open": "",
            "heating_power": "80",
            "solar_irradiance": "",
            "blind_position": "",
            "device_setpoint": "26.0",
        },
    ]
    result = store._downsample(rows, bucket_seconds=300)
    assert len(result) == 1
    assert result[0]["device_setpoint"] == "24.0"


def test_rotation_with_a_history_file_from_an_older_release(history_dir):
    """New columns must not break the history file an update finds on disk."""
    store = HistoryStore(history_dir)
    old_fields = [f for f in DETAIL_FIELDS if f not in ("humidity", "heat_target", "cool_target")]
    path = os.path.join(history_dir, "room_history.csv")
    os.makedirs(history_dir, exist_ok=True)
    now = time.time()
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=old_fields)
        writer.writeheader()
        writer.writerow({"timestamp": now - 91 * 86400, "room_temp": 20.0, "mode": "idle"})
        writer.writerow({"timestamp": now - 30 * 86400, "room_temp": 21.0, "mode": "idle"})

    store.record("room", {"room_temp": 22.0, "mode": "idle", "humidity": 48.5, "heat_target": 21.0}, now - 3 * 86400)
    store.rotate("room")

    rows = store.read_history("room")
    assert [float(r["room_temp"]) for r in rows] == [21.0, 22.0]
    assert float(rows[-1]["humidity"]) == 48.5
    assert float(rows[-1]["heat_target"]) == 21.0
    assert rows[-1]["cool_target"] == ""


def test_target_reason_and_mold_boost_are_recorded_and_downsampled(history_dir):
    store = HistoryStore(history_dir)
    store.record("room_a", {"room_temp": 20.0, "mode": "idle", "target_reason": "override", "mold_boost": 2.0}, 1000)
    store.record("room_a", {"room_temp": 20.0, "mode": "idle", "target_reason": "", "mold_boost": 0.0}, 1060)
    rows = store.read_detail("room_a")
    assert rows[0]["target_reason"] == "override"
    assert rows[0]["mold_boost"] == "2.0"
    bucket = store._downsample(rows, bucket_seconds=300)[0]
    assert bucket["target_reason"] == "override"
    assert bucket["mold_boost"] == 1.0


def test_price_columns_are_recorded_and_downsampled(history_dir):
    store = HistoryStore(history_dir)
    store.record("room_a", {"mode": "idle", "price": 30.0, "price_level": "expensive", "price_shift": -1.0}, 1000)
    store.record("room_a", {"mode": "idle", "price": 20.0, "price_level": "normal", "price_shift": 0.0}, 1060)
    rows = store.read_detail("room_a")
    assert rows[0]["price_level"] == "expensive"
    bucket = store._downsample(rows, bucket_seconds=300)[0]
    assert bucket["price"] == 25.0
    assert bucket["price_level"] == "expensive"
    assert bucket["price_shift"] == -0.5


def test_co2_column_is_recorded_and_downsampled(history_dir):
    """Room CO2 for the analytics panel (#267); a room without sensor writes an empty cell."""
    store = HistoryStore(history_dir)
    store.record("room_a", {"mode": "idle", "co2": 900.0}, 1000)
    store.record("room_a", {"mode": "idle", "co2": 1100.0}, 1060)
    store.record("room_b", {"mode": "idle", "co2": None}, 1000)
    assert store._downsample(store.read_detail("room_a"), bucket_seconds=300)[0]["co2"] == 1000.0
    assert store.read_detail("room_b")[0]["co2"] == ""


def test_record_marks_the_rows_where_a_run_starts(history_dir):
    store = HistoryStore(history_dir)
    for i, mode in enumerate(["heating", "heating", "idle", "heating", "cooling", "cooling"]):
        store.record("room_a", {"mode": mode}, 1000 + i * 180)
    rows = store.read_detail("room_a")
    # The first row has nothing to compare with, like the transitions on the analytics page
    assert [r["heat_starts"] for r in rows] == ["0", "0", "0", "1", "0", "0"]
    assert [r["cool_starts"] for r in rows] == ["0", "0", "0", "0", "1", "0"]


def test_record_after_a_restart_compares_with_the_last_row_on_disk(history_dir):
    HistoryStore(history_dir).record("room_a", {"mode": "idle"}, 1000)
    restarted = HistoryStore(history_dir)
    restarted.record("room_a", {"mode": "heating"}, 1180)
    assert restarted.read_detail("room_a")[-1]["heat_starts"] == "1"


def test_remove_room_forgets_the_last_mode(history_dir):
    store = HistoryStore(history_dir)
    store.record("room_a", {"mode": "idle"}, 1000)
    store.remove_room("room_a")
    store.record("room_a", {"mode": "heating"}, 1180)
    assert store.read_detail("room_a")[-1]["heat_starts"] == "0"


def test_downsample_sums_the_starts_a_bucket_keeps_only_the_first_mode_of(history_dir):
    store = HistoryStore(history_dir)
    # Two short runs inside 5-min buckets that start idle: the bucket mode hides both
    for i, mode in enumerate(["idle", "heating", "idle", "idle", "cooling", "idle"]):
        store.record("room_a", {"mode": mode}, 600 + i * 100)
    buckets = store._downsample(store.read_detail("room_a"), bucket_seconds=300)
    assert [b["mode"] for b in buckets] == ["idle", "idle"]
    assert [(b["heat_starts"], b["cool_starts"]) for b in buckets] == [(1, 0), (0, 1)]


def test_downsample_keeps_the_extremes_of_the_room_temperature(history_dir):
    store = HistoryStore(history_dir)
    # A short run peaks inside the bucket, its mean hides the peak
    for i, temp in enumerate([21.0, 21.8, 21.3, 20.6, 20.9]):
        store.record("room_a", {"mode": "idle", "room_temp": temp}, 600 + i * 60)
    rows = store.read_detail("room_a")
    assert rows[0]["room_temp_max"] == ""
    (bucket,) = store._downsample(rows, bucket_seconds=300)
    assert bucket["room_temp"] == 21.12
    assert (bucket["room_temp_max"], bucket["room_temp_min"]) == (21.8, 20.6)


def test_downsample_without_room_temperature_has_no_extremes(history_dir):
    store = HistoryStore(history_dir)
    (bucket,) = store._downsample([{"timestamp": "600", "mode": "idle", "room_temp": ""}], bucket_seconds=300)
    assert (bucket["room_temp_max"], bucket["room_temp_min"]) == ("", "")


def test_downsample_counts_rows_from_before_the_columns_against_the_row_before(history_dir):
    store = HistoryStore(history_dir)
    rows = [
        {"timestamp": str(600 + i * 100), "mode": mode, "heat_starts": "", "cool_starts": ""}
        for i, mode in enumerate(["heating", "idle", "heating", "idle", "cooling"])
    ]
    rows.append({"timestamp": "1100", "mode": "heating", "heat_starts": "1", "cool_starts": "0"})
    buckets = store._downsample(rows, bucket_seconds=300)
    # The first row has no row before it in the batch: no start
    assert [(b["heat_starts"], b["cool_starts"]) for b in buckets] == [(1, 0), (1, 1)]


def test_rotate_keeps_the_starts_in_an_old_history_file(history_dir):
    store = HistoryStore(history_dir)
    os.makedirs(history_dir, exist_ok=True)
    old_fields = DETAIL_FIELDS[: DETAIL_FIELDS.index("heat_starts")]
    now = time.time()
    with open(os.path.join(history_dir, "room_a_history.csv"), "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=old_fields)
        writer.writeheader()
        writer.writerow({"timestamp": now - 5 * 86400, "mode": "heating"})
    base = (now - 3 * 86400) // 300 * 300
    for i, mode in enumerate(["idle", "heating", "idle", "heating"]):
        store.record("room_a", {"mode": mode}, base + i * 100)
    store.rotate("room_a")
    rows = store.read_history("room_a")
    assert rows[0]["heat_starts"] == ""
    assert sum(int(r["heat_starts"]) for r in rows[1:]) == 2
