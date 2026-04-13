"Command-line interface for the kaydet diary application."

from __future__ import annotations

import argparse
import subprocess  # Used by tests  # noqa: F401
from datetime import datetime
from pathlib import Path
from textwrap import dedent

from rich.console import Console

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
from .commands.edit import update_entry_inline
from .commands.search import (
    build_search_query,
    load_matches,
    print_matches,
)
from .commands.todo import list_todos_command
from .formatters import format_todo_results
from .indexing import rebuild_index_if_empty
from .parsers import (
    extract_tags_from_text,  # noqa: F401
    tokenize_query,
)
from .startfile import startfile
from .sync import sync_modified_diary_files
from .utils import (
    DEFAULT_SETTINGS,  # noqa: F401
    load_config,
    migrate_storage,
    open_file_in_editor,
)

INDEX_FILENAME = "index.db"


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

    db_path = index_dir / INDEX_FILENAME
    conn = database.get_db_connection(db_path)
    database.initialize_database(conn)

    if args.doctor:
        print(
            "Rebuilding search index from diary files..."
            " This may take a moment."
        )
        from kaydet.cli_printers import print_doctor

        print_doctor(doctor_command(conn, storage_dir, config, now))
        return

    sync_modified_diary_files(conn, storage_dir, config, now)
    rebuild_index_if_empty(conn, storage_dir, config, now)

    if args.stats:
        from kaydet.cli_printers import print_stats

        print_stats(
            stats_command(storage_dir, config, now),
            args.output_format,
        )
        return

    if args.list_tags:
        from kaydet.cli_printers import print_tags
        print_tags(tags_command(conn), args.output_format)
        return

    if args.get is not None:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT source_file FROM entries WHERE id = ?", (args.get,)
        )
        result = cursor.fetchone()
        if result is None:
            print(f"Entry {args.get} not found.")
            return
        locations = [(result[0], args.get)]
        matches = load_matches(locations, storage_dir, config)
        if not matches:
            print(f"Entry {args.get} not found.")
            return
        print_matches(
            matches,
            f"id:{args.get}",
            args.output_format,
            config,
            console=console,
        )
        # Show decrypted secret if one exists
        from .secrets import decrypt_secret, get_secret
        from .utils import get_secret_password

        encrypted = get_secret(conn, args.get)
        if encrypted:
            password = get_secret_password(config_dir)
            if password:
                try:
                    plaintext = decrypt_secret(encrypted, password)
                    console.print(
                        f"\n[bold]Secret:[/bold] {plaintext}"
                    )
                except Exception:
                    console.print(
                        "\n[red]Failed to decrypt secret."
                        " Wrong password?[/red]"
                    )
            else:
                console.print(
                    "\n[yellow]Entry has a secret but no password"
                    " is configured.[/yellow]"
                )
        return

    # args.todo with nargs="*" returns:
    # - None if --todo flag not provided
    # - [] (empty list) if --todo provided without arguments
    # - ["text", "here"] if --todo provided with arguments
    # Check --todo BEFORE --filter to handle --todo --filter correctly
    if args.todo is not None:
        has_todo_text = bool(args.todo)

        if has_todo_text:
            res = todo_command(
                args, config, config_dir, storage_dir, now, conn
            )
            if "message" in res:
                print(res["message"])
        elif args.filter:
            # Filter todos and display in todo format
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
            todos = []
            for match in matches:
                status = match.metadata.get("status", "pending")
                if status == "done":
                    continue
                completed_at = match.metadata.get("completed_at", "")
                description = (
                    match.lines[0] if match.lines else "(no description)"
                )
                date_str = match.day.isoformat() if match.day else "unknown"

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

            if not todos:
                print("No pending todos found matching the filter.")
                return

            format_todo_results(
                todos, args.output_format, config=config, console=console
            )
        else:
            # kaydet --todo (no arguments) → list all todos
            todos = list_todos_command(conn, storage_dir, config)
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
            res = done_command(
                conn, storage_dir, config, entry_id, now
            )
            if "message" in res:
                print(res["message"])
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
        res = search_command(
            conn, storage_dir, config, query, allow_empty=True
        )
        if res.get('success', False):
            if not res['matches'] and not query:
                pass
            elif not res['matches']:
                print(f"No entries matched '{query}'.")
            else:
                print_matches(
                    res['matches'],
                    query,
                    args.output_format,
                    config,
                    console=console,
                    default_since_hint=default_since_hint,
                    metadata_filters=res.get(
                        'metadata_filters'
                    ),
                )
        else:
            if 'error' in res:
                print(res['error'])
        return

    # Handle standalone --filter (shorthand for --list --filter)
    if args.filter:
        res = search_command(
            conn, storage_dir, config, args.filter
        )
        if res.get('success', False):
            if not res['matches']:
                print(
                    f"No entries matched '{args.filter}'."
                )
            else:
                print_matches(
                    res['matches'],
                    args.filter,
                    args.output_format,
                    config,
                    console=console,
                    metadata_filters=res.get(
                        'metadata_filters'
                    ),
                )
        else:
            if 'error' in res:
                print(res['error'])
        return

    if args.edit is not None and args.delete is not None:
        print("Use either --edit or --delete, not both.")
        return
    if args.edit is not None:
        try:
            edit_id = int(args.edit[0])
        except ValueError:
            print(f"Invalid entry ID: {args.edit[0]}")
            return
        if len(args.edit) > 1:
            # Inline update: --edit ID "new text"
            inline_text = " ".join(args.edit[1:])
            update_entry_inline(
                conn, storage_dir, config, edit_id, text=inline_text, now=now
            )
        else:
            # Editor mode: --edit ID
            edit_entry_command(conn, storage_dir, config, edit_id, now)
        return
    if args.delete is not None:
        res = delete_entry_command(
            conn,
            storage_dir,
            config,
            args.delete,
            assume_yes=args.assume_yes,
            now=now,
        )
        if res and "message" in res:
            print(res["message"])
        return

    res = add_entry_command(
        args, config, config_dir, storage_dir, now, conn
    )
    if res and "message" in res:
        print(res["message"])


def _handle_sync_command(
    args, config, config_dir, storage_dir, index_dir, console
):
    """Handle kaydet sync subcommands."""

    action = getattr(args, "sync_action", None)

    if action == "setup":
        _sync_setup(config, config_dir)
        return

    if action == "status":
        from .sync_client import SyncClient

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
    from .sync_client import SyncClient

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
    from configparser import ConfigParser

    print("\nSync Setup")
    print("=" * 40)

    print("\nTransport options:")
    print("  1. stdin  (local server, same machine)")
    print("  2. http   (remote server)")

    choice = input("\nChoose transport [1]: ").strip()
    transport = "http" if choice == "2" else "stdin"

    config_path = config_dir / "config.ini"
    parser = ConfigParser(interpolation=None)
    if config_path.exists():
        parser.read(config_path, encoding="utf-8")
    section = "SETTINGS"
    if section not in parser:
        parser[section] = {}

    parser[section]["sync_transport"] = transport

    if transport == "http":
        server = input("Server URL: ").strip()
        api_key = input("API key: ").strip()
        parser[section]["sync_server"] = server
        parser[section]["sync_api_key"] = api_key
    else:
        path = input(
            "Server binary path [kaydet]: "
        ).strip()
        parser[section]["sync_server_path"] = path or "kaydet"

    with config_path.open("w", encoding="utf-8") as f:
        parser.write(f)

    print("\nSync configured.")


def _handle_server_command(
    args, config, config_dir, storage_dir, index_dir, console
):
    """Handle kaydet server subcommands."""
    from . import database

    db_path = Path(index_dir) / INDEX_FILENAME
    conn = database.get_db_connection(db_path)
    database.initialize_database(conn)

    action = getattr(args, "server_action", None)

    if action == "start":
        if args.transport == "http":
            _start_http_server(
                conn,
                storage_dir,
                config,
                config_dir,
                args.host,
                args.port,
            )
        else:
            from .sync_server import run_stdin_server

            run_stdin_server()
        return

    if action == "generate-key":
        from .sync_server import generate_api_key

        key = generate_api_key(conn, args.name)
        print(f"API key generated: {key}")
        print(f"Name: {args.name}")
        print("\nStore this key securely. "
              "It won't be shown again.")
        return

    if action == "list-keys":
        from .sync_server import list_api_keys

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
        from .sync_server import revoke_api_key

        if revoke_api_key(conn, args.name):
            print(f"Key '{args.name}' revoked.")
        else:
            print(f"Key '{args.name}' not found.")
        return

    print("Usage: kaydet server <start|generate-key"
          "|list-keys|revoke-key>")


def _start_http_server(
    conn, storage_dir, config, config_dir, host, port
):
    """Start the HTTP sync server."""
    from http.server import BaseHTTPRequestHandler, HTTPServer

    from .service import KaydetService
    from .sync_protocol import (
        deserialize_message,
        serialize_message,
    )
    from .sync_server import SyncServer, validate_api_key

    svc = KaydetService(
        config=config, config_dir=config_dir,
        log_dir=storage_dir, conn=conn,
    )
    server_inst = SyncServer(svc)

    class SyncHandler(BaseHTTPRequestHandler):
        def do_POST(self):
            if self.path != "/sync":
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b"Not found")
                return

            # Auth check
            auth = self.headers.get("Authorization", "")
            if not auth.startswith("Bearer "):
                self.send_response(401)
                self.end_headers()
                self.wfile.write(b"Missing API key")
                return

            api_key = auth[7:]
            if not validate_api_key(conn, api_key):
                self.send_response(401)
                self.end_headers()
                self.wfile.write(b"Invalid API key")
                return

            length = int(
                self.headers.get("Content-Length", 0)
            )
            body = self.rfile.read(length).decode("utf-8")

            try:
                msg = deserialize_message(body)
                response = server_inst.handle_message(msg)
                resp_json = serialize_message(
                    response
                ).encode("utf-8")

                self.send_response(200)
                self.send_header(
                    "Content-Type", "application/json"
                )
                self.end_headers()
                self.wfile.write(resp_json)
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(str(e).encode("utf-8"))

        def log_message(self, format, *a):
            print(f"[sync] {self.address_string()} "
                  f"{format % a}")

    httpd = HTTPServer((host, port), SyncHandler)
    print(f"Sync server listening on {host}:{port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
