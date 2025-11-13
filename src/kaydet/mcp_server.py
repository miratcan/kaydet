"""MCP (Model Context Protocol) server for Kaydet diary application.

This module provides an MCP server that exposes Kaydet's functionality
to AI assistants and other MCP-compatible tools.

Install with: pip install kaydet[mcp]
Run with: kaydet-mcp
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import sys

from . import database
from .cli import INDEX_FILENAME
from .commands.add import EmptyEntryError, create_entry
from .commands.delete import delete_entry_command
from .commands.edit import update_entry_inline
from .commands.search import (
    build_search_query,
    load_matches,
    tokenize_query,
)
from .commands.stats import collect_month_counts
from .commands.todo import done_command
from .indexing import rebuild_index_if_empty
from .parsers import parse_day_entries, resolve_entry_date
from .sync import sync_modified_diary_files
from .utils import load_config


class MissingMCPDependencyError(RuntimeError):
    """Raised when the optional MCP dependency is missing."""


Server: Any | None = None
stdio_server: Any | None = None
TextContent: Any | None = None
Tool: Any | None = None


def _load_mcp_dependencies():
    """Return MCP objects or raise a helpful error if missing."""

    global Server, stdio_server, TextContent, Tool
    if all(symbol is not None for symbol in (Server, stdio_server, TextContent, Tool)):
        return Server, stdio_server, TextContent, Tool

    try:
        from mcp.server import Server as MCPServer
        from mcp.server.stdio import stdio_server as MCPStdio
        from mcp.types import TextContent as MCPTextContent, Tool as MCPTool
    except ModuleNotFoundError as error:  # pragma: no cover - import guard
        raise MissingMCPDependencyError(
            (
                "kaydet-mcp requires the optional 'mcp' dependency. "
                "Install it via `pip install 'kaydet[mcp]'` or the "
                "GitHub equivalent `pip install \"git+https://github.com/"
                "miratcan/kaydet.git#egg=kaydet[mcp]\"`."
            )
        ) from error
    Server = MCPServer
    stdio_server = MCPStdio
    TextContent = MCPTextContent
    Tool = MCPTool
    return Server, stdio_server, TextContent, Tool


@dataclass
class KaydetService:
    """Programmatic interface over Kaydet command logic."""

    config: Any
    config_dir: Path
    log_dir: Path
    conn: Any

    @classmethod
    def initialize(cls) -> "KaydetService":
        (
            config,
            _config_path,
            config_dir,
            storage_dir,
            index_dir,
        ) = load_config()
        db_path = index_dir / INDEX_FILENAME
        conn = database.get_db_connection(db_path)
        database.initialize_database(conn)
        return cls(
            config=config,
            config_dir=config_dir,
            log_dir=storage_dir,
            conn=conn,
        )

    def _ensure_index(self, now: datetime) -> None:
        sync_modified_diary_files(self.conn, self.log_dir, self.config, now)
        rebuild_index_if_empty(self.conn, self.log_dir, self.config, now)

    def add_entry(
        self,
        *,
        text: str,
        metadata: dict[str, str] | None = None,
        tags: Iterable[str] | None = None,
        timestamp: str | None = None,
    ) -> dict[str, Any]:
        now = datetime.now()
        metadata = metadata or {}
        tags = list(tags or [])
        if timestamp:
            now = now.replace(
                hour=int(timestamp[:2]),
                minute=int(timestamp[3:]),
            )

        try:
            result = create_entry(
                raw_entry=text,
                metadata=metadata,
                explicit_tags=tags,
                config=self.config,
                config_dir=self.config_dir,
                log_dir=self.log_dir,
                now=now,
                conn=self.conn,
            )
        except EmptyEntryError as error:
            return {"success": False, "error": str(error)}
        return {"success": True, **result}

    def delete_entry(self, entry_id: int) -> dict[str, Any]:
        now = datetime.now()
        result = delete_entry_command(
            self.conn,
            self.log_dir,
            self.config,
            entry_id,
            assume_yes=True,
            now=now,
        )
        if result is None:
            return {"success": False, "error": "Entry not deleted."}
        return {"success": True, **result}

    def update_entry(
        self,
        entry_id: int,
        *,
        text: str | None = None,
        metadata: dict[str, str] | None = None,
        tags: Iterable[str] | None = None,
        timestamp: str | None = None,
    ) -> dict[str, Any]:
        now = datetime.now()
        result = update_entry_inline(
            self.conn,
            self.log_dir,
            self.config,
            entry_id,
            text=text,
            metadata=metadata,
            tags=tags,
            timestamp=timestamp,
            now=now,
        )
        if result is None:
            return {"success": False, "error": "Entry not updated."}
        return {"success": True, **result}

    def search_entries(self, query: str) -> dict[str, Any]:
        now = datetime.now()
        self._ensure_index(now)

        (
            include_text,
            exclude_text,
            include_meta,
            exclude_meta,
            include_tags,
            exclude_tags,
        ) = tokenize_query(query)

        if not any([include_text, exclude_text, include_meta, exclude_meta, include_tags, exclude_tags]):
            return {"success": False, "error": "Search query is empty."}

        sql_query, params = build_search_query(
            include_text,
            exclude_text,
            include_meta,
            exclude_meta,
            include_tags,
            exclude_tags,
        )
        cursor = self.conn.cursor()
        try:
            cursor.execute(sql_query, params)
        except Exception as error:  # pragma: no cover - sqlite errors rare
            return {
                "success": False,
                "error": f"Database query failed: {error}",
            }
        locations = cursor.fetchall()
        if not locations:
            return {"success": True, "query": query, "matches": [], "total": 0}

        matches = load_matches(locations, self.log_dir, self.config)
        matches.sort(
            key=lambda entry: int(entry.entry_id or 0),
            reverse=True,
        )
        payload = [match.to_dict() for match in matches]
        return {
            "success": True,
            "query": query,
            "matches": payload,
            "total": len(payload),
        }

    def list_tags(self) -> dict[str, Any]:
        cursor = self.conn.cursor()
        cursor.execute(
            (
                "SELECT tag_name, COUNT(*) "
                "FROM tags "
                "GROUP BY tag_name "
                "ORDER BY tag_name"
            )
        )
        rows = cursor.fetchall()
        tags = [
            {"tag": name, "count": count}
            for name, count in rows
        ]
        return {"success": True, "tags": tags}

    @staticmethod
    def _normalize_directory_tag(name: str) -> str:
        """Normalize a directory name into a tag-friendly slug."""
        slug = re.sub(r"[^a-z0-9\-]+", "-", name.lower())
        return slug.strip("-")

    def suggest_tags(self, directory: Path | str | None = None) -> dict[str, Any]:
        """Suggest tags based on the active project directory."""
        inspected_dir = (
            Path(directory).expanduser()
            if directory is not None
            else Path.cwd()
        )

        if not inspected_dir.exists():
            return {
                "success": False,
                "error": f"Directory does not exist: {inspected_dir}",
            }
        if not inspected_dir.is_dir():
            return {
                "success": False,
                "error": f"Not a directory: {inspected_dir}",
            }

        tags_file = inspected_dir / ".kaydet.tags"
        if tags_file.is_file():
            try:
                lines = tags_file.read_text(encoding="utf-8").splitlines()
            except OSError as error:  # pragma: no cover - filesystem edge case
                return {
                    "success": False,
                    "error": f"Failed to read {tags_file}: {error}",
                }
            tags = [
                line.strip()
                for line in lines
                if line.strip() and not line.strip().startswith("#")
            ]
            if tags:
                return {
                    "success": True,
                    "suggested_tags": tags,
                    "source": "tags_file",
                    "directory": str(inspected_dir),
                }

        normalized = self._normalize_directory_tag(inspected_dir.name)
        if not normalized:
            return {
                "success": False,
                "error": (
                    "Unable to derive tag suggestion from directory name. "
                    "Create a .kaydet.tags file to define tags explicitly."
                ),
            }
        return {
            "success": True,
            "suggested_tags": [normalized],
            "source": "directory_name",
            "directory": str(inspected_dir),
        }

    def get_stats(
        self, *, year: int | None = None, month: int | None = None
    ) -> dict[str, Any]:
        now = datetime.now()
        target_year = year or now.year
        target_month = month or now.month
        counts = collect_month_counts(
            self.log_dir,
            self.config,
            target_year,
            target_month,
        )
        total = sum(counts.values())
        return {
            "success": True,
            "year": target_year,
            "month": target_month,
            "days": counts,
            "total_entries": total,
        }

    def list_recent_entries(self, limit: int = 10) -> dict[str, Any]:
        now = datetime.now()
        self._ensure_index(now)
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT source_file, id FROM entries ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        locations = cursor.fetchall()
        if not locations:
            return {"success": True, "entries": []}
        matches = load_matches(locations, self.log_dir, self.config)
        matches.sort(
            key=lambda entry: int(entry.entry_id or 0),
            reverse=True,
        )
        payload = [match.to_dict() for match in matches]
        return {"success": True, "entries": payload}

    def entries_by_tag(self, tag: str, limit: int = 10) -> dict[str, Any]:
        now = datetime.now()
        self._ensure_index(now)
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT e.source_file, e.id
            FROM entries e
            JOIN tags t ON e.id = t.entry_id
            WHERE t.tag_name = ?
            ORDER BY e.id DESC
            LIMIT ?
            """,
            (tag, limit),
        )
        locations = cursor.fetchall()
        if not locations:
            return {"success": True, "entries": []}
        matches = load_matches(locations, self.log_dir, self.config)
        payload = [match.to_dict() for match in matches]
        return {"success": True, "entries": payload}

    def create_todo(
        self, description: str, metadata: dict[str, str] | None = None
    ) -> dict[str, Any]:
        """Create a new todo entry with status:pending and #todo tag."""
        now = datetime.now()
        metadata = metadata or {}
        metadata["status"] = "pending"

        try:
            result = create_entry(
                raw_entry=description,
                metadata=metadata,
                explicit_tags=["todo"],
                config=self.config,
                config_dir=self.config_dir,
                log_dir=self.log_dir,
                now=now,
                conn=self.conn,
            )
        except EmptyEntryError as error:
            return {"success": False, "error": str(error)}
        return {"success": True, **result}

    def mark_todo_done(self, entry_id: int) -> dict[str, Any]:
        """Mark a todo entry as done by updating its status."""
        now = datetime.now()
        try:
            done_command(
                self.conn,
                self.log_dir,
                self.config,
                entry_id,
                now,
            )
            return {
                "success": True,
                "entry_id": entry_id,
                "message": f"Todo {entry_id} marked as done",
            }
        except Exception as error:
            return {"success": False, "error": str(error)}

    def list_todos(self) -> dict[str, Any]:
        """List all todos with their status."""
        now = datetime.now()
        self._ensure_index(now)

        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT DISTINCT e.id, e.source_file "
            "FROM entries e "
            "JOIN tags t ON e.id = t.entry_id "
            "WHERE t.tag_name = 'todo' "
            "ORDER BY e.source_file, e.id"
        )
        results = cursor.fetchall()

        if not results:
            return {"success": True, "todos": []}

        todos = []
        for entry_id, source_file in results:
            day_file = self.log_dir / source_file
            if not day_file.exists():
                continue

            day_file_pattern = self.config.get("DAY_FILE_PATTERN", "")
            entry_date = resolve_entry_date(day_file, day_file_pattern)
            entries = parse_day_entries(day_file, entry_date)

            for entry in entries:
                if entry.entry_id == str(entry_id):
                    status = entry.metadata.get("status", "pending")
                    completed_at = entry.metadata.get("completed_at", "")
                    description = (
                        entry.lines[0] if entry.lines else "(no description)"
                    )

                    date_str = (
                        entry.day.isoformat() if entry.day else "unknown"
                    )
                    todos.append(
                        {
                            "id": entry_id,
                            "date": date_str,
                            "timestamp": entry.timestamp,
                            "status": status,
                            "completed_at": completed_at,
                            "description": description,
                        }
                    )
                    break

        return {"success": True, "todos": todos}


async def serve() -> None:
    """Start the MCP server."""

    Server, stdio_server, TextContent, Tool = _load_mcp_dependencies()
    service = KaydetService.initialize()
    server = Server("kaydet")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        """List available Kaydet tools."""
        return [
            Tool(
                name="add_entry",
                description="Add a new diary entry",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                        "metadata": {
                            "type": "object",
                            "additionalProperties": {"type": "string"},
                        },
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "timestamp": {
                            "type": "string",
                            "pattern": "^\\d{2}:\\d{2}$",
                        },
                    },
                    "required": ["text"],
                },
            ),
            Tool(
                name="update_entry",
                description=(
                    "Update an existing entry without opening an editor"
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "entry_id": {"type": "integer"},
                        "text": {"type": "string"},
                        "metadata": {
                            "type": "object",
                            "additionalProperties": {"type": "string"},
                        },
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "timestamp": {
                            "type": "string",
                            "pattern": "^\\d{2}:\\d{2}$",
                        },
                    },
                    "required": ["entry_id"],
                },
            ),
            Tool(
                name="delete_entry",
                description="Delete an entry by numeric identifier",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "entry_id": {"type": "integer"},
                    },
                    "required": ["entry_id"],
                },
            ),
            Tool(
                name="search_entries",
                description="Search diary entries",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                    },
                    "required": ["query"],
                },
            ),
            Tool(
                name="list_recent_entries",
                description="List the most recent entries",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "minimum": 1},
                    },
                },
            ),
            Tool(
                name="entries_by_tag",
                description="List recent entries for a tag",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "tag": {"type": "string"},
                        "limit": {"type": "integer", "minimum": 1},
                    },
                    "required": ["tag"],
                },
            ),
            Tool(
                name="list_tags",
                description="List all tags with counts",
                inputSchema={
                    "type": "object",
                    "properties": {},
                },
            ),
            Tool(
                name="suggest_kaydet_tags",
                description="Suggest project tags based on the current directory",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": (
                                "Directory to inspect. Defaults to the current "
                                "working directory."
                            ),
                        },
                    },
                },
            ),
            Tool(
                name="get_stats",
                description="Get entry counts for a given month",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "year": {"type": "integer", "minimum": 1900},
                        "month": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 12,
                        },
                    },
                },
            ),
            Tool(
                name="create_todo",
                description="Create a new todo entry with status:pending",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "description": {"type": "string"},
                        "metadata": {
                            "type": "object",
                            "additionalProperties": {"type": "string"},
                        },
                    },
                    "required": ["description"],
                },
            ),
            Tool(
                name="mark_todo_done",
                description="Mark a todo entry as done",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "entry_id": {"type": "integer"},
                    },
                    "required": ["entry_id"],
                },
            ),
            Tool(
                name="list_todos",
                description="List all todos with their status",
                inputSchema={
                    "type": "object",
                    "properties": {},
                },
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: Any) -> list[TextContent]:
        """Handle tool calls."""
        def error_response(message: str) -> list[TextContent]:
            return [
                TextContent(
                    type="text",
                    text=json.dumps(
                        {"success": False, "error": message}
                    ),
                )
            ]

        if name == "add_entry":
            text = arguments.get("text", "")
            if not text:
                return error_response("Entry text is required")
            result = service.add_entry(
                text=text,
                metadata=arguments.get("metadata"),
                tags=arguments.get("tags"),
                timestamp=arguments.get("timestamp"),
            )
            return [TextContent(type="text", text=json.dumps(result))]

        if name == "update_entry":
            entry_id = arguments.get("entry_id")
            if entry_id is None:
                return error_response("entry_id is required")
            result = service.update_entry(
                entry_id,
                text=arguments.get("text"),
                metadata=arguments.get("metadata"),
                tags=arguments.get("tags"),
                timestamp=arguments.get("timestamp"),
            )
            return [TextContent(type="text", text=json.dumps(result))]

        if name == "delete_entry":
            entry_id = arguments.get("entry_id")
            if entry_id is None:
                return error_response("entry_id is required")
            result = service.delete_entry(entry_id)
            return [TextContent(type="text", text=json.dumps(result))]

        if name == "search_entries":
            query = arguments.get("query", "")
            if not query:
                return error_response("Search query is required")
            result = service.search_entries(query)
            return [TextContent(type="text", text=json.dumps(result))]

        if name == "list_recent_entries":
            limit = arguments.get("limit", 10)
            result = service.list_recent_entries(limit=limit)
            return [TextContent(type="text", text=json.dumps(result))]

        if name == "entries_by_tag":
            tag = arguments.get("tag")
            if not tag:
                return error_response("tag is required")
            limit = arguments.get("limit", 10)
            result = service.entries_by_tag(tag, limit=limit)
            return [TextContent(type="text", text=json.dumps(result))]

        if name == "list_tags":
            result = service.list_tags()
            return [TextContent(type="text", text=json.dumps(result))]

        if name == "suggest_kaydet_tags":
            result = service.suggest_tags(directory=arguments.get("path"))
            return [TextContent(type="text", text=json.dumps(result))]

        if name == "get_stats":
            result = service.get_stats(
                year=arguments.get("year"),
                month=arguments.get("month"),
            )
            return [TextContent(type="text", text=json.dumps(result))]

        if name == "create_todo":
            description = arguments.get("description", "")
            if not description:
                return error_response("Todo description is required")
            result = service.create_todo(
                description=description,
                metadata=arguments.get("metadata"),
            )
            return [TextContent(type="text", text=json.dumps(result))]

        if name == "mark_todo_done":
            entry_id = arguments.get("entry_id")
            if entry_id is None:
                return error_response("entry_id is required")
            result = service.mark_todo_done(entry_id)
            return [TextContent(type="text", text=json.dumps(result))]

        if name == "list_todos":
            result = service.list_todos()
            return [TextContent(type="text", text=json.dumps(result))]

        return error_response(f"Unknown tool: {name}")

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream, write_stream, server.create_initialization_options()
        )


def main() -> None:
    """Entry point for the MCP server."""
    import asyncio

    try:
        asyncio.run(serve())
    except MissingMCPDependencyError as error:
        print(error, file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
