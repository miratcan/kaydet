"""MCP server wiring tests (tool registration / call path)."""

from __future__ import annotations

import asyncio

from kaydet import mcp_server


def test_serve_registers_tools(monkeypatch, mcp_env):
    recorded = {}

    class FakeTextContent:
        def __init__(self, *, type, text):
            self.type = type
            self.text = text

    class FakeTool:
        def __init__(self, name, description, inputSchema):
            self.name = name
            self.description = description
            self.inputSchema = inputSchema

    class FakeServer:
        instance = None

        def __call__(self, name):
            FakeServer.instance = self
            return self

        def list_tools(self):
            def decorator(func):
                recorded["list_tools"] = func
                return func

            return decorator

        def call_tool(self):
            def decorator(func):
                recorded["call_tool"] = func
                return func

            return decorator

        def create_initialization_options(self):
            return {}

        async def run(self, *args, **kwargs):
            return

    class FakeStdio:
        async def __aenter__(self):
            return None, None

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(mcp_server, "Tool", FakeTool, raising=False)
    monkeypatch.setattr(
        mcp_server,
        "TextContent",
        FakeTextContent,
        raising=False,
    )
    monkeypatch.setattr(mcp_server, "Server", FakeServer(), raising=False)
    monkeypatch.setattr(mcp_server, "stdio_server", FakeStdio, raising=False)

    asyncio.run(mcp_server.serve())

    tools = asyncio.run(recorded["list_tools"]())
    names = {tool.name for tool in tools}
    required_tools = {
        "add_entry",
        "update_entry",
        "delete_entry",
        "get_entry",
        "search_entries",
        "create_todo",
        "mark_todo_done",
        "list_todos",
        "suggest_kaydet_tags",
    }
    assert required_tools <= names

    response = asyncio.run(
        recorded["call_tool"]("add_entry", {"text": "from mcp"})
    )
    assert isinstance(response[0], FakeTextContent)

    suggestion_response = asyncio.run(
        recorded["call_tool"](
            "suggest_kaydet_tags",
            {"path": str(mcp_env["log_dir"])},
        )
    )
    assert isinstance(suggestion_response[0], FakeTextContent)


