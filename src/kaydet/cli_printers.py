"""Simple print helpers for stats, tags, and doctor commands."""

from __future__ import annotations

import calendar
from typing import Any

from .json_output import print_json_err, print_json_ok


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
    for week in month_calendar:
        cells = []
        for day in week:
            if day == 0:
                cells.append("      ")
                continue
            count = counts.get(day, 0)
            if count == 0:
                cells.append(f"{day:2d}[  ]")
            elif count < 100:
                cells.append(f"{day:2d}[{count:2d}]")
            else:
                cells.append(f"{day:2d}[**]")
        print(" ".join(cells))

    total_entries = result["total_entries"]
    if total_entries == 0:
        print("\n\U0001f4ad No entries recorded for this month yet")
    else:
        print(f"\nTotal entries this month: {total_entries}")


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
        print("\U0001f3f7\ufe0f No tags recorded yet")
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
