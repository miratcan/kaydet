"""Aggregate and format numeric metadata sums for --sum / MCP."""

from __future__ import annotations

import re
from collections import Counter
from typing import Any, Iterable, Mapping

# Keys treated as durations (minutes under the hood for summing).
DURATION_KEYS = frozenset(
    {
        "time",
        "duration",
        "saat",
        "sure",
        "süre",
        "mins",
        "minutes",
        "hours",
    }
)

# Suffix → minutes multiplier
_DURATION_SUFFIXES: dict[str, float] = {
    "h": 60.0,
    "hr": 60.0,
    "hrs": 60.0,
    "hour": 60.0,
    "hours": 60.0,
    "saat": 60.0,
    "m": 1.0,
    "min": 1.0,
    "mins": 1.0,
    "minute": 1.0,
    "minutes": 1.0,
    "dk": 1.0,
}

_DURATION_RE = re.compile(
    r"^([-+]?\d+(?:\.\d+)?)([a-zA-ZğüşıöçĞÜŞİÖÇ]*)$"
)


def parse_duration_minutes(raw_value: str) -> float | None:
    """Parse a duration string into minutes.

    ``2h`` / ``2saat`` → 120, ``30m`` / ``30dk`` → 30.
    Bare numbers on duration keys are treated as hours (``2`` → 120).
    """
    value = raw_value.strip().lower()
    if not value:
        return None
    match = _DURATION_RE.match(value)
    if not match:
        return None
    amount = float(match.group(1))
    suffix = match.group(2)
    if not suffix:
        # Bare number → hours (historical diary convention)
        return amount * 60.0
    mult = _DURATION_SUFFIXES.get(suffix)
    if mult is None:
        return None
    return amount * mult


def format_duration_minutes(minutes: float) -> str:
    """Render minutes as ``3h 30m``, ``2h``, or ``45m``."""
    total = int(round(minutes))
    if total < 0:
        sign = "-"
        total = abs(total)
    else:
        sign = ""
    hours, mins = divmod(total, 60)
    if hours and mins:
        return f"{sign}{hours}h {mins}m"
    if hours:
        return f"{sign}{hours}h"
    return f"{sign}{mins}m"


def is_duration_key(key: str) -> bool:
    return key.lower() in DURATION_KEYS


def aggregate_sums(matches: Iterable[Any]) -> dict[str, float]:
    """Sum numeric metadata across entries.

    Duration keys (``time``, ``duration``, …) are summed in **minutes**
    using unit-aware parsing of the original metadata strings so
    ``time:2h`` + ``time:30m`` → 150 minutes.
    Other keys use ``metadata_numbers`` (raw stored floats).
    """
    totals: Counter[str] = Counter()
    duration_totals: Counter[str] = Counter()

    for match in matches:
        metadata = getattr(match, "metadata", None) or {}
        numbers = getattr(match, "metadata_numbers", None) or {}

        for key, raw in metadata.items():
            if is_duration_key(key):
                mins = parse_duration_minutes(str(raw))
                if mins is not None:
                    duration_totals[key] += mins
                continue
            if key in numbers:
                totals[key] += numbers[key]

        # Numeric keys not already covered via metadata strings
        for key, value in numbers.items():
            if is_duration_key(key):
                continue
            if key not in metadata:
                totals[key] += value

    result = {
        key: int(value) if value == int(value) else value
        for key, value in sorted(totals.items())
    }
    for key, value in sorted(duration_totals.items()):
        result[key] = int(value) if value == int(value) else value
    return result


def format_sum_value(key: str, value: float) -> str:
    """Human-readable value for a sum line."""
    if is_duration_key(key):
        return format_duration_minutes(float(value))
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
        key: format_sum_value(key, float(value))
        for key, value in sums.items()
    }
    return {
        "total_entries": len(match_list),
        "sums": sums,
        "sums_display": display,
    }


def print_sums(matches: list) -> None:
    """Print summed numeric metadata for the CLI."""
    payload = format_sums_payload(matches)
    if not payload["sums"]:
        print("\U0001f50d No numeric values found to sum")
        return

    n = payload["total_entries"]
    entry_label = "entry" if n == 1 else "entries"
    print(f"\U0001f4ca {n} {entry_label}")

    sums: Mapping[str, float] = payload["sums"]
    display: Mapping[str, str] = payload["sums_display"]
    width = max(len(key) for key in sums) if sums else 0
    for key in sums:
        print(f"  {key:<{width}}  {display[key]}")
