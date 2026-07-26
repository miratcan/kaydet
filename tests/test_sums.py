"""Tests for unit-aware --sum aggregation and display."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from kaydet.sums import (
    aggregate_sums,
    format_duration_minutes,
    format_sum_value,
    format_sums_payload,
    parse_duration_minutes,
    print_sums,
)


def test_parse_duration_minutes_units():
    assert parse_duration_minutes("2h") == 120
    assert parse_duration_minutes("3saat") == 180
    assert parse_duration_minutes("30m") == 30
    assert parse_duration_minutes("15dk") == 15
    assert parse_duration_minutes("1.5h") == 90
    # bare number = hours
    assert parse_duration_minutes("2") == 120


def test_format_duration_minutes():
    assert format_duration_minutes(150) == "2h 30m"
    assert format_duration_minutes(120) == "2h"
    assert format_duration_minutes(45) == "45m"
    assert format_duration_minutes(0) == "0m"


def _entry(metadata: dict, numbers: dict):
    return SimpleNamespace(
        metadata=metadata,
        metadata_numbers=numbers,
        day=date(2025, 10, 27),
        entry_id="1",
        tags=(),
        text="",
    )


def test_aggregate_mixes_hours_and_minutes():
    matches = [
        _entry({"time": "2h"}, {"time": 2.0}),
        _entry({"time": "30m"}, {"time": 30.0}),
        _entry({"cost": "100tl"}, {"cost": 100.0}),
        _entry({"cost": "50"}, {"cost": 50.0}),
    ]
    sums = aggregate_sums(matches)
    assert sums["time"] == 150  # minutes
    assert sums["cost"] == 150
    assert format_sum_value("time", sums["time"]) == "2h 30m"
    assert format_sum_value("cost", sums["cost"]) == "150"


def test_format_sums_payload_display(capsys):
    matches = [
        _entry({"time": "1h"}, {"time": 1.0}),
        _entry({"time": "90m"}, {"time": 90.0}),
        _entry({"price": "12.5"}, {"price": 12.5}),
    ]
    payload = format_sums_payload(matches)
    assert payload["total_entries"] == 3
    assert payload["sums"]["time"] == 150
    assert payload["sums_display"]["time"] == "2h 30m"
    assert payload["sums_display"]["price"] == "12.5"

    print_sums(matches)
    out = capsys.readouterr().out
    assert "3 entries" in out
    assert "2h 30m" in out
    assert "12.5" in out
