"""Tests for unit-grouped --sum (no cross-unit conversion)."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from kaydet.sums import (
    aggregate_sums,
    format_sums_payload,
    print_sums,
    split_amount_unit,
)


def _entry(metadata: dict):
    return SimpleNamespace(
        metadata=metadata,
        metadata_numbers={},
        day=date(2025, 10, 27),
        entry_id="1",
        tags=(),
        text="",
    )


def test_split_amount_unit():
    assert split_amount_unit("1saat") == (1.0, "saat")
    assert split_amount_unit("30dk") == (30.0, "dk")
    assert split_amount_unit("1hour") == (1.0, "hour")
    assert split_amount_unit("100") == (100.0, "")
    assert split_amount_unit("18:51") is None


def test_aggregate_groups_by_unit_no_conversion():
    """Same key, different suffixes → separate sum lines."""
    matches = [
        _entry({"timespent": "1saat"}),
        _entry({"timespent": "2saat"}),
        _entry({"timespent": "30dk"}),
        _entry({"timespent": "1hour"}),
    ]
    groups = {g["label"]: g for g in aggregate_sums(matches)}
    assert groups["timespent (saat)"]["total"] == 3
    assert groups["timespent (saat)"]["display"] == "3saat"
    assert groups["timespent (dk)"]["total"] == 30
    assert groups["timespent (dk)"]["display"] == "30dk"
    assert groups["timespent (hour)"]["total"] == 1
    assert groups["timespent (hour)"]["display"] == "1hour"
    assert len(groups) == 3


def test_bare_numbers_group_without_unit():
    matches = [
        _entry({"cost": "100"}),
        _entry({"cost": "50tl"}),
        _entry({"cost": "25tl"}),
    ]
    groups = {g["label"]: g for g in aggregate_sums(matches)}
    assert groups["cost"]["display"] == "100"
    assert groups["cost (tl)"]["display"] == "75tl"


def test_print_sums_worklog_example(capsys):
    matches = [
        _entry({"timespent": "1saat"}),
        _entry({"timespent": "2saat"}),
        _entry({"timespent": "30dk"}),
        _entry({"timespent": "1hour"}),
    ]
    print_sums(matches)
    out = capsys.readouterr().out
    assert "4 entries" in out
    assert "timespent (saat)" in out and "3saat" in out
    assert "timespent (dk)" in out and "30dk" in out
    assert "timespent (hour)" in out and "1hour" in out


def test_format_sums_payload_shape():
    matches = [_entry({"n": "1km"}), _entry({"n": "2km"})]
    payload = format_sums_payload(matches)
    assert payload["total_entries"] == 2
    assert payload["sums"]["n (km)"] == 3
    assert payload["sums_display"]["n (km)"] == "3km"
    assert payload["groups"][0]["unit"] == "km"
