"""Simple print helpers for stats, tags, and doctor commands."""

from __future__ import annotations

import calendar
from typing import Any

from .json_output import print_json_err, print_json_ok

# Calendar cell width: keep week rows aligned
#   empty  → "dd  ·  "  (7)
#   count  → "dd[nn] "  (7)
#   100+   → "dd[99+]"  (7)
_CELL_WIDTH = 7


def _format_day_cell(day: int, count: int) -> str:
    """Format one calendar day cell (fixed width)."""
    if count == 0:
        # Quiet empty day: no empty brackets
        return f"{day:2d}  ·  "
    if count < 100:
        return f"{day:2d}[{count:2d}] "
    # 100+ — readable marker (not opaque **)
    return f"{day:2d}[99+]"


def print_stats(result: dict[str, Any], output_format: str) -> None:
    """Print monthly calendar stats."""
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

    print(result["month_name"])
    print("Mo Tu We Th Fr Sa Su")
    month_calendar = calendar.Calendar().monthdayscalendar(
        result["year"], result["month"]
    )
    counts = result["days"]
    saw_capped = False
    for week in month_calendar:
        cells = []
        for day in week:
            if day == 0:
                cells.append(" " * _CELL_WIDTH)
                continue
            count = counts.get(day, 0)
            if count >= 100:
                saw_capped = True
            cells.append(_format_day_cell(day, count))
        print(" ".join(cells))

    total_entries = result["total_entries"]
    if total_entries == 0:
        print("\n\U0001f4ca No entries recorded for this month yet")
    else:
        print(f"\n\U0001f4ca Total entries this month: {total_entries}")
        if saw_capped:
            print("   99+ = 100 or more entries that day")


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
