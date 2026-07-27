"""Simple print helpers for stats, tags, and doctor commands."""

from __future__ import annotations

import shutil
from datetime import date, timedelta
from typing import Any

from rich.console import Console
from rich.text import Text

from .json_output import print_json_err, print_json_ok

# IonicaBizau/cli-gh-cal LEVELS + git-stats-colors DARK theme
# (colored output always uses ◼ like git-stats-colors does)
_LEVEL_COLORS = (
    "#343434",
    "#2e643d",
    "#589f43",
    "#98bc21",
    "#b9fc04",
)
_FG = "#565656"
_WEEKDAYS = ("Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat")


def _level_for(count: int, max_count: int) -> int:
    """Match cli-gh-cal: max/(5*2) buckets; any activity ≥ level 1."""
    if count <= 0 or max_count <= 0:
        return 0
    bucket = max_count / 10.0
    if bucket <= 0:
        return 1
    level = round(count / bucket)
    if level >= 4:
        return 4
    if level == 0:
        return 1
    return level


def _cell(level: int) -> Text:
    return Text("◼", style=_LEVEL_COLORS[level])


def _fmt_date(d: date) -> str:
    """Match moment's ``MMM D, YYYY`` (no leading zero on day)."""
    return f"{d.strftime('%b')} {d.day}, {d.year}"


def _print_git_stats_calendar(
    days: dict[str, int],
    start: date,
    end: date,
    console: Console,
    *,
    total: int,
    longest: int,
    current: int,
    max_day: int,
) -> None:
    """Render a year grid like ``git-stats`` / cli-gh-cal."""
    max_count = max(days.values()) if days else 0

    weeks: list[list[int | None]] = []
    month_at: dict[int, str] = {}
    week: list[int | None] = [None] * 7

    d = start
    while d <= end:
        sun_idx = (d.weekday() + 1) % 7  # Sun=0 … Sat=6
        # New week column starts on Sunday (cli-gh-cal firstDay)
        if sun_idx == 0 and any(c is not None for c in week):
            weeks.append(week)
            week = [None] * 7

        week[sun_idx] = _level_for(days.get(d.isoformat(), 0), max_count)
        if d.day == 1:
            month_at[len(weeks)] = d.strftime("%b")

        d += timedelta(days=1)

    if any(c is not None for c in week):
        weeks.append(week)

    # Crop left when terminal is narrow (cli-gh-cal: weeks*2 + 11)
    term_w = shutil.get_terminal_size(fallback=(100, 24)).columns
    max_weeks = max(1, (term_w - 12) // 2)
    cropped = False
    if len(weeks) > max_weeks:
        cut = len(weeks) - max_weeks
        weeks = weeks[cut:]
        month_at = {i - cut: lab for i, lab in month_at.items() if i >= cut}
        cropped = True

    # Month labels at 2-col pitch per week
    month_chars = [" "] * max(2 * len(weeks), 1)
    for i, label in month_at.items():
        if 0 <= i < len(weeks):
            pos = 2 * i
            for j, ch in enumerate(label[:3]):
                if pos + j < len(month_chars):
                    month_chars[pos + j] = ch
    month_header = "".join(month_chars)
    # cli-gh-cal left-pads with 4 spaces ("MMMM" hack)
    header_plain = "    " + month_header

    day_rows: list[Text] = []
    day_plains: list[str] = []
    for wd, name in enumerate(_WEEKDAYS):
        row = Text(name, style=_FG)
        plain_parts = [name]
        for col in weeks:
            level = col[wd]
            row.append(" ")
            plain_parts.append(" ")
            if level is None:
                row.append(" ")
                plain_parts.append(" ")
            else:
                row.append_text(_cell(level))
                plain_parts.append("◼")
        day_rows.append(row)
        day_plains.append("".join(plain_parts))

    when = f"{_fmt_date(start)} – {_fmt_date(end)}"
    sep = "\n" if cropped else " | "
    stats_parts = [
        f"Entries in {when}: {total}",
        f"Longest Streak: {longest} days",
        f"Current Streak: {current} days",
        f"Max a day: {max_day}",
    ]
    if cropped:
        stats_lines = stats_parts  # one per line
        dash_line = " * * * "
    else:
        stats_lines = [sep.join(stats_parts)]
        body_w = max(
            len(header_plain),
            max((len(p) for p in day_plains), default=0),
            40,
        )
        dash_line = "-" * body_w

    all_plain = [header_plain, *day_plains, dash_line, *stats_lines]
    inner_w = max(len(line) for line in all_plain) + 1

    def box_edge(char_left: str, char_mid: str, char_right: str) -> Text:
        return Text(
            char_left + char_mid * (inner_w + 1) + char_right,
            style=_FG,
        )

    def box_plain_row(s: str) -> Text:
        pad = inner_w - len(s)
        return Text(f"║ {s}{' ' * max(0, pad)}║", style=_FG)

    console.print(box_edge("╔", "═", "╗"))
    console.print(box_plain_row(header_plain))
    for row, plain in zip(day_rows, day_plains, strict=True):
        pad = inner_w - len(plain)
        line = Text("║ ", style=_FG)
        line.append_text(row)
        if pad > 0:
            line.append(" " * pad, style=_FG)
        line.append("║", style=_FG)
        console.print(line)
    console.print(box_plain_row(dash_line))
    for part in stats_lines:
        console.print(box_plain_row(part))
    console.print(box_edge("╚", "═", "╝"))


def print_stats(result: dict[str, Any], output_format: str) -> None:
    """Print last-year activity like ``git-stats`` (GitHub calendar)."""
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
                "start": result.get("start"),
                "end": result.get("end"),
                "days": result.get("days"),
                "total_entries": result["total_entries"],
                "longest_streak": result.get("longest_streak"),
                "current_streak": result.get("current_streak"),
                "max_a_day": result.get("max_a_day"),
                "year": result.get("year"),
                "month": result.get("month"),
                "month_name": result.get("month_name"),
                "month_days": result.get("month_days"),
            }
        )
        return

    console = Console(highlight=False)
    days = result.get("days") or {}
    start = date.fromisoformat(result["start"])
    end = date.fromisoformat(result["end"])
    _print_git_stats_calendar(
        days,
        start,
        end,
        console,
        total=result["total_entries"],
        longest=result.get("longest_streak", 0),
        current=result.get("current_streak", 0),
        max_day=result.get("max_a_day", 0),
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
