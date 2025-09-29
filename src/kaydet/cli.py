"""Command-line interface for the kaydet diary application."""
from __future__ import annotations

import argparse
import calendar
import re
import subprocess
from configparser import ConfigParser, SectionProxy
from datetime import date, datetime, timedelta
from os import environ as env, fdopen, remove
from pathlib import Path
from tempfile import mkstemp
from textwrap import dedent
from collections import defaultdict
from typing import Dict, Optional, Tuple

from startfile import startfile

from . import __description__

CONFIG_SECTION = "SETTINGS"
DEFAULT_SETTINGS = {
    "DAY_FILE_PATTERN": "%Y-%m-%d.txt",
    "DAY_TITLE_PATTERN": "%Y/%m/%d/ - %A",
    "LOG_DIR": str(Path.home() / ".kaydet"),
    "EDITOR": env.get("EDITOR", "vim"),
}
LAST_ENTRY_FILENAME = "last_entry_timestamp"
REMINDER_THRESHOLD = timedelta(hours=2)
ENTRY_LINE_PATTERN = re.compile(r"^\d{2}:\d{2}: ")
TAG_CAPTURE_PATTERN = re.compile(r"^\d{2}:\d{2}: \[(?P<tags>[a-z-]+(?:,[a-z-]+)*)\]\s")
TAG_PATTERN = re.compile(r"^[a-z-]+$")


def parse_args(config_path: Path) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        prog="kaydet",
        description=__description__,
        epilog=dedent(
            f"""
            You can configure this by editing: {config_path}

              $ kaydet 'I am feeling grateful now.'
              $ kaydet \"When I'm typing this I felt that I need an editor\" --editor
            """
        ).strip(),
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "entry",
        type=str,
        nargs="?",
        metavar="Entry",
        help=(
            "Your entry to be saved. If not given, the configured editor will be "
            "opened for a longer note."
        ),
    )
    parser.add_argument(
        "--editor",
        "-e",
        dest="use_editor",
        action="store_true",
        help="Force opening the configured editor, even when an entry is provided.",
    )
    parser.add_argument(
        "--folder",
        "-f",
        dest="open_folder",
        action="store_true",
        help="Open the folder that contains your records and exit.",
    )
    parser.add_argument(
        "--reminder",
        dest="reminder",
        action="store_true",
        help="Print a reminder if it has been more than two hours since the last entry.",
    )
    parser.add_argument(
        "--stats",
        dest="stats",
        action="store_true",
        help="Show a calendar for the current month with daily entry counts.",
    )
    parser.add_argument(
        "--tags",
        dest="list_tags",
        action="store_true",
        help="List every tag you have used so far and exit.",
    )
    parser.add_argument(
        "--tag",
        "-t",
        dest="tag",
        type=validate_tag,
        metavar="TAG",
        help="Assign a lowercase tag (letters and hyphen only) to the saved entry.",
    )
    return parser.parse_args()


def get_entry(args: argparse.Namespace, config: SectionProxy) -> str:
    """Resolve the entry content either from CLI arguments or an editor."""
    if args.use_editor or args.entry is None:
        return open_editor(args.entry or "", config["EDITOR"])
    return args.entry


def open_editor(initial_text: str, editor_command: str) -> str:
    """Open a temporary file with the configured editor and return its contents."""
    fd, tmp_path = mkstemp()
    temp_file = Path(tmp_path)
    try:
        with fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(initial_text)
        subprocess.call([editor_command, str(temp_file)])
        return temp_file.read_text(encoding="utf-8")
    finally:
        try:
            remove(temp_file)
        except OSError:
            pass


def get_config() -> Tuple[SectionProxy, Path, Path]:
    """Load configuration and ensure defaults exist."""
    config_root = Path(env.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    config_dir = config_root / "kaydet"
    config_dir.mkdir(parents=True, exist_ok=True)

    parser = ConfigParser(interpolation=None)
    config_path = config_dir / "config.ini"

    if config_path.exists():
        parser.read(config_path, encoding="utf-8")

    updated = False
    if CONFIG_SECTION not in parser:
        parser[CONFIG_SECTION] = DEFAULT_SETTINGS.copy()
        updated = True

    section = parser[CONFIG_SECTION]
    for key, value in DEFAULT_SETTINGS.items():
        current = section.get(key)
        if current is None or current.strip() == "":
            section[key] = value
            updated = True

    if updated:
        with config_path.open("w", encoding="utf-8") as config_file:
            parser.write(config_file)

    return section, config_path, config_dir


def load_last_entry_timestamp(config_dir: Path, log_dir: Path) -> Optional[datetime]:
    """Return the timestamp of the most recent saved entry, if any."""
    record_path = config_dir / LAST_ENTRY_FILENAME
    try:
        raw_value = record_path.read_text(encoding="utf-8").strip()
        if raw_value:
            return datetime.fromisoformat(raw_value)
    except (FileNotFoundError, ValueError):
        pass

    latest_mtime: Optional[float] = None
    if log_dir.exists():
        for candidate in log_dir.iterdir():
            if candidate.is_file():
                mtime = candidate.stat().st_mtime
                if latest_mtime is None or mtime > latest_mtime:
                    latest_mtime = mtime
    if latest_mtime is None:
        return None
    return datetime.fromtimestamp(latest_mtime)


def save_last_entry_timestamp(config_dir: Path, moment: datetime) -> None:
    """Persist the provided timestamp for subsequent reminder checks."""
    record_path = config_dir / LAST_ENTRY_FILENAME
    record_path.write_text(moment.isoformat(), encoding="utf-8")


def maybe_show_reminder(config_dir: Path, log_dir: Path, now: datetime) -> None:
    """Emit a reminder if no entry has been written recently."""
    last_entry = load_last_entry_timestamp(config_dir, log_dir)
    if last_entry is None:
        print(
            "You haven't written any Kaydet entries yet. "
            "Capture your first note with `kaydet --editor`."
        )
        return

    if now - last_entry >= REMINDER_THRESHOLD:
        print(
            "It's been over two hours since your last Kaydet entry. "
            "Capture what you've been up to with `kaydet --editor`."
        )


def ensure_day_file(log_dir: Path, now: datetime, config: SectionProxy) -> Path:
    """Ensure the daily file exists and return its path."""
    log_dir.mkdir(parents=True, exist_ok=True)

    file_name = now.strftime(config["DAY_FILE_PATTERN"])
    day_file = log_dir / file_name

    if not day_file.exists():
        title = now.strftime(config["DAY_TITLE_PATTERN"])
        with day_file.open("w", encoding="utf-8") as handle:
            handle.write(f"{title}\n")
            handle.write("-" * (len(title) - 1))
            handle.write("\n")

    return day_file


def append_entry(day_file: Path, timestamp: str, entry_text: str, tag: Optional[str]) -> None:
    """Append a timestamped entry to the daily file."""
    with day_file.open("a", encoding="utf-8") as handle:
        formatted = format_entry(entry_text, tag)
        handle.write(f"{timestamp}: {formatted}\n")


def show_calendar_stats(log_dir: Path, config: SectionProxy, now: datetime) -> None:
    """Render a calendar for the current month with entry counts per day."""
    if not log_dir.exists():
        print("No diary entries found yet.")
        return

    year = now.year
    month = now.month

    counts = collect_month_counts(log_dir, config, year, month)

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
) -> Dict[int, int]:
    """Return a mapping of day number to entry count for the given month."""
    counts: Dict[int, int] = defaultdict(int)
    day_file_pattern = config.get("DAY_FILE_PATTERN", DEFAULT_SETTINGS["DAY_FILE_PATTERN"])

    for candidate in sorted(log_dir.iterdir()):
        if not candidate.is_file():
            continue

        entry_date = resolve_entry_date(candidate, day_file_pattern)
        if entry_date is None:
            entry_date = datetime.fromtimestamp(candidate.stat().st_mtime).date()

        if entry_date.year != year or entry_date.month != month:
            continue

        counts[entry_date.day] += count_entries(candidate)

    return dict(counts)


def resolve_entry_date(day_file: Path, pattern: str) -> Optional[datetime.date]:
    """Infer the date represented by a diary file using the configured pattern."""
    try:
        return datetime.strptime(day_file.name, pattern).date()
    except ValueError:
        return None


def count_entries(day_file: Path) -> int:
    """Count timestamped diary entries inside a daily file."""
    lines = day_file.read_text(encoding="utf-8").splitlines()
    return sum(1 for line in lines if ENTRY_LINE_PATTERN.match(line))


def list_tags(log_dir: Path) -> None:
    """Print the unique set of tags recorded across all diary entries."""
    if not log_dir.exists():
        print("No diary entries found yet.")
        return

    tags = sorted({tag for path in log_dir.iterdir() if path.is_file() for tag in extract_tags(path)})
    if not tags:
        print("No tags have been recorded yet.")
        return

    for tag in tags:
        print(tag)


def extract_tags(day_file: Path) -> Tuple[str, ...]:
    """Return all tags found within a single diary file."""
    found = []
    for line in day_file.read_text(encoding="utf-8").splitlines():
        match = TAG_CAPTURE_PATTERN.match(line)
        if match:
            found.extend(match.group("tags").split(","))
    return tuple(found)


def format_entry(entry_text: str, tag: Optional[str]) -> str:
    """Prepend the optional tag to the entry text."""
    if tag:
        return f"[{tag}] {entry_text}"
    return entry_text


def validate_tag(value: str) -> str:
    """Ensure tag strings only contain lowercase letters and hyphens."""
    if not TAG_PATTERN.fullmatch(value):
        raise argparse.ArgumentTypeError(
            "Tags must use only lowercase letters and hyphens (example: personal-growth)."
        )
    return value


def main() -> None:
    """Application entry point for the kaydet CLI."""
    config, config_path, config_dir = get_config()

    args = parse_args(config_path)

    log_dir = Path(config["LOG_DIR"]).expanduser()

    now = datetime.now()

    if args.reminder:
        maybe_show_reminder(config_dir, log_dir, now)
        return

    if args.stats:
        show_calendar_stats(log_dir, config, now)
        return

    if args.list_tags:
        list_tags(log_dir)
        return

    log_dir.mkdir(parents=True, exist_ok=True)

    if args.open_folder:
        startfile(str(log_dir))
        return

    day_file = ensure_day_file(log_dir, now, config)

    entry = get_entry(args, config).strip()
    if not entry:
        print("Nothing to save.")
        return

    append_entry(day_file, now.strftime("%H:%M"), entry, args.tag)
    save_last_entry_timestamp(config_dir, now)

    print("Entry added to:", day_file)
