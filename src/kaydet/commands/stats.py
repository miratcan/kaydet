"""Stats command — diary activity for motivation / calendars."""

from __future__ import annotations

from collections import defaultdict
from configparser import SectionProxy
from datetime import date, datetime, timedelta
from pathlib import Path

from ..parsers import count_entries, resolve_entry_date
from ..utils import DEFAULT_SETTINGS, get_file_glob_from_pattern


def stats_command(
    log_dir: Path,
    config: SectionProxy,
    now: datetime,
) -> dict:
    """Return last-year daily activity (git-stats style) plus streaks."""
    if not log_dir.exists():
        return {
            "success": False,
            "error": "\U0001f4ca No diary entries found yet",
        }

    day_pattern = config.get(
        "DAY_FILE_PATTERN", DEFAULT_SETTINGS["DAY_FILE_PATTERN"]
    )
    glob_pattern = get_file_glob_from_pattern(day_pattern)

    if not any(log_dir.glob(glob_pattern)):
        return {
            "success": False,
            "error": "\U0001f4ca No diary entries found yet",
        }

    end = now.date()
    # Match git-stats default window: one calendar year back
    try:
        start = end.replace(year=end.year - 1)
    except ValueError:
        # Feb 29 → Feb 28
        start = end.replace(year=end.year - 1, day=28)
    daily = collect_range_counts(log_dir, config, start, end)
    total = sum(daily.values())
    longest, current = compute_streaks(daily, start, end)
    max_day = max(daily.values()) if daily else 0

    month_counts = collect_month_counts(log_dir, config, now.year, now.month)

    return {
        "success": True,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "days": {d.isoformat(): c for d, c in sorted(daily.items())},
        "total_entries": total,
        "longest_streak": longest,
        "current_streak": current,
        "max_a_day": max_day,
        # retained for MCP / older consumers (current calendar month)
        "year": now.year,
        "month": now.month,
        "month_name": now.strftime("%B %Y"),
        "month_days": month_counts,
    }


def collect_month_counts(
    log_dir: Path, config: SectionProxy, year: int, month: int
) -> dict[int, int]:
    """Return a mapping of day number to entry count for the given month."""
    counts: dict[int, int] = defaultdict(int)
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


def collect_range_counts(
    log_dir: Path,
    config: SectionProxy,
    start: date,
    end: date,
) -> dict[date, int]:
    """Return entry counts per calendar day in [start, end]."""
    counts: dict[date, int] = defaultdict(int)
    day_file_pattern = config.get(
        "DAY_FILE_PATTERN", DEFAULT_SETTINGS["DAY_FILE_PATTERN"]
    )

    if not log_dir.exists():
        return {}

    for candidate in sorted(log_dir.iterdir()):
        if not candidate.is_file():
            continue

        entry_date = resolve_entry_date(candidate, day_file_pattern)
        if entry_date is None:
            entry_date = datetime.fromtimestamp(
                candidate.stat().st_mtime
            ).date()

        if entry_date < start or entry_date > end:
            continue

        counts[entry_date] += count_entries(candidate)

    return dict(counts)


def compute_streaks(
    daily: dict[date, int], start: date, end: date
) -> tuple[int, int]:
    """Return (longest_streak, current_streak) like cli-gh-cal / git-stats.

    Current streak is the run ending on ``end`` (0 if that day is empty).
    """
    longest = 0
    run = 0
    d = start
    while d <= end:
        if daily.get(d, 0) > 0:
            run += 1
            longest = max(longest, run)
        else:
            run = 0
        d += timedelta(days=1)
    return longest, run
