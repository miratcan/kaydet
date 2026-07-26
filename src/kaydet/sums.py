"""Aggregate and format numeric metadata sums for --sum / MCP.

Unit-agnostic grouping: values are split into (number, unit-suffix).
Only identical (key, unit) pairs are summed — no conversion between
units (``1saat`` and ``30dk`` stay separate lines).

Example::

    timespent:1saat + timespent:2saat + timespent:30dk + timespent:1hour
    →
    timespent (dk)    30
    timespent (hour)  1
    timespent (saat)  3

Unit lives in the label only (no ``3saat`` repetition on the value).
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any, Iterable

# Leading number + optional letter suffix (any language's letters).
# Rejects timestamps like 18:51 (colon) and bare non-numeric text.
_AMOUNT_UNIT_RE = re.compile(
    r"^([-+]?\d+(?:\.\d+)?)([^\W\d_]*)$",
    re.UNICODE,
)


def split_amount_unit(raw_value: str) -> tuple[float, str] | None:
    """Split ``2saat`` → (2.0, ``saat``), ``100`` → (100.0, ``""``).

    Suffix is lowercased for stable grouping; no unit semantics applied.
    """
    value = raw_value.strip().lower()
    if not value or ":" in value:
        return None
    match = _AMOUNT_UNIT_RE.match(value)
    if not match:
        return None
    return float(match.group(1)), match.group(2)


def _format_number(value: float) -> str:
    if value == int(value):
        return str(int(value))
    return str(value)


def _group_label(key: str, unit: str) -> str:
    if unit:
        return f"{key} ({unit})"
    return key


def _group_display(total: float, unit: str) -> str:
    """Value column: number only (unit already shown in the label)."""
    return _format_number(total)


def aggregate_sums(
    matches: Iterable[Any],
) -> list[dict[str, Any]]:
    """Sum by (metadata key, unit suffix).

    Returns a sorted list of groups::

        [{"key": "timespent", "unit": "saat", "total": 3,
          "label": "timespent (saat)", "display": "3"}, ...]
    """
    totals: Counter[tuple[str, str]] = Counter()

    for match in matches:
        metadata = getattr(match, "metadata", None) or {}
        for key, raw in metadata.items():
            parsed = split_amount_unit(str(raw))
            if parsed is None:
                continue
            amount, unit = parsed
            totals[(key, unit)] += amount

    groups: list[dict[str, Any]] = []
    for (key, unit), total in sorted(
        totals.items(), key=lambda item: (item[0][0], item[0][1])
    ):
        total_out: float | int = (
            int(total) if total == int(total) else total
        )
        groups.append(
            {
                "key": key,
                "unit": unit,
                "total": total_out,
                "label": _group_label(key, unit),
                "display": _group_display(float(total_out), unit),
            }
        )
    return groups


def format_sums_payload(
    matches: Iterable[Any],
) -> dict[str, Any]:
    """Build structured sum payload for CLI JSON and MCP."""
    match_list = list(matches)
    groups = aggregate_sums(match_list)
    # Flat maps keyed by label for simple consumers
    sums = {g["label"]: g["total"] for g in groups}
    sums_display = {g["label"]: g["display"] for g in groups}
    return {
        "total_entries": len(match_list),
        "groups": groups,
        "sums": sums,
        "sums_display": sums_display,
    }


def _has_split_units(groups: list[dict[str, Any]]) -> bool:
    """True when the same metadata key appears with 2+ unit suffixes."""
    by_key: Counter[str] = Counter()
    for g in groups:
        by_key[g["key"]] += 1
    return any(n > 1 for n in by_key.values())


def print_sums(matches: list) -> None:
    """Print summed numeric metadata for the CLI."""
    payload = format_sums_payload(matches)
    groups = payload["groups"]
    if not groups:
        print("\U0001f4ca No numeric values found to sum")
        return

    n = payload["total_entries"]
    entry_label = "entry" if n == 1 else "entries"
    print(f"\U0001f4ca {n} {entry_label}")

    width = max(len(g["label"]) for g in groups)
    for g in groups:
        print(f"  {g['label']:<{width}}  {g['display']}")

    if _has_split_units(groups):
        print(
            "\U0001f4a1 Same key, different units — not combined."
        )
