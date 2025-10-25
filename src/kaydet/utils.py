"""Utility functions for kaydet."""

from __future__ import annotations

import shlex
import subprocess
from configparser import ConfigParser, SectionProxy
from datetime import datetime, timedelta
from os import environ as env
from os import fdopen, remove
from pathlib import Path
from tempfile import mkstemp
from typing import Iterable, Optional, Tuple

from .models import DiaryEntry
from .parsers import parse_day_entries, resolve_entry_date

CONFIG_SECTION = "SETTINGS"
DEFAULT_SETTINGS = {
    "DAY_FILE_PATTERN": "%Y-%m-%d.txt",
    "DAY_TITLE_PATTERN": "%Y/%m/%d/ - %A",
    "LOG_DIR": str(
        Path(env.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
        / "kaydet"
    ),
    "EDITOR": env.get("EDITOR", "vim"),
}
LAST_ENTRY_FILENAME = "last_entry_timestamp"
REMINDER_THRESHOLD = timedelta(hours=2)


def get_config() -> Tuple[SectionProxy, Path, Path]:
    """Load configuration and ensure defaults exist."""
    config_root = Path(env.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    config_dir = config_root / "kaydet"
    config_dir.mkdir(parents=True, exist_ok=True)
    parser = ConfigParser(interpolation=None)
    config_path = config_dir / "config.ini"
    if config_path.exists():
        parser.read(config_path, encoding="utf-8")
    if CONFIG_SECTION not in parser:
        parser[CONFIG_SECTION] = {}
    section = parser[CONFIG_SECTION]
    updated = False
    for key, value in DEFAULT_SETTINGS.items():
        if not section.get(key):
            section[key] = value
            updated = True
    if updated:
        with config_path.open("w", encoding="utf-8") as config_file:
            parser.write(config_file)
    return section, config_path, config_dir


def iter_diary_entries(
    log_dir: Path, config: SectionProxy
) -> Iterable[DiaryEntry]:
    """Yield entries from every diary file sorted by filename."""
    if not log_dir.exists():
        return
    day_file_pattern = config.get(
        "DAY_FILE_PATTERN", DEFAULT_SETTINGS["DAY_FILE_PATTERN"]
    )
    for candidate in sorted(log_dir.glob("*.txt")):
        if not candidate.is_file():
            continue
        entry_date = resolve_entry_date(candidate, day_file_pattern)
        yield from parse_day_entries(candidate, entry_date)


def save_last_entry_timestamp(config_dir: Path, moment: datetime) -> None:
    """Persist the provided timestamp for subsequent reminder checks."""
    (config_dir / LAST_ENTRY_FILENAME).write_text(
        moment.isoformat(), encoding="utf-8"
    )


def load_last_entry_timestamp(
    config_dir: Path, log_dir: Path
) -> Optional[datetime]:
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
            if candidate.is_file() and candidate.suffix == ".txt":
                mtime = candidate.stat().st_mtime
                if latest_mtime is None or mtime > latest_mtime:
                    latest_mtime = mtime
    if latest_mtime is None:
        return None
    return datetime.fromtimestamp(latest_mtime)


def ensure_day_file(
    log_dir: Path, now: datetime, config: SectionProxy
) -> Path:
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


def open_editor(initial_text: str, editor_command: str) -> str:
    """Open a temp file in the configured editor and return its text."""
    fd, tmp_path = mkstemp()
    try:
        with fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(initial_text)
        subprocess.call(shlex.split(editor_command) + [str(tmp_path)])
        return Path(tmp_path).read_text(encoding="utf-8")
    finally:
        try:
            remove(tmp_path)
        except OSError:
            pass
