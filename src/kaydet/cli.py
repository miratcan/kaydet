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
    browse_command,
    delete_entry_command,
    doctor_command,
    done_command,
    edit_entry_command,
    list_todos_command,
    reminder_command,
    search_command,
    stats_command,
    tags_command,
    todo_command,
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
            '  $ kaydet "Fixed bug #work #urgent status:done time:2h"\n'
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
        "--search", dest="search", metavar="TEXT", help="Search entries (or filter todos with --todo)."
    )
    parser.add_argument(
        "--browse",
        dest="browse",
        action="store_true",
        help="Open the interactive browser.",
    )
    parser.add_argument(
        "--doctor", dest="doctor", action="store_true",
        help="Rebuild search index.",
    )
    parser.add_argument(
        "--edit",
        dest="edit",
        type=int,
        metavar="ID",
        help="Edit an entry by numeric identifier.",
    )
    parser.add_argument(
        "--delete",
        dest="delete",
        type=int,
        metavar="ID",
        help="Delete an entry by numeric identifier.",
    )
    parser.add_argument(
        "--todo",
        dest="todo",
        nargs="*",
        metavar="TEXT",
        help="Create a new todo entry (auto-adds status:pending and #todo tag).",
    )
    parser.add_argument(
        "--done",
        dest="done",
        type=int,
        metavar="ID",
        help="Mark a todo as done by ID.",
    )
    parser.add_argument(
        "--list-todos",
        dest="list_todos",
        action="store_true",
        help="List all todos with their status.",
    )
    parser.add_argument(
        "--yes",
        dest="assume_yes",
        action="store_true",
        help="Automatically confirm prompts.",
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
    db = database.get_db_connection(db_path) # TODO: This is returnin connection but it's named as db?
    database.initialize_database(db)

    if args.doctor:
        doctor_command(db, log_dir, config, now)
        return

    sync_modified_diary_files(db, log_dir, config, now)
    rebuild_index_if_empty(db, log_dir, config, now)

    # TODO: I hated this, will be removed in future.
    if args.browse:
        browse_command(db, log_dir, config)
        return

    if args.stats:
        stats_command(log_dir, config, now, args.output_format)
        return

    if args.list_tags:
        tags_command(db, args.output_format)
        return

    if args.search:
        search_command(db, log_dir, config, args.search, args.output_format)
        return

    if args.list_todos:
        list_todos_command(db, log_dir, config, args.output_format)
        return

    # args.todo with nargs="*" returns:
    # - None if --todo flag not provided
    # - [] (empty list) if --todo provided without arguments
    # - ["text", "here"] if --todo provided with arguments
    if args.todo is not None:
        has_todo_text = bool(args.todo)

        if has_todo_text:
            todo_command(args, config, config_dir, log_dir, now, db)
        elif args.search:
            combined_query = f"{args.search} #todo"
            print(f"Filtering todos: {combined_query}\n")
            search_command(db, log_dir, config, combined_query, args.output_format)
        else:
            list_todos_command(db, log_dir, config, args.output_format)
            print("\nTo create a new todo: kaydet --todo \"your task description\"")
            print("To filter todos: kaydet --todo --search \"#valocom priority:high\"")
        return

    if args.done is not None:
        done_command(db, log_dir, config, args.done, now)
        return

    if args.edit is not None and args.delete is not None:
        print("Use either --edit or --delete, not both.")
        return
    if args.edit is not None:
        edit_entry_command(db, log_dir, config, args.edit, now)
        return
    if args.delete is not None:
        delete_entry_command(
            db,
            log_dir,
            config,
            args.delete,
            assume_yes=args.assume_yes,
            now=now,
        )
        return

    add_entry_command(
        args, config, config_dir, log_dir, now, db
    )
