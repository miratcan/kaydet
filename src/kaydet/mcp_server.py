"""MCP (Model Context Protocol) server for Kaydet diary application.

This module provides an MCP server that exposes Kaydet's functionality
to AI assistants and other MCP-compatible tools.

Install with: pip install kaydet[mcp]
Run with: kaydet-mcp
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

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
from .indexing import rebuild_index_if_empty
from .sync import sync_modified_diary_files
from .utils import load_config

# Check if MCP is available
try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import TextContent, Tool

    MCP_AVAILABLE = True
except ImportError:  # pragma: no cover - dependency optional
    MCP_AVAILABLE = False


@dataclass
class KaydetService:
    """Programmatic interface over Kaydet command logic."""

    config: Any
    config_dir: Path
    log_dir: Path
    db: Any

    @classmethod
    def initialize(cls) -> "KaydetService":
        config, _config_path, config_dir, log_dir = load_config()
        db_path = log_dir / INDEX_FILENAME
        db = database.get_db_connection(db_path)
        database.initialize_database(db)
        return cls(
            config=config,
            config_dir=config_dir,
            log_dir=log_dir,
            db=db,
        )

    def _ensure_index(self, now: datetime) -> None:
        sync_modified_diary_files(self.db, self.log_dir, self.config, now)
        rebuild_index_if_empty(self.db, self.log_dir, self.config, now)

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
                db=self.db,
            )
        except EmptyEntryError as error:
            return {"success": False, "error": str(error)}
        return {"success": True, **result}

    def delete_entry(self, entry_id: int) -> dict[str, Any]:
        now = datetime.now()
        result = delete_entry_command(
            self.db,
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
            self.db,
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

        text_terms, metadata_filters, tag_filters = tokenize_query(query)
        if not any([text_terms, metadata_filters, tag_filters]):
            return {"success": False, "error": "Search query is empty."}

        sql_query, params = build_search_query(
            text_terms, metadata_filters, tag_filters
        )
        cursor = self.db.cursor()
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
        cursor = self.db.cursor()
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
        cursor = self.db.cursor()
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
        cursor = self.db.cursor()
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


async def serve() -> None:
    """Start the MCP server."""
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

        if name == "get_stats":
            result = service.get_stats(
                year=arguments.get("year"),
                month=arguments.get("month"),
            )
            return [TextContent(type="text", text=json.dumps(result))]

        return error_response(f"Unknown tool: {name}")

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream, write_stream, server.create_initialization_options()
        )


def main() -> None:
    """Entry point for the MCP server."""
    if not MCP_AVAILABLE:
        print(
            "Error: MCP dependencies not installed.\n"
            "Install with: pip install kaydet[mcp]",
            file=sys.stderr,
        )
        sys.exit(1)

    import asyncio

    asyncio.run(serve())


if __name__ == "__main__":
    main()
