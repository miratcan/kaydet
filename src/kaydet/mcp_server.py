"""MCP (Model Context Protocol) server for Kaydet diary application.

This module provides an MCP server that exposes Kaydet's functionality
to AI assistants and other MCP-compatible tools.

Install with: pip install kaydet[mcp]
Run with: kaydet-mcp
"""

from __future__ import annotations

import json
import subprocess
import sys
from typing import Any

# Check if MCP is available
try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import TextContent, Tool

    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False


def run_kaydet_command(*args: str) -> dict[str, Any]:
    """Execute a kaydet CLI command and return parsed JSON output."""
    try:
        result = subprocess.run(
            ["kaydet", *args],
            capture_output=True,
            text=True,
            check=True,
        )
        # If command returns JSON, parse it
        if "--format" in args and "json" in args:
            return json.loads(result.stdout)
        return {"output": result.stdout, "success": True}
    except subprocess.CalledProcessError as e:
        return {
            "error": e.stderr or str(e),
            "success": False,
        }
    except json.JSONDecodeError as e:
        return {
            "error": f"Failed to parse JSON: {e}",
            "output": result.stdout,
            "success": False,
        }


async def serve() -> None:
    """Start the MCP server."""
    server = Server("kaydet")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        """List available Kaydet tools."""
        return [
            Tool(
                name="add_entry",
                description="Add a new diary entry to Kaydet",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "text": {
                            "type": "string",
                            "description": "The diary entry text. Can include hashtags like #work #project",
                        },
                    },
                    "required": ["text"],
                },
            ),
            Tool(
                name="search_entries",
                description="Search diary entries for a query string or tag",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Text to search for in entries (can be a word, phrase, or tag)",
                        },
                    },
                    "required": ["query"],
                },
            ),
            Tool(
                name="list_tags",
                description="List all tags used in diary entries",
                inputSchema={
                    "type": "object",
                    "properties": {},
                },
            ),
            Tool(
                name="get_stats",
                description="Get statistics about diary entries for the current month",
                inputSchema={
                    "type": "object",
                    "properties": {},
                },
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: Any) -> list[TextContent]:
        """Handle tool calls."""
        if name == "add_entry":
            text = arguments.get("text", "")
            if not text:
                return [
                    TextContent(
                        type="text",
                        text=json.dumps(
                            {
                                "error": "Entry text is required",
                                "success": False,
                            }
                        ),
                    )
                ]

            result = run_kaydet_command(text)
            return [TextContent(type="text", text=json.dumps(result))]

        elif name == "search_entries":
            query = arguments.get("query", "")
            if not query:
                return [
                    TextContent(
                        type="text",
                        text=json.dumps(
                            {
                                "error": "Search query is required",
                                "success": False,
                            }
                        ),
                    )
                ]

            result = run_kaydet_command("--search", query, "--format", "json")
            return [TextContent(type="text", text=json.dumps(result))]

        elif name == "list_tags":
            result = run_kaydet_command("--tags", "--format", "json")
            return [TextContent(type="text", text=json.dumps(result))]

        elif name == "get_stats":
            result = run_kaydet_command("--stats", "--format", "json")
            return [TextContent(type="text", text=json.dumps(result))]

        else:
            return [
                TextContent(
                    type="text",
                    text=json.dumps(
                        {"error": f"Unknown tool: {name}", "success": False}
                    ),
                )
            ]

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
