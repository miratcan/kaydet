"""MCP (Model Context Protocol) server for Kaydet.

This module provides an MCP server that exposes Kaydet's functionality
to AI assistants and other MCP-compatible tools.

Install with: pip install kaydet[mcp]
Run with: kaydet-mcp
"""

from __future__ import annotations

import json
import sys
from typing import Any

from .database import log_sync_action
from .service import KaydetService


class MissingMCPDependencyError(RuntimeError):
    """Raised when the optional MCP dependency is missing."""


Server: Any | None = None
stdio_server: Any | None = None
TextContent: Any | None = None
Tool: Any | None = None


def _load_mcp_dependencies():
    """Return MCP objects or raise a helpful error if missing."""

    global Server, stdio_server, TextContent, Tool
    if all(
        symbol is not None
        for symbol in (Server, stdio_server, TextContent, Tool)
    ):
        return Server, stdio_server, TextContent, Tool

    try:
        from mcp.server import Server as MCPServer  # noqa: PLC0415
        from mcp.server.stdio import stdio_server as MCPStdio  # noqa: PLC0415
        from mcp.types import TextContent as MCPTextContent  # noqa: PLC0415
        from mcp.types import Tool as MCPTool  # noqa: PLC0415
    except ModuleNotFoundError as error:  # pragma: no cover - import guard
        raise MissingMCPDependencyError(
            (
                "kaydet-mcp requires the optional 'mcp' dependency. "
                "Install it via `pip install 'kaydet[mcp]'` or the "
                'GitHub equivalent `pip install "git+https://github.com/'
                'miratcan/kaydet.git#egg=kaydet[mcp]"`.'
            )
        ) from error
    Server = MCPServer
    stdio_server = MCPStdio
    TextContent = MCPTextContent
    Tool = MCPTool
    return Server, stdio_server, TextContent, Tool


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
                description="Add a new entry",
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
                        "entry_id": {"type": "string"},
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
                        "entry_id": {"type": "string"},
                    },
                    "required": ["entry_id"],
                },
            ),
            Tool(
                name="get_entry",
                description="Get a single entry by its numeric ID",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "entry_id": {"type": "string"},
                    },
                    "required": ["entry_id"],
                },
            ),
            Tool(
                name="search_entries",
                description="Search entries",
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
                description=(
                    "Suggest project tags based on "
                    "the current directory"
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": (
                                "Directory to inspect."
                                " Defaults to cwd."
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
                        "entry_id": {"type": "string"},
                    },
                    "required": ["entry_id"],
                },
            ),
            Tool(
                name="list_todos",
                description=(
                    "List todos. By default only pending todos are shown."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "status": {
                            "type": "string",
                            "enum": ["pending", "done", "all"],
                            "description": (
                                "Filter by status. 'pending' (default), "
                                "'done', or 'all'."
                            ),
                        },
                        "filter": {
                            "type": "string",
                            "description": (
                                "Optional search query to filter todos "
                                "(e.g., '#work' or 'groceries')."
                            ),
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
                    text=json.dumps({"success": False, "error": message}),
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
            if result.get("success") and result.get("entry_id"):
                log_sync_action(service.conn, result["entry_id"], "created")
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
            if result.get("success"):
                log_sync_action(service.conn, entry_id, "updated")
            return [TextContent(type="text", text=json.dumps(result))]

        if name == "delete_entry":
            entry_id = arguments.get("entry_id")
            if entry_id is None:
                return error_response("entry_id is required")
            result = service.delete_entry(entry_id)
            if result.get("success"):
                log_sync_action(service.conn, entry_id, "deleted")
            return [TextContent(type="text", text=json.dumps(result))]

        if name == "get_entry":
            entry_id = arguments.get("entry_id")
            if entry_id is None:
                return error_response("entry_id is required")
            result = service.get_entry(entry_id)
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
            if result.get("success") and result.get("entry_id"):
                log_sync_action(service.conn, result["entry_id"], "created")
            return [TextContent(type="text", text=json.dumps(result))]

        if name == "mark_todo_done":
            entry_id = arguments.get("entry_id")
            if entry_id is None:
                return error_response("entry_id is required")
            result = service.mark_todo_done(entry_id)
            if result.get("success"):
                log_sync_action(service.conn, entry_id, "updated")
            return [TextContent(type="text", text=json.dumps(result))]

        if name == "list_todos":
            raw_status = arguments.get("status", "pending")
            status_filter = None if raw_status == "all" else raw_status
            result = service.list_todos(
                status=status_filter,
                filter_query=arguments.get("filter"),
            )
            return [TextContent(type="text", text=json.dumps(result))]

        return error_response(f"Unknown tool: {name}")

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream, write_stream, server.create_initialization_options()
        )


def main() -> None:
    """Entry point for the MCP server."""
    import asyncio  # noqa: PLC0415

    try:
        asyncio.run(serve())
    except MissingMCPDependencyError as error:
        print(error, file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
