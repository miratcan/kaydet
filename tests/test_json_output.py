"""Tests for the consistent --format json envelope."""

from __future__ import annotations

import json

from kaydet.json_output import json_err, json_ok


def test_json_ok_envelope():
    payload = json.loads(json_ok({"tags": [{"name": "work", "count": 2}]}))
    assert payload == {
        "success": True,
        "data": {"tags": [{"name": "work", "count": 2}]},
    }


def test_json_err_envelope():
    payload = json.loads(json_err("not found", code="not_found"))
    assert payload["success"] is False
    assert payload["error"] == "not found"
    assert payload["code"] == "not_found"
