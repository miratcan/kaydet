"""Utility functions for kaydet."""

from __future__ import annotations

import platform
import shlex
import subprocess
from configparser import ConfigParser, SectionProxy
from datetime import datetime, timedelta
from os import environ as env
from os import fdopen, remove
from pathlib import Path
from tempfile import mkstemp
from typing import Iterable, Optional, Tuple

from .models import Entry
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
    "COLOR_HEADER": "bold cyan",
    "COLOR_TAG": "bold magenta",
    "COLOR_DATE": "green",
    "COLOR_ID": "yellow",
}
LAST_ENTRY_FILENAME = "last_entry_timestamp"
REMINDER_THRESHOLD = timedelta(hours=2)


def get_default_storage_path() -> Path:
    """Return the default storage path based on the operating system."""
    system = platform.system()

    if system == "Darwin":  # macOS
        return Path.home() / "Documents" / "Kaydet"
    elif system == "Windows":
        return Path.home() / "Documents" / "Kaydet"
    else:  # Linux and others
        return Path.home() / "Kaydet"


def get_default_index_path() -> Path:
    """Return the default index path (always local)."""
    return Path(
        env.get("XDG_DATA_HOME") or Path.home() / ".local" / "share"
    ) / "kaydet"


def prompt_storage_location() -> Path:
    """Prompt user for storage location on first run."""
    print("\nWelcome to Kaydet!\n")
    print("Where should I store your entries?")
    print("(Plain text files, safe to sync with cloud storage)\n")

    default = get_default_storage_path()
    print(f"Default: {default}")

    try:
        user_input = input("Path (or press Enter for default): ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\nUsing default path.")
        user_input = ""

    if not user_input:
        storage_path = default
    else:
        storage_path = Path(user_input).expanduser()

    storage_path.mkdir(parents=True, exist_ok=True)

    print(f"\n✓ Kaydet will store entries in: {storage_path}")
    print(f"✓ Index stored locally in: {get_default_index_path()}\n")

    return storage_path


def load_config() -> Tuple[SectionProxy, Path, Path, Path, Path]:
    """Load configuration, ensuring directories and defaults exist.

    Returns:
        Tuple of (config_section, config_path, config_dir, storage_dir, index_dir)
    """
    current_home = Path.home()
    home_config_dir = current_home / ".config" / "kaydet"
    xdg_root = env.get("XDG_CONFIG_HOME")
    config_root = Path(xdg_root) if xdg_root else Path.home() / ".config"
    config_dir = config_root / "kaydet"
    fallback_path = home_config_dir / "config.ini"
    use_fallback = False
    if fallback_path.exists():
        system_home = Path(env.get("HOME", str(current_home))).expanduser()
        try:
            patched_home = current_home.resolve() != system_home.resolve()
        except OSError:
            patched_home = True

        if not xdg_root or patched_home:
            use_fallback = True
        else:
            try:
                home_dir = current_home.resolve()
                xdg_dir = Path(xdg_root).expanduser().resolve()
                if xdg_dir.is_relative_to(home_dir):
                    use_fallback = True
            except (OSError, RuntimeError):
                # If resolution fails, prefer XDG path.
                pass
    if use_fallback:
        config_dir = home_config_dir
        config_path = fallback_path
    else:
        config_path = config_dir / "config.ini"

    config_dir.mkdir(parents=True, exist_ok=True)
    parser = ConfigParser(interpolation=None)
    if config_path.exists():
        parser.read(config_path, encoding="utf-8")
    if CONFIG_SECTION not in parser:
        parser[CONFIG_SECTION] = {}
    section = parser[CONFIG_SECTION]

    # Check if STORAGE_DIR is set; if not, this is first run
    if not section.get("STORAGE_DIR"):
        storage_dir = prompt_storage_location()
        section["STORAGE_DIR"] = str(storage_dir)
        with config_path.open("w", encoding="utf-8") as config_file:
            parser.write(config_file)

    updated = False
    for key, value in DEFAULT_SETTINGS.items():
        if not section.get(key):
            section[key] = value
            updated = True
    if updated:
        with config_path.open("w", encoding="utf-8") as config_file:
            parser.write(config_file)

    # Storage directory: where .txt files live (can be synced)
    storage_dir = Path(section["STORAGE_DIR"]).expanduser()
    storage_dir.mkdir(parents=True, exist_ok=True)

    # Index directory: where index.db lives (always local)
    # Use LOG_DIR for backward compatibility, or default index path
    if section.get("INDEX_DIR"):
        index_dir = Path(section["INDEX_DIR"]).expanduser()
    else:
        # For backward compatibility: if LOG_DIR was customized, use it for index
        # Otherwise, use the new default index path
        log_dir_value = section.get("LOG_DIR", "")
        default_log_dir = DEFAULT_SETTINGS["LOG_DIR"]
        if log_dir_value and log_dir_value != default_log_dir:
            # User had a custom LOG_DIR, keep using it for index
            index_dir = Path(log_dir_value).expanduser()
        else:
            # Use new default
            index_dir = get_default_index_path()

    index_dir.mkdir(parents=True, exist_ok=True)

    return section, config_path, config_dir, storage_dir, index_dir




def iter_diary_entries(
    log_dir: Path, config: SectionProxy
) -> Iterable[Entry]:
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
