"""Stats command."""

import calendar
import json
from collections import defaultdict
from configparser import SectionProxy
from datetime import datetime
from pathlib import Path

from ..parsers import count_entries, resolve_entry_date
from ..utils import DEFAULT_SETTINGS


def stats_command(
    log_dir: Path,
    config: SectionProxy,
    now: datetime,
    output_format: str = "text",
):
    """Render a calendar for the current month with entry counts per day."""
    if not log_dir.exists():
        if output_format == "json":
            print(json.dumps({"error": "No diary entries found yet."}))
        else:
            print("No diary entries found yet.")
        return

    year = now.year
    month = now.month

    counts = collect_month_counts(log_dir, config, year, month)

    if output_format == "json":
        result = {
            "year": year,
            "month": month,
            "month_name": now.strftime("%B %Y"),
            "days": counts,
            "total_entries": sum(counts.values()),
        }
        print(json.dumps(result, indent=2))
    else:
        title = now.strftime("%B %Y")
        print(title)
        print("Mo Tu We Th Fr Sa Su")

        month_calendar = calendar.Calendar().monthdayscalendar(year, month)
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

        total_entries = sum(counts.values())
        if total_entries == 0:
            print("\nNo entries recorded for this month yet.")
        else:
            print(f"\nTotal entries this month: {total_entries}")


def collect_month_counts(
    log_dir: Path, config: SectionProxy, year: int, month: int
):
    """Return a mapping of day number to entry count for the given month."""
    counts = defaultdict(int)
    day_file_pattern = config.get(
        "DAY_FILE_PATTERN", DEFAULT_SETTINGS["DAY_FILE_PATTERN"]
    )

    for candidate in sorted(log_dir.iterdir()):
        if not candidate.is_file():
            continue

        entry_date = resolve_entry_date(candidate, day_file_pattern)
        if entry_date is None:
            entry_date = datetime.fromtimestamp(
                candidate.stat().st_mtime
            ).date()

        if entry_date.year != year or entry_date.month != month:
            continue

        counts[entry_date.day] += count_entries(candidate)

    return dict(counts)
