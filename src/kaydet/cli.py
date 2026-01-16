"Command-line interface for the kaydet diary application."

from __future__ import annotations

import argparse
import subprocess  # Used by tests  # noqa: F401
from datetime import datetime
from pathlib import Path
from textwrap import dedent

from rich.console import Console

from .startfile import startfile

from . import __description__, __version__, database
from .commands import (
    add_entry_command,
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
from .utils import DEFAULT_SETTINGS, load_config  # noqa: F401

INDEX_FILENAME = "index.db"


def build_parser(config_path: Path, storage_path: Path) -> argparse.ArgumentParser:
    """Create the kaydet CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="kaydet",
        description=__description__,
        epilog=dedent(
            f"""\
            Quick Start:
              kaydet 'Meeting with team #work time:2h'
              kaydet --editor
              kaydet --todo "Buy groceries #home"
              kaydet --filter "#work status:done"
              kaydet --list --today

            Documentation:
              Query syntax: docs/QUERY_SYNTAX.md
              Configuration: {config_path}
              Storage: {storage_path}
              (Change via config.ini → STORAGE_DIR; Kaydet will move files for you)
            """
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
    basic_group.add_argument(
        "--at",
        dest="at",
        type=str,
        help="Set a custom timestamp (YYYY-MM-DD:HH:MM or HH:MM).",
    )

    # Todo Management
    todo_group = parser.add_argument_group("Todo Management")
    todo_group.add_argument(
        "--todo",
        dest="todo",
        nargs="*",
        metavar="TEXT",
        help=(
            "Create a new todo entry (e.g., 'kaydet --todo \"Buy groceries #home\"'). "
            "Use without arguments to list todos, or combine with --filter to "
            "narrow results (e.g., 'kaydet --todo --filter \"#work\"')."
        ),
    )
    todo_group.add_argument(
        "--done",
        dest="done",
        type=int,
        nargs="+",
        metavar="ID",
        help="Mark todos as done by ID (e.g., 'kaydet --done 1 2 3').",
    )


    # Query commands
    query_group = parser.add_argument_group("Query")
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
        help=dedent("""\
            Filter entries or todos by query.

            Examples:
              kaydet --filter "#work status:done"
              kaydet --filter "meeting time:>2"
              kaydet --filter "#harcama miktar:100..500"
              kaydet --filter "#work -#urgent since:2025-01-01"

            Syntax:
              #tag          - Match tag
              key:value     - Match metadata
              key:>N        - Comparison (>, >=, <, <=)
              key:N..M      - Range
              key:*         - Wildcard
              -term         - Exclude
              since:DATE    - Date filter (YYYY-MM-DD)

            See docs/QUERY_SYNTAX.md for full documentation.
            """),
    )
    query_group.add_argument(
        "--today",
        dest="today",
        action="store_true",
        help="List today's entries only (shorthand for since:YYYY-MM-DD).",
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
    management_group.add_argument(
        "--config",
        dest="edit_config",
        action="store_true",
        help="Edit configuration file in your default editor.",
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
    config, config_path, config_dir, storage_dir, index_dir = load_config()
    parser = build_parser(config_path, storage_dir)
    args = parser.parse_args()

    now = datetime.now()
    console = Console()

    if args.reminder:
        reminder_command(config_dir, storage_dir, now)
        return
    if args.open_folder:
        startfile(str(storage_dir))
        return
    if args.edit_config:
        from .utils import open_file_in_editor, migrate_storage

        # Save old storage path
        old_storage_dir = storage_dir

        # Open config in editor
        open_file_in_editor(config_path, config["EDITOR"])

        # Reload config to check for changes
        new_config, _, _, new_storage_dir, _ = load_config()

        # Check if storage path changed
        if old_storage_dir != new_storage_dir:
            print(f"\nStorage path changed:")
            print(f"  Old: {old_storage_dir}")
            print(f"  New: {new_storage_dir}")

            try:
                response = input("\nMove files to new location? [y/N]: ").strip().lower()
                if response == 'y':
                    migrate_storage(old_storage_dir, new_storage_dir)
                else:
                    print("\n⚠️  Files not moved. You may need to move them manually.")
            except (EOFError, KeyboardInterrupt):
                print("\n\n⚠️  Files not moved. You may need to move them manually.")
        else:
            print("\n✓ Configuration saved.")

        return

    db_path = index_dir / INDEX_FILENAME
    conn = database.get_db_connection(db_path)
    database.initialize_database(conn)

    if args.doctor:
        doctor_command(conn, storage_dir, config, now)
        return

    sync_modified_diary_files(conn, storage_dir, config, now)
    rebuild_index_if_empty(conn, storage_dir, config, now)

    if args.stats:
        stats_command(storage_dir, config, now, args.output_format)
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
            todo_command(args, config, config_dir, storage_dir, now, conn)
        elif args.filter:
            # Filter todos and display in todo format
            from .commands.search import build_search_query, load_matches
            from .parsers import tokenize_query

            combined_query = f"{args.filter} #todo"
            print(f"Filtering todos: {combined_query}\n")

            (
                include_text,
                exclude_text,
                include_meta,
                exclude_meta,
                include_tags,
                exclude_tags,
            ) = tokenize_query(combined_query)

            sql_query, params = build_search_query(
                include_text,
                exclude_text,
                include_meta,
                exclude_meta,
                include_tags,
                exclude_tags,
            )

            cursor = conn.cursor()
            cursor.execute(sql_query, params)
            locations = cursor.fetchall()

            if not locations:
                print(f"No todos found matching '{args.filter}'.")
                return

            matches = load_matches(locations, storage_dir, config)

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

            format_todo_results(
                todos, args.output_format, config=config, console=console
            )
        else:
            # kaydet --todo (no arguments) → list all todos
            from .commands.todo import list_todos_command
            list_todos_command(conn, storage_dir, config, args.output_format, console)
        return

    if args.done is not None:
        for entry_id in args.done:
            done_command(conn, storage_dir, config, entry_id, now)
        return

    # Handle --today: add today's date as a since: filter
    if args.today:
        today_since = f"since:{now.date().isoformat()}"
        if args.filter:
            args.filter = f"{args.filter} {today_since}"
        else:
            args.filter = today_since
        # Enable list mode if not already set
        if not args.list_entries:
            args.list_entries = True

    # Handle --list (with optional --filter)
    if args.list_entries:
        query = (args.filter or "").strip()
        default_since_hint = None
        if not query:
            month_start = now.replace(day=1).date().isoformat()
            query = f"since:{month_start}"
            default_since_hint = month_start

        # allow_empty=True lets --list show all entries when no filter
        # is provided
        search_command(
            conn,
            storage_dir,
            config,
            query,
            args.output_format,
            console=console,
            allow_empty=True,
            default_since_hint=default_since_hint,
        )
        return

    # Handle standalone --filter (shorthand for --list --filter)
    if args.filter:
        search_command(
            conn, storage_dir, config, args.filter, args.output_format,
            console=console
        )
        return

    if args.edit is not None and args.delete is not None:
        print("Use either --edit or --delete, not both.")
        return
    if args.edit is not None:
        edit_entry_command(conn, storage_dir, config, args.edit, now)
        return
    if args.delete is not None:
        delete_entry_command(
            conn,
            storage_dir,
            config,
            args.delete,
            assume_yes=args.assume_yes,
            now=now,
        )
        return

    add_entry_command(
        args, config, config_dir, storage_dir, now, conn
    )
