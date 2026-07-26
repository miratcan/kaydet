"""Consistent JSON envelope for ``--format json`` CLI output.

Success::

    {"success": true, "data": { ... }}

Error::

    {"success": false, "error": "human-readable message"}
"""

from __future__ import annotations

import json
from typing import Any


def json_ok(data: Any) -> str:
    """Serialize a successful response envelope."""
    return json.dumps(
        {"success": True, "data": data},
        indent=2,
        ensure_ascii=False,
        default=str,
    )


def json_err(error: str, **extra: Any) -> str:
    """Serialize a failed response envelope."""
    payload: dict[str, Any] = {"success": False, "error": error}
    if extra:
        payload.update(extra)
    return json.dumps(
        payload, indent=2, ensure_ascii=False, default=str
    )


def print_json_ok(data: Any) -> None:
    print(json_ok(data))


def print_json_err(error: str, **extra: Any) -> None:
    print(json_err(error, **extra))
