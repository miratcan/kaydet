"""Stats command."""

from collections import defaultdict
from configparser import SectionProxy
from datetime import datetime
from pathlib import Path

from ..parsers import count_entries, resolve_entry_date
from ..utils import DEFAULT_SETTINGS, get_file_glob_from_pattern


def stats_command(
    storage_dir: Path,
    config: SectionProxy,
    now: datetime,
) -> dict:
    """Return calendar stats for the current month."""
    if not storage_dir.exists():
        return {"success": False, "error": "No entries found yet."}

    day_pattern = config.get(
        "DAY_FILE_PATTERN", DEFAULT_SETTINGS["DAY_FILE_PATTERN"]
    )
    glob_pattern = get_file_glob_from_pattern(day_pattern)

    if not any(storage_dir.glob(glob_pattern)):
        return {"success": False, "error": "No entries found yet."}

    year = now.year
    month = now.month

    counts = collect_month_counts(storage_dir, config, year, month)

    return {
        "success": True,
        "year": year,
        "month": month,
        "month_name": now.strftime("%B %Y"),
        "days": counts,
        "total_entries": sum(counts.values()),
    }


def collect_month_counts(
    storage_dir: Path, config: SectionProxy, year: int, month: int
):
    """Return a mapping of day number to entry count for the given month."""
    counts = defaultdict(int)
    day_file_pattern = config.get(
        "DAY_FILE_PATTERN", DEFAULT_SETTINGS["DAY_FILE_PATTERN"]
    )

    for candidate in sorted(storage_dir.iterdir()):
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
