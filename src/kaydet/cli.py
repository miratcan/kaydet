"""Command-line interface for the kaydet diary application."""
from __future__ import annotations

import argparse
import subprocess
from configparser import ConfigParser, SectionProxy
from datetime import datetime, timedelta
from os import environ as env, fdopen, remove
from pathlib import Path
from tempfile import mkstemp
from textwrap import dedent
from typing import Optional, Tuple

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


def append_entry(day_file: Path, timestamp: str, entry_text: str) -> None:
    """Append a timestamped entry to the daily file."""
    with day_file.open("a", encoding="utf-8") as handle:
        handle.write(f"{timestamp}: {entry_text}\n")


def main() -> None:
    """Application entry point for the kaydet CLI."""
    config, config_path, config_dir = get_config()

    args = parse_args(config_path)

    log_dir = Path(config["LOG_DIR"]).expanduser()

    now = datetime.now()

    if args.reminder:
        maybe_show_reminder(config_dir, log_dir, now)
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

    append_entry(day_file, now.strftime("%H:%M"), entry)
    save_last_entry_timestamp(config_dir, now)

    print("Entry added to:", day_file)
