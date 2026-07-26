"""Simple print helpers for stats, tags, and doctor commands."""

from __future__ import annotations

import calendar
from typing import Any

from .json_output import print_json_err, print_json_ok

# GitHub-style contribution intensity (empty → heavy)
_HEAT = ("·", "░", "▒", "▓", "█")
_WEEKDAYS = ("Mo", "Tu", "We", "Th", "Fr", "Sa", "Su")


def _heat_glyph(count: int, month_max: int) -> str:
    """Map a day's entry count to a contribution-grid level."""
    if count <= 0:
        return _HEAT[0]
    if month_max <= 1:
        return _HEAT[1]
    ratio = count / month_max
    if ratio <= 0.25:
        return _HEAT[1]
    if ratio <= 0.50:
        return _HEAT[2]
    if ratio <= 0.75:
        return _HEAT[3]
    return _HEAT[4]


def _print_contribution_grid(
    year: int, month: int, counts: dict[int, int]
) -> None:
    """Print a GitHub-like weekday × week heat map for one month."""
    cal = calendar.Calendar(firstweekday=calendar.MONDAY)
    weeks = cal.monthdayscalendar(year, month)
    month_max = max(counts.values()) if counts else 0

    # One row per weekday (GitHub contribution graph orientation)
    for wd, label in enumerate(_WEEKDAYS):
        cells: list[str] = []
        for week in weeks:
            day = week[wd]
            if day == 0:
                cells.append(" ")
            else:
                cells.append(_heat_glyph(counts.get(day, 0), month_max))
        print(f"{label}  {' '.join(cells)}")

    print()
    print(f"  {' '.join(_HEAT)}  less → more")


def print_stats(result: dict[str, Any], output_format: str) -> None:
    """Print monthly writing activity (motivation grid, not a ledger)."""
    if not result.get("success"):
        error = result.get("error", "Error")
        if output_format == "json":
            print_json_err(error)
        else:
            print(error)
        return

    if output_format == "json":
        print_json_ok(
            {
                "year": result["year"],
                "month": result["month"],
                "month_name": result.get("month_name"),
                "days": result["days"],
                "total_entries": result["total_entries"],
            }
        )
        return

    year = result["year"]
    month = result["month"]
    raw_days = result["days"] or {}
    counts = {int(k): int(v) for k, v in raw_days.items()}

    days_in_month = calendar.monthrange(year, month)[1]
    active_days = sum(
        1 for d in range(1, days_in_month + 1) if counts.get(d, 0) > 0
    )

    print(result["month_name"])
    print()
    _print_contribution_grid(year, month, counts)
    print()

    if active_days == 0:
        print("\U0001f4ca No writing yet this month — one line is enough")
    elif active_days == 1:
        print("\U0001f4ca 1 day with writing this month")
    else:
        print(
            f"\U0001f4ca {active_days} of {days_in_month} days "
            f"with writing this month"
        )


def print_tags(result: dict[str, Any], output_format: str) -> None:
    """Print tag list with counts."""
    if not result.get("success"):
        if output_format == "json":
            print_json_err(result.get("error", "Failed to list tags"))
        return
    rows = result.get("tags", [])
    if output_format == "json":
        print_json_ok({"tags": rows})
        return

    if not rows:
        print("\U0001f4ca No tags recorded yet")
        return

    for t in rows:
        name, count = t["name"], t["count"]
        label = f"#{name}"
        suffix = "entry" if count == 1 else "entries"
        print(f"{label:<20} {count} {suffix}")


def print_doctor(
    result: dict[str, Any], output_format: str = "text"
) -> None:
    """Print doctor rebuild results."""
    if not result.get("success"):
        if output_format == "json":
            print_json_err(result.get("error", "Doctor failed"))
        return

    if output_format == "json":
        print_json_ok(
            {
                "total_entries": result.get("total_entries", 0),
                "normalized_files": result.get("normalized_files", []),
                "tag_stats": result.get("tag_stats", []),
                "messages": result.get("messages", []),
            }
        )
        return

    for msg in result.get("messages", []):
        print(msg)
    total_entries = result.get("total_entries", 0)
    entry_label = "entry" if total_entries == 1 else "entries"
    print(f"Rebuilt search index for {total_entries} {entry_label}.")

    tag_stats = result.get("tag_stats", [])
    if tag_stats:
        tag_list = ", ".join(f"#{t['tag']}: {t['count']}" for t in tag_stats)
        print(f"Tags: {tag_list}")
