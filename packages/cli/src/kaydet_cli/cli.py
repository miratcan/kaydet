"Command-line interface for kaydet."

from __future__ import annotations

import argparse
import subprocess  # Used by tests  # noqa: F401
from datetime import datetime
from pathlib import Path
from textwrap import dedent

from rich.console import Console

from kaydet_core import database
from kaydet_core.commands import (
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
from kaydet_core.database import INDEX_FILENAME, log_sync_action
from kaydet_core.indexing import rebuild_index_if_empty
from kaydet_core.parsers import (
    extract_tags_from_text,  # noqa: F401
)
from kaydet_core.sync import sync_modified_day_files
from kaydet_core.utils import (
    DEFAULT_SETTINGS,  # noqa: F401
    load_config,
    migrate_storage,
    open_file_in_editor,
)

from . import __description__, __version__
from .formatters import (
    SearchResult,
    format_search_results,
    format_todo_results,
)
from .startfile import startfile


def print_matches(
    matches,
    query: str,
    output_format: str,
    config,
    console=None,
    metadata_filters=None,
    default_since_hint=None,
) -> None:
    """Render matches as JSON or terminal-friendly listing."""
    import json
    import re
    import shutil

    if output_format == "json":
        print(
            json.dumps(
                {
                    "query": query,
                    "matches": [
                        match.to_dict() for match in matches
                    ],
                    "total": len(matches),
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return

    if not matches:
        return

    try:
        terminal_width = shutil.get_terminal_size().columns
    except OSError:
        terminal_width = 80

    search_results = [
        SearchResult(
            entry_id=match.entry_id,
            day=match.day,
            timestamp=match.timestamp,
            lines=match.lines,
            metadata=match.metadata,
            tags=match.tags,
            attachments=list(match.attachments),
        )
        for match in matches
    ]

    format_search_results(
        search_results, terminal_width, config, console
    )

    since_value = None
    until_value = None
    if metadata_filters:
        for key, value in metadata_filters:
            if key == "since":
                since_value = value
            elif key == "until":
                until_value = value

    entry_label = (
        "entry" if len(matches) == 1 else "entries"
    )

    display_query = query
    if "since:" in query:
        display_query = re.sub(
            r"\bsince:\S+\s*", "", query
        ).strip()
    if "until:" in query:
        display_query = re.sub(
            r"\buntil:\S+\s*", "", query
        ).strip()

    if display_query:
        status_msg = (
            f"\nListed {len(matches)} {entry_label}"
            f" containing {display_query}"
        )
    else:
        status_msg = (
            f"\nListed {len(matches)} {entry_label}"
        )

    has_since = since_value and since_value not in (
        "0",
        "all",
    )
    has_until = until_value and until_value not in (
        "0",
        "all",
    )

    if has_since and has_until:
        status_msg += (
            f" ({since_value} to {until_value})"
        )
    elif has_since:
        status_msg += f" (since {since_value})"
    elif has_until:
        status_msg += f" (until {until_value})"

    print(status_msg + ".")

    if has_since or has_until:
        if display_query:
            print(
                f"Use '{display_query} since:0' "
                f"to see all entries."
            )
        else:
            print("Use 'since:0' to see all entries.")

    if default_since_hint and not display_query:
        print(
            "Note: No filter provided, so showing "
            f"entries since {default_since_hint}. "
            "Use '--list --filter \"since:0\"' for the "
            "full archive (this may be very verbose)."
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
    basic_group.add_argument(
        "--secret",
        dest="secret",
        type=str,
        metavar="TEXT",
        help="Attach an encrypted secret to the entry.",
    )

    # Todo Management
    todo_group = parser.add_argument_group("Todo Management")
    todo_group.add_argument(
        "--todo",
        dest="todo",
        nargs="*",
        metavar="TEXT",
        help=(
            "Create a new todo entry "
            "(e.g., 'kaydet --todo \"Buy groceries #home\"'). "
            "Use without arguments to list todos, or combine "
            "with --filter to narrow results "
            "(e.g., 'kaydet --todo --filter \"#work\"')."
        ),
    )
    todo_group.add_argument(
        "--done",
        dest="done",
        type=str,
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
        "--get",
        dest="get",
        type=str,
        metavar="ID",
        help="Show a single entry by its identifier.",
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
        type=str,
        metavar="ID",
        help="Delete an entry by identifier.",
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


def _build_sync_parser() -> argparse.ArgumentParser:
    """Build parser for 'kaydet sync' subcommands."""
    parser = argparse.ArgumentParser(
        prog="kaydet sync",
        description="Sync entries with a remote server.",
    )
    sub = parser.add_subparsers(dest="sync_action")
    sub.add_parser("setup", help="Configure sync settings.")
    sub.add_parser("status", help="Show sync status.")
    sub.add_parser("devices", help="List registered devices.")
    return parser


def _build_server_parser() -> argparse.ArgumentParser:
    """Build parser for 'kaydet server' subcommands."""
    parser = argparse.ArgumentParser(
        prog="kaydet server",
        description="Server management commands.",
    )
    sub = parser.add_subparsers(dest="server_action")

    start_p = sub.add_parser(
        "start", help="Start the sync server."
    )
    start_p.add_argument(
        "--transport",
        choices=["stdin", "http"],
        default="stdin",
        help="Transport mode (default: stdin).",
    )
    start_p.add_argument(
        "--host",
        default="127.0.0.1",
        help="HTTP host to bind (default: 127.0.0.1).",
    )
    start_p.add_argument(
        "--port",
        type=int,
        default=8484,
        help="HTTP port (default: 8484).",
    )
    genkey_p = sub.add_parser(
        "generate-key", help="Generate an API key."
    )
    genkey_p.add_argument(
        "--name", required=True, help="Key name."
    )
    sub.add_parser(
        "list-keys", help="List all API keys."
    )
    revoke_p = sub.add_parser(
        "revoke-key", help="Revoke an API key."
    )
    revoke_p.add_argument(
        "name", help="Key name to revoke."
    )
    return parser


def main() -> None:
    """Application entry point for the kaydet CLI."""
    import sys as _sys

    config, config_path, config_dir, storage_dir, index_dir = load_config()

    # Intercept sync/server subcommands before main parser
    argv = _sys.argv[1:]
    if argv and argv[0] == "sync":
        args = _build_sync_parser().parse_args(argv[1:])
        console = Console()
        _handle_sync_command(
            args, config, config_dir, storage_dir, index_dir,
            console,
        )
        return
    if argv and argv[0] == "server":
        args = _build_server_parser().parse_args(argv[1:])
        console = Console()
        _handle_server_command(
            args, config, config_dir, storage_dir, index_dir,
            console,
        )
        return

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
        # Save old storage path
        old_storage_dir = storage_dir

        # Open config in editor
        open_file_in_editor(config_path, config["EDITOR"])

        # Reload config to check for changes
        new_config, _, _, new_storage_dir, _ = load_config()

        # Check if storage path changed
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
            print("\n✓ Configuration saved.")

        return

    from kaydet_core.service import KaydetService
    service = KaydetService.initialize()
    conn = service.conn

    if args.doctor:
        print(
            "Rebuilding search index from day files..."
            " This may take a moment."
        )
        from kaydet_cli.cli_printers import print_doctor

        print_doctor(doctor_command(conn, storage_dir, config, now, config_dir=config_dir))
        return

    sync_modified_day_files(conn, storage_dir, config, now, config_dir=config_dir)
    rebuild_index_if_empty(conn, storage_dir, config, now)

    if args.stats:
        from kaydet_cli.cli_printers import print_stats

        res = service.get_stats()
        print_stats(res, args.output_format)
        return

    if args.list_tags:
        from kaydet_cli.cli_printers import print_tags
        res = service.list_tags()
        print_tags(res.get("tags", []), args.output_format)
        return

    if args.get is not None:
        res = service.get_entry(args.get)
        if not res.get("success"):
            print(f"Entry {args.get} not found.")
            return
        entry = res["entry"]
        # Wrap in a list-like structure for print_matches
        from kaydet_core.models import Entry as CoreEntry
        from datetime import date as _date
        from pathlib import Path as _Path
        try:
            day = _date.fromisoformat(entry.get("date", ""))
        except ValueError:
            day = None
        fake_entry = CoreEntry(
            entry_id=entry["entry_id"],
            timestamp=entry.get("timestamp", ""),
            lines=tuple(entry.get("text", "").splitlines()),
            tags=tuple(entry.get("tags", [])),
            metadata=entry.get("metadata", {}),
            metadata_numbers={},
            source=_Path("."),
            day=day,
        )
        print_matches(
            [fake_entry],
            f"id:{args.get}",
            args.output_format,
            config,
            console=console,
        )
        if entry.get("secret"):
            console.print(f"\n[bold]Secret:[/bold] {entry['secret']}")
        elif entry.get("secret_error"):
            console.print(f"\n[red]Secret: {entry['secret_error']}[/red]")
        return

    # args.todo with nargs="*" returns:
    # - None if --todo flag not provided
    # - [] (empty list) if --todo provided without arguments
    # - ["text", "here"] if --todo provided with arguments
    # Check --todo BEFORE --filter to handle --todo --filter correctly
    if args.todo is not None:
        has_todo_text = bool(args.todo)

        if has_todo_text:
            description = " ".join(args.todo)
            res = service.create_todo(description=description)
            if res.get("entry_id"):
                log_sync_action(conn, res["entry_id"], "created")
            if res.get("success"):
                print(f"Todo added (ID: {res['entry_id']})")
            else:
                print(f"Error: {res.get('error')}")
        elif args.filter:
            # Filter todos and display in todo format
            res = service.list_todos(filter_query=args.filter)
            todos = res.get("todos", [])
            if not todos:
                print(f"No todos found matching '{args.filter}'.")
                return
            format_todo_results(
                todos, args.output_format, config=config, console=console
            )
        else:
            # kaydet --todo (no arguments) → list all pending todos
            res = service.list_todos(status="pending")
            todos = res.get("todos", [])
            if not todos:
                print("No pending todos.")
            else:
                format_todo_results(
                    todos,
                    args.output_format,
                    config=config,
                    console=console,
                )
        return

    if args.done is not None:
        for entry_id in args.done:
            res = service.mark_todo_done(entry_id)
            if "message" in res:
                print(res["message"])
            if res.get("success"):
                log_sync_action(conn, entry_id, "updated")
        return

    # Handle --today: add today's date as a since: filter
    if args.today:
        today_since = f"since:{now.date().isoformat()}"
        if args.filter:
            args.filter = f"{args.filter} {today_since}"
        else:
            args.filter = today_since
        if not args.list_entries:
            args.list_entries = True

    def _print_search_result(res, query, default_since_hint=None):
        if res.get("success"):
            matches = res.get("matches", [])
            if not matches:
                if query:
                    print(f"No entries matched '{query}'.")
            else:
                from kaydet_core.models import Entry as CoreEntry
                from datetime import date as _date
                from pathlib import Path as _Path
                fake_entries = []
                for m in matches:
                    try:
                        day = _date.fromisoformat(m.get("date", ""))
                    except ValueError:
                        day = None
                    fake_entries.append(CoreEntry(
                        entry_id=m["entry_id"],
                        timestamp=m.get("timestamp", ""),
                        lines=tuple(m.get("text", "").splitlines()),
                        tags=tuple(m.get("tags", [])),
                        metadata=m.get("metadata", {}),
                        metadata_numbers={},
                        source=_Path("."),
                        day=day,
                    ))
                print_matches(
                    fake_entries,
                    query,
                    args.output_format,
                    config,
                    console=console,
                    default_since_hint=default_since_hint,
                )
        elif "error" in res:
            print(res["error"])

    # Handle --list (with optional --filter)
    if args.list_entries:
        query = (args.filter or "").strip()
        default_since_hint = None
        if not query:
            month_start = now.replace(day=1).date().isoformat()
            query = f"since:{month_start}"
            default_since_hint = month_start
        res = service.search_entries(query, limit=0)
        _print_search_result(res, query, default_since_hint)
        return

    # Handle standalone --filter (shorthand for --list --filter)
    if args.filter:
        res = service.search_entries(args.filter)
        _print_search_result(res, args.filter)
        return

    if args.edit is not None and args.delete is not None:
        print("Use either --edit or --delete, not both.")
        return
    if args.edit is not None:
        edit_id = args.edit[0]
        if len(args.edit) > 1:
            inline_text = " ".join(args.edit[1:])
            res = service.update_entry(edit_id, text=inline_text)
        else:
            # Editor mode: still uses Python path (opens $EDITOR)
            edit_entry_command(conn, storage_dir, config, edit_id, now)
            res = {"success": True}
        if res.get("success"):
            log_sync_action(conn, edit_id, "updated")
        return
    if args.delete is not None:
        res = service.delete_entry(args.delete)
        if res.get("success"):
            log_sync_action(conn, args.delete, "deleted")
        elif "error" in res:
            print(res["error"])
        return

    res = add_entry_command(
        args, config, config_dir, storage_dir, now
    )
    if res and "message" in res:
        print(res["message"])
    if res and res.get("success") and res.get("entry_id"):
        log_sync_action(conn, res["entry_id"], "created")


def _handle_sync_command(
    args, config, config_dir, storage_dir, index_dir, console
):
    """Handle kaydet sync subcommands."""

    action = getattr(args, "sync_action", None)

    if action == "setup":
        _sync_setup(config, config_dir)
        return

    if action == "status":
        from kaydet_server.sync_client import SyncClient

        client = SyncClient.initialize()
        status = client.get_status()
        print(f"Transport: {status['transport']}")
        print(f"Server: {status['server'] or '(local)'}")
        print(f"Sync token: {status['sync_token']}")
        return

    if action == "devices":
        print("Device listing requires server connection.")
        return

    # Default: run sync
    from kaydet_server.sync_client import SyncClient

    client = SyncClient.initialize()
    print("Syncing...")
    result = client.sync()

    pull = result["pull"]
    push = result["push"]
    print(
        f"Pulled {pull['pulled']} entries "
        f"(token: {pull['new_token']})"
    )
    print(f"Pushed {push['pushed']} entries")
    if push.get("errors"):
        for err in push["errors"]:
            print(f"  Error: {err}")


def _sync_setup(config, config_dir):
    """Interactive sync setup."""
    from kaydet_core.utils import save_config_setting

    print("\nSync Setup")
    print("=" * 40)

    print("\nTransport options:")
    print("  1. stdin  (local server, same machine)")
    print("  2. http   (remote server)")

    choice = input("\nChoose transport [1]: ").strip()
    transport = "http" if choice == "2" else "stdin"

    save_config_setting(config_dir, "sync_transport", transport)

    if transport == "http":
        server = input("Server URL: ").strip()
        api_key = input("API key: ").strip()
        save_config_setting(config_dir, "sync_server", server)
        save_config_setting(config_dir, "sync_api_key", api_key)
    else:
        path = input(
            "Server binary path [kaydet]: "
        ).strip()
        save_config_setting(
            config_dir, "sync_server_path", path or "kaydet"
        )

    print("\nSync configured.")


def _handle_server_command(
    args, config, config_dir, storage_dir, index_dir, console
):
    """Handle kaydet server subcommands."""
    from kaydet_core import database

    db_path = Path(index_dir) / INDEX_FILENAME
    conn = database.get_db_connection(db_path)
    database.initialize_database(conn)

    action = getattr(args, "server_action", None)

    if action == "start":
        if args.transport == "http":
            _print_qr(conn, args.host, args.port)
            _start_http_server(
                conn,
                storage_dir,
                config,
                config_dir,
                args.host,
                args.port,
            )
        else:
            from kaydet_server.sync_server import run_stdin_server

            run_stdin_server()
        return

    if action == "generate-key":
        from kaydet_server.sync_server import generate_api_key

        key = generate_api_key(conn, args.name)
        print(f"API key generated: {key}")
        print(f"Name: {args.name}")
        print("\nStore this key securely. "
              "It won't be shown again.")
        return

    if action == "list-keys":
        from kaydet_server.sync_server import list_api_keys

        keys = list_api_keys(conn)
        if not keys:
            print("No API keys.")
            return
        for k in keys:
            used = k["last_used_at"] or "never"
            print(
                f"  {k['name']}: {k['key_prefix']} "
                f"(created: {k['created_at']}, "
                f"last used: {used})"
            )
        return

    if action == "revoke-key":
        from kaydet_server.sync_server import revoke_api_key

        if revoke_api_key(conn, args.name):
            print(f"Key '{args.name}' revoked.")
        else:
            print(f"Key '{args.name}' not found.")
        return

    print("Usage: kaydet server <start|generate-key"
          "|list-keys|revoke-key>")


def _print_qr(conn, host: str, port: int) -> None:
    """Print ASCII QR code for mobile pairing."""
    import qrcode
    import socket

    cursor = conn.cursor()
    cursor.execute("SELECT key FROM sync_keys LIMIT 1")
    row = cursor.fetchone()
    if not row:
        print("No API key found. Run: kaydet server generate-key --name <name>")
        return

    api_key = row[0]

    # Resolve actual LAN IP when binding to all interfaces
    qr_host = host
    if host in ("0.0.0.0", "::"):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            qr_host = s.getsockname()[0]
            s.close()
        except OSError:
            qr_host = "127.0.0.1"

    payload = f"kaydet://{api_key}@{qr_host}:{port}"

    qr = qrcode.QRCode(border=1)
    qr.add_data(payload)
    qr.make(fit=True)
    qr.print_ascii(invert=True)
    print(f"\nServer: http://{qr_host}:{port}")
    print(f"Scan with the kaydet mobile app to connect.\n")


def _start_http_server(
    conn, storage_dir, config, config_dir, host, port
):
    """Start the HTTP sync server."""
    from kaydet_server.http_server import start_http_server

    start_http_server(
        conn, storage_dir, config, config_dir, host, port
    )
