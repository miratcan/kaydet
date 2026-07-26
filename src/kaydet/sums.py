"""Aggregate and format numeric metadata sums for --sum / MCP.

Unit-agnostic: only the leading number is summed (``2h`` and ``30m`` both
contribute their raw numbers — 2 and 30). No language-specific suffix
conversion; callers own meaning of units.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Iterable, Mapping


def aggregate_sums(matches: Iterable[Any]) -> dict[str, float]:
    """Sum ``metadata_numbers`` across entries (raw stored floats)."""
    totals: Counter[str] = Counter()
    for match in matches:
        numbers = getattr(match, "metadata_numbers", None) or {}
        for key, value in numbers.items():
            totals[key] += value

    return {
        key: int(value) if value == int(value) else value
        for key, value in sorted(totals.items())
    }


def format_sum_value(value: float) -> str:
    """Human-readable number (no unit conversion)."""
    if value == int(value):
        return str(int(value))
    return str(value)


def format_sums_payload(
    matches: Iterable[Any],
) -> dict[str, Any]:
    """Build structured sum payload (raw + display strings)."""
    match_list = list(matches)
    sums = aggregate_sums(match_list)
    display = {
        key: format_sum_value(float(value)) for key, value in sums.items()
    }
    return {
        "total_entries": len(match_list),
        "sums": sums,
        "sums_display": display,
    }


def print_sums(matches: list) -> None:
    """Print summed numeric metadata for the CLI (aligned columns)."""
    payload = format_sums_payload(matches)
    if not payload["sums"]:
        print("\U0001f50d No numeric values found to sum")
        return

    n = payload["total_entries"]
    entry_label = "entry" if n == 1 else "entries"
    print(f"\U0001f4ca {n} {entry_label}")

    sums: Mapping[str, float] = payload["sums"]
    display: Mapping[str, str] = payload["sums_display"]
    width = max(len(key) for key in sums)
    for key in sums:
        print(f"  {key:<{width}}  {display[key]}")
