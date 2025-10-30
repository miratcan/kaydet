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
    reminder_command,
    search_command,
    stats_command,
    tags_command,
    todo_command,
)
from .indexing import rebuild_index_if_empty
from .parsers import extract_tags_from_text  # noqa: F401
from .sync import sync_modified_diary_files
from rich.console import Console
from typing import Optional
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

    # Basic Commands
    basic_group = parser.add_argument_group("Basic Commands")
    basic_group.add_argument(
        "entry", type=str, nargs="*", metavar="Entry", help="Entry content."
    )
    basic_group.add_argument(
        "--editor",
        "-e",
        dest="use_editor",
        action="store_true",
        help="Force opening editor.",
    )
    basic_group.add_argument(
        "--folder",
        "-f",
        dest="open_folder",
        action="store_true",
        help="Open the log directory.",
    )
    basic_group.add_argument(
        "--reminder",
        dest="reminder",
        action="store_true",
        help="Show reminder if you haven't written in a while.",
    )

    # Todo Management
    todo_group = parser.add_argument_group("Todo Management")
    todo_group.add_argument(
        "--todo",
        dest="todo",
        nargs="*",
        metavar="TEXT",
        help="Create a new todo entry (e.g., 'kaydet --todo \"Buy groceries #home\"'). Use without arguments to list todos, or combine with --filter to narrow results (e.g., 'kaydet --todo --filter \"#work\"').",
    )
    todo_group.add_argument(
        "--done",
        dest="done",
        type=int,
        metavar="ID",
        help="Mark a todo as done by ID (e.g., 'kaydet --done 42').",
    )


    # Query & Browse
    query_group = parser.add_argument_group("Query & Browse")
    query_group.add_argument(
        "--list",
        dest="list_entries",
        action="store_true",
        help="List all entries. Use with --filter to narrow results.",
    )
    query_group.add_argument(
        "--filter",
        dest="filter",
        metavar="QUERY",
        help="Filter entries or todos by query.",
    )
    query_group.add_argument(
        "--tags", dest="list_tags", action="store_true", help="List all tags."
    )
    query_group.add_argument(
        "--stats",
        dest="stats",
        action="store_true",
        help="Show calendar stats.",
    )
    query_group.add_argument(
        "--browse",
        dest="browse",
        action="store_true",
        help="Open the interactive browser.",
    )

    # Management
    management_group = parser.add_argument_group("Management")
    management_group.add_argument(
        "--doctor", dest="doctor", action="store_true",
        help="Rebuild search index.",
    )
    management_group.add_argument(
        "--edit",
        dest="edit",
        type=int,
        metavar="ID",
        help="Edit an entry by numeric identifier.",
    )
    management_group.add_argument(
        "--delete",
        dest="delete",
        type=int,
        metavar="ID",
        help="Delete an entry by numeric identifier.",
    )
    management_group.add_argument(
        "--yes",
        dest="assume_yes",
        action="store_true",
        help="Automatically confirm prompts.",
    )

    # Global Options
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
    console = Console()

    if args.reminder:
        reminder_command(config_dir, log_dir, now)
        return
    if args.open_folder:
        startfile(str(log_dir))
        return

    db_path = log_dir / INDEX_FILENAME
    conn = database.get_db_connection(db_path)
    database.initialize_database(conn)

    if args.doctor:
        doctor_command(conn, log_dir, config, now)
        return

    sync_modified_diary_files(conn, log_dir, config, now)
    rebuild_index_if_empty(conn, log_dir, config, now)

    # TODO: I hated this, will be removed in future.
    if args.browse:
        browse_command(conn, log_dir, config)
        return

    if args.stats:
        stats_command(log_dir, config, now, args.output_format)
        return

    if args.list_tags:
        tags_command(conn, args.output_format)
        return



    # args.todo with nargs="*" returns:
    # - None if --todo flag not provided
    # - [] (empty list) if --todo provided without arguments
    # - ["text", "here"] if --todo provided with arguments
    # Check --todo BEFORE --filter to handle --todo --filter correctly
    if args.todo is not None:
        has_todo_text = bool(args.todo)

        if has_todo_text:
            todo_command(args, config, config_dir, log_dir, now, conn)
        elif args.filter:
            # Filter todos and display in todo format
            from .commands.search import build_search_query, load_matches
            from .parsers import tokenize_query

            combined_query = f"{args.filter} #todo"
            print(f"Filtering todos: {combined_query}\n")

            text_terms, metadata_filters, tag_filters = tokenize_query(
                combined_query
            )
            sql_query, params = build_search_query(
                text_terms, metadata_filters, tag_filters
            )

            cursor = conn.cursor()
            cursor.execute(sql_query, params)
            locations = cursor.fetchall()

            if not locations:
                print(f"No todos found matching '{args.filter}'.")
                return

            matches = load_matches(locations, log_dir, config)

            # Convert search results to todo format
            from .formatters import format_todo_results

            todos = []
            for match in matches:
                status = match.metadata.get("status", "pending")
                completed_at = match.metadata.get("completed_at", "")
                description = (
                    match.lines[0] if match.lines else "(no description)"
                )
                date_str = (
                    match.day.isoformat() if match.day else "unknown"
                )

                todos.append(
                    {
                        "id": int(match.entry_id) if match.entry_id else 0,
                        "date": date_str,
                        "timestamp": match.timestamp,
                        "status": status,
                        "completed_at": completed_at,
                        "description": description,
                    }
                )

            format_todo_results(todos, args.output_format, config=config, console=console)
        else:
            print(
                '\nTo create a new todo: kaydet --todo '
                '"your task description"'
            )
            print(
                'To filter todos: kaydet --todo --filter '
                '"#work priority:high"'
            )
        return

    if args.done is not None:
        done_command(conn, log_dir, config, args.done, now)
        return

    # Handle --list (with optional --filter)
    if args.list_entries:
        query = args.filter if args.filter else ""
        # allow_empty=True lets --list show all entries when no filter is provided
        search_command(conn, log_dir, config, query, args.output_format, console=console, allow_empty=True)
        return

    # Handle standalone --filter (shorthand for --list --filter)
    if args.filter:
        search_command(conn, log_dir, config, args.filter, args.output_format, console=console)
        return

    if args.edit is not None and args.delete is not None:
        print("Use either --edit or --delete, not both.")
        return
    if args.edit is not None:
        edit_entry_command(conn, log_dir, config, args.edit, now)
        return
    if args.delete is not None:
        delete_entry_command(
            conn,
            log_dir,
            config,
            args.delete,
            assume_yes=args.assume_yes,
            now=now,
        )
        return

    add_entry_command(
        args, config, config_dir, log_dir, now, conn
    )
