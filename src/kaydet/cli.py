"""Command-line interface for the kaydet diary application."""

from __future__ import annotations

import argparse
import subprocess  # Used by tests  # noqa: F401
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
from .indexing import rebuild_index_if_empty
from .parsers import extract_tags_from_text  # noqa: F401
from .sync import sync_modified_diary_files
from .utils import DEFAULT_SETTINGS, load_config  # noqa: F401

INDEX_FILENAME = "index.db"


def build_parser(config_path: Path) -> argparse.ArgumentParser:
    """Create the kaydet CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="kaydet",
        description=__description__,
        epilog=dedent(
            f"""You can configure this by editing: {config_path}\n\n"""
            "  $ kaydet 'I am feeling grateful now.'\n"
            '  $ kaydet "Fixed issue" status:done time:45m #work\n'
            "  $ kaydet --editor"
            ""
        ),
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "entry", type=str, nargs="*", metavar="Entry", help="Entry content."
    )
    parser.add_argument(
        "--editor",
        "-e",
        dest="use_editor",
        action="store_true",
        help="Force opening editor.",
    )
    parser.add_argument(
        "--folder",
        "-f",
        dest="open_folder",
        action="store_true",
        help="Open the log directory.",
    )
    parser.add_argument(
        "--reminder",
        dest="reminder",
        action="store_true",
        help="Show reminder.",
    )
    parser.add_argument(
        "--stats",
        dest="stats",
        action="store_true",
        help="Show calendar stats.",
    )
    parser.add_argument(
        "--tags", dest="list_tags", action="store_true", help="List all tags."
    )
    parser.add_argument(
        "--search", dest="search", metavar="TEXT", help="Search entries."
    )
    parser.add_argument(
        "--doctor", dest="doctor", action="store_true",
        help="Rebuild search index.",
    )
    parser.add_argument(
        "--format",
        dest="output_format",
        choices=["text", "json"],
        default="text",
        help="Output format.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
        help="Show version.",
    )
    return parser


def main() -> None:
    """Application entry point for the kaydet CLI."""
    config, config_path, config_dir, log_dir = load_config()
    parser = build_parser(config_path)
    args = parser.parse_args()

    now = datetime.now()

    if args.reminder:
        reminder_command(config_dir, log_dir, now)
        return
    if args.open_folder:
        startfile(str(log_dir))
        return

    db_path = log_dir / INDEX_FILENAME
    db = database.get_db_connection(db_path)
    database.initialize_database(db)

    if args.doctor:
        doctor_command(db, log_dir, config, now)
        return

    sync_modified_diary_files(db, log_dir, config, now)
    rebuild_index_if_empty(db, log_dir, config, now)

    if args.stats:
        stats_command(log_dir, config, now, args.output_format)
        return

    if args.list_tags:
        tags_command(db, args.output_format)
        return

    if args.search:
        search_command( db, log_dir, config, args.search, args.output_format)
        return

    add_entry_command(
        args, config, config_dir, log_dir, now, db
    )
