"""Command-line interface for the kaydet diary application."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from textwrap import dedent

from startfile import startfile

from . import __description__, __version__, database
from .commands import (
    add_entry_command,
    doctor_command,
    reminder_command,
    search_command,
    stats_command,
    tags_command,
)
from .parsers import extract_tags_from_text
from .utils import DEFAULT_SETTINGS, get_config, open_editor

# For backward compatibility - re-export commonly used items
import subprocess  # Used by tests

INDEX_FILENAME = "index.db"


def main() -> None:
    """Application entry point for the kaydet CLI."""
    config, config_path, config_dir = get_config()
    parser = argparse.ArgumentParser(
        prog="kaydet",
        description=__description__,
        epilog=dedent(
            f"""You can configure this by editing: {config_path}\n\n"""
            "  $ kaydet 'I am feeling grateful now.'\n"
            "  $ kaydet \"Fixed issue\" status:done time:45m #work\n"
            "  $ kaydet --editor"""
        ),
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("entry", type=str, nargs="*", metavar="Entry", help="Entry content.")
    parser.add_argument("--editor", "-e", dest="use_editor", action="store_true", help="Force opening editor.")
    parser.add_argument("--folder", "-f", dest="open_folder", nargs="?", const="", metavar="TAG", help="Open log directory.")
    parser.add_argument("--reminder", dest="reminder", action="store_true", help="Show reminder.")
    parser.add_argument("--stats", dest="stats", action="store_true", help="Show calendar stats.")
    parser.add_argument("--tags", dest="list_tags", action="store_true", help="List all tags.")
    parser.add_argument("--search", dest="search", metavar="TEXT", help="Search entries.")
    parser.add_argument("--doctor", dest="doctor", action="store_true", help="Rebuild search index.")
    parser.add_argument("--format", dest="output_format", choices=["text", "json"], default="text", help="Output format.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}", help="Show version.")
    args = parser.parse_args()

    log_dir = Path(config["LOG_DIR"]).expanduser()
    now = datetime.now()

    if args.reminder:
        reminder_command(config_dir, log_dir, now)
        return
    elif args.stats:
        stats_command(log_dir, config, now, args.output_format)
        return
    elif args.list_tags:
        log_dir.mkdir(parents=True, exist_ok=True)
        db_path = log_dir / INDEX_FILENAME
        db = database.get_db_connection(db_path)
        database.initialize_database(db)
        tags_command(db, args.output_format)
    elif args.search:
        log_dir.mkdir(parents=True, exist_ok=True)
        db_path = log_dir / INDEX_FILENAME
        db = database.get_db_connection(db_path)
        database.initialize_database(db)
        search_command(db, log_dir, config, args.search, args.output_format)
    elif args.doctor:
        log_dir.mkdir(parents=True, exist_ok=True)
        db_path = log_dir / INDEX_FILENAME
        db = database.get_db_connection(db_path)
        database.initialize_database(db)
        doctor_command(db, log_dir, config)
    elif args.open_folder is not None:
        if args.open_folder == "":
            startfile(str(log_dir))
        else:
            tag_name = args.open_folder.lstrip("#")
            print(
                "Tag folders are no longer maintained. "
                f"Search for '#{tag_name}' instead."
            )
        return
    else:
        log_dir.mkdir(parents=True, exist_ok=True)
        db_path = log_dir / INDEX_FILENAME
        db = database.get_db_connection(db_path)
        database.initialize_database(db)
        add_entry_command(args, config, config_dir, log_dir, now, db)
