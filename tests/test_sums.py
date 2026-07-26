"""Tests for unit-agnostic --sum aggregation and display."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from kaydet.sums import (
    aggregate_sums,
    format_sum_value,
    format_sums_payload,
    print_sums,
)


def _entry(metadata: dict, numbers: dict):
    return SimpleNamespace(
        metadata=metadata,
        metadata_numbers=numbers,
        day=date(2025, 10, 27),
        entry_id="1",
        tags=(),
        text="",
    )


def test_aggregate_is_unit_agnostic():
    """Suffixes are ignored at parse time; sum uses stored raw numbers only."""
    matches = [
        _entry({"time": "2h"}, {"time": 2.0}),
        _entry({"time": "30m"}, {"time": 30.0}),
        _entry({"cost": "100tl"}, {"cost": 100.0}),
        _entry({"cost": "50"}, {"cost": 50.0}),
    ]
    sums = aggregate_sums(matches)
    # No conversion: 2 + 30, not 150 minutes
    assert sums["time"] == 32
    assert sums["cost"] == 150
    assert format_sum_value(sums["time"]) == "32"
    assert format_sum_value(sums["cost"]) == "150"


def test_format_sums_payload_and_print(capsys):
    matches = [
        _entry({"price": "12.5"}, {"price": 12.5}),
        _entry({"price": "7.5"}, {"price": 7.5}),
        _entry({"km": "3"}, {"km": 3.0}),
    ]
    payload = format_sums_payload(matches)
    assert payload["total_entries"] == 3
    assert payload["sums"]["price"] == 20.0
    assert payload["sums_display"]["price"] == "20"
    assert payload["sums_display"]["km"] == "3"

    print_sums(matches)
    out = capsys.readouterr().out
    assert "3 entries" in out
    assert "20" in out
    assert "km" in out
