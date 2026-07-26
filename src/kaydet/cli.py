"Command-line interface for the kaydet diary application."

from __future__ import annotations

import argparse
import subprocess  # Used by tests  # noqa: F401
from datetime import datetime, timedelta
from pathlib import Path
from textwrap import dedent

from rich.console import Console

from . import __description__, __version__
from .cli_printers import print_doctor, print_stats, print_tags
from .commands.reminder import reminder_command
from .commands.search import print_matches, print_no_matches
from .json_output import print_json_err, print_json_ok
from .parsers import extract_tags_from_text  # noqa: F401
from .service import KaydetService
from .startfile import startfile
from .sums import format_sums_payload, print_sums
from .utils import (
    DEFAULT_SETTINGS,  # noqa: F401
    load_config,
    migrate_storage,
    open_file_in_editor,
)


def build_parser(
    config_path: Path, storage_path: Path
) -> argparse.ArgumentParser:
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
              (Change via config.ini → STORAGE_DIR;
               Kaydet will move files for you)
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
    basic_group.add_argument(
        "--attach",
        dest="attach",
        action="append",
        metavar="FILE",
        help="Attach file(s) to the entry (repeatable).",
    )
    basic_group.add_argument(
        "--grab",
        dest="grab",
        action="append",
        metavar="FILE",
        help="Attach file(s) and remove the originals (repeatable).",
    )

    # Todo Management
    todo_group = parser.add_argument_group("Todo Management")
    todo_group.add_argument(
        "--todo",
        dest="todo",
        nargs="*",
        metavar="TEXT",
        help=(
            "With text: create a todo (#todo, status:pending). "
            "Without text: shortcut for --filter '#todo' "
            "(same search UI, full entry body). "
            "Combine with --filter: "
            "'kaydet --todo --filter \"#work\"' → '#work #todo'."
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
    date_window = query_group.add_mutually_exclusive_group()
    date_window.add_argument(
        "--today",
        dest="today",
        action="store_true",
        help="List today's entries only (shorthand for since:YYYY-MM-DD).",
    )
    date_window.add_argument(
        "--week",
        dest="week",
        action="store_true",
        help=(
            "List this week's entries (since Monday of the current "
            "ISO week; shorthand for since:YYYY-MM-DD)."
        ),
    )
    date_window.add_argument(
        "--month",
        dest="month",
        action="store_true",
        help=(
            "List this month's entries (since the 1st; "
            "shorthand for since:YYYY-MM-01)."
        ),
    )
    query_group.add_argument(
        "--get",
        dest="get",
        type=int,
        metavar="ID",
        help="Show a single entry by its numeric identifier.",
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
        "--sum",
        dest="summarize",
        action="store_true",
        help="Show summed numeric metadata for matching entries.",
    )
    query_group.add_argument(
        "--limit",
        dest="limit",
        type=int,
        metavar="N",
        default=None,
        help=(
            "Show at most N most recent matching entries "
            "(0 = unlimited). Useful for large result sets."
        ),
    )

    # Sync
    sync_group = parser.add_argument_group("Sync")
    sync_group.add_argument(
        "--init",
        dest="git_init",
        type=str,
        nargs="?",
        const="",
        metavar="REMOTE_URL",
        help=(
            "Initialize git repo in storage directory. "
            "Optionally add remote URL."
        ),
    )
    sync_group.add_argument(
        "--sync",
        dest="git_sync",
        action="store_true",
        help="Commit all changes, push, and pull.",
    )
    sync_group.add_argument(
        "--status",
        dest="git_status",
        action="store_true",
        help="Show working tree status.",
    )

    # Management
    management_group = parser.add_argument_group("Management")
    management_group.add_argument(
        "--doctor",
        dest="doctor",
        action="store_true",
        help="Rebuild search index.",
    )
    management_group.add_argument(
        "--edit",
        dest="edit",
        nargs="+",
        metavar="ARG",
        help=(
            "Edit an entry: --edit ID opens editor, "
            '--edit ID "new text" updates inline.'
        ),
    )
    management_group.add_argument(
        "--delete",
        dest="delete",
        type=int,
        nargs="+",
        metavar="ID",
        help=(
            "Delete entries by numeric identifier(s) "
            "(e.g., --delete 31 32 33)."
        ),
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


def _handle_search_result(
    res: dict,
    *,
    query: str,
    args: argparse.Namespace,
    config: object,
    console: Console,
    default_since_hint: str | None = None,
) -> None:
    """Render a service.query() result for CLI."""
    if not res.get("success", False):
        error = res.get("error", "Search failed")
        if args.output_format == "json":
            print_json_err(error)
        else:
            print(error)
        return

    if args.summarize:
        if res["matches"]:
            payload = format_sums_payload(res["matches"])
            if args.output_format == "json":
                print_json_ok(
                    {
                        "query": query,
                        "total": payload["total_entries"],
                        "sums": payload["sums"],
                        "sums_display": payload["sums_display"],
                    }
                )
            else:
                print_sums(res["matches"])
        else:
            if args.output_format == "json":
                print_json_err("No numeric values found to sum")
            else:
                print("\U0001f50d No numeric values found to sum")
        return

    if not res["matches"] and args.output_format != "json":
        print_no_matches(
            query,
            metadata_filters=res.get("metadata_filters"),
            default_since_hint=default_since_hint,
        )
        return

    print_matches(
        res["matches"],
        query,
        args.output_format,
        config,
        console=console,
        default_since_hint=default_since_hint,
        metadata_filters=res.get("metadata_filters"),
        total=res.get("total"),
        limit=res.get("limit"),
    )


def main() -> None:
    """Application entry point for the kaydet CLI."""
    service = KaydetService.initialize()
    config = service.config
    config_path = service.config_path
    config_dir = service.config_dir
    storage_dir = service.log_dir

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
        old_storage_dir = storage_dir
        open_file_in_editor(config_path, config["EDITOR"])
        _new_config, _, _, new_storage_dir, _ = load_config()
        if old_storage_dir != new_storage_dir:
            print("\nStorage path changed:")
            print(f"  Old: {old_storage_dir}")
            print(f"  New: {new_storage_dir}")
            try:
                response = (
                    input("\nMove files to new location? [y/N]: ")
                    .strip()
                    .lower()
                )
                if response == "y":
                    migrate_storage(old_storage_dir, new_storage_dir)
                else:
                    print(
                        "\n⚠️  Files not moved. "
                        "You may need to move them manually."
                    )
            except (EOFError, KeyboardInterrupt):
                print(
                    "\n\n⚠️  Files not moved. "
                    "You may need to move them manually."
                )
        else:
            print("\n\u2705 Configuration saved")
        return

    if args.doctor:
        if args.output_format != "json":
            print(
                "Rebuilding search index from diary files..."
                " This may take a moment."
            )
        print_doctor(service.doctor(now=now), args.output_format)
        return

    if args.git_init is not None:
        remote = args.git_init if args.git_init else None
        res = service.git_init(remote_url=remote)
        print(res["message"])
        return

    if args.git_sync:
        res = service.git_sync()
        print(res["message"])
        return

    if args.git_status:
        res = service.git_status()
        print(res["message"])
        return

    # Ensure index is warm for remaining commands
    service._ensure_index(now)

    if args.stats:
        print_stats(
            service.monthly_stats(now=now),
            args.output_format,
        )
        return

    if args.list_tags:
        print_tags(service.tags(), args.output_format)
        return

    if args.get is not None:
        res = service.load_entry(args.get)
        if not res.get("success"):
            msg = f"\U0001f937 Entry {args.get} not found"
            if args.output_format == "json":
                print_json_err(f"Entry {args.get} not found")
            else:
                print(msg)
            return
        print_matches(
            res["matches"],
            f"id:{args.get}",
            args.output_format,
            config,
            console=console,
        )
        return

    # args.todo with nargs="*" returns:
    # - None if --todo flag not provided
    # - [] if --todo with no arguments → list via --filter '#todo'
    # - ["text", ...] if creating a todo
    if args.todo is not None:
        if args.todo:
            res = service.create_todo_from_cli(list(args.todo), now=now)
            if "message" in res:
                print(res["message"])
            return
        # Bare --todo is only a shortcut for filter '#todo' (no special UI)
        if args.filter:
            args.filter = f"{args.filter} #todo"
        else:
            args.filter = "#todo"

    if args.done is not None:
        for entry_id in args.done:
            res = service.mark_todo_done(entry_id)
            if "message" in res:
                print(res["message"])
        return

    # Date shorthands: inject since: and enable list mode
    since_date = None
    if args.today:
        since_date = now.date()
    elif args.week:
        # Monday of the current ISO week
        since_date = now.date() - timedelta(days=now.date().weekday())
    elif args.month:
        since_date = now.date().replace(day=1)

    if since_date is not None:
        since_token = f"since:{since_date.isoformat()}"
        if args.filter:
            args.filter = f"{args.filter} {since_token}"
        else:
            args.filter = since_token
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

        search_limit = None if args.summarize else args.limit
        res = service.query(
            query,
            allow_empty=True,
            limit=search_limit,
            now=now,
        )
        _handle_search_result(
            res,
            query=query,
            args=args,
            config=config,
            console=console,
            default_since_hint=default_since_hint,
        )
        return

    # Handle standalone --filter (shorthand for --list --filter)
    if args.filter:
        search_limit = None if args.summarize else args.limit
        res = service.query(
            args.filter,
            limit=search_limit,
            now=now,
        )
        _handle_search_result(
            res,
            query=args.filter,
            args=args,
            config=config,
            console=console,
        )
        return

    if args.edit is not None and args.delete is not None:
        print("\U0001f937 Use either --edit or --delete, not both")
        return
    if args.edit is not None:
        try:
            edit_id = int(args.edit[0])
        except ValueError:
            print(f"\U0001f937 Invalid entry ID: {args.edit[0]}")
            return
        if len(args.edit) > 1:
            inline_text = " ".join(args.edit[1:])
            service.update_entry(edit_id, text=inline_text)
        else:
            service.edit_in_editor(edit_id, now=now)
        return
    if args.delete is not None:
        for entry_id in args.delete:
            res = service.delete_entry(
                entry_id, assume_yes=args.assume_yes
            )
            if res and "message" in res:
                print(res["message"])
            elif res and not res.get("success") and "error" in res:
                print(res["error"])
        return

    if args.summarize:
        res = service.query("", allow_empty=True, now=now)
        if res.get("success", False) and res["matches"]:
            print_sums(res["matches"])
        else:
            print("\U0001f50d No entries found to sum")
        return

    res = service.add_from_cli(args, now=now)
    if res and "message" in res:
        print(res["message"])
