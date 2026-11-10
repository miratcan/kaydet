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

    class FakeResult:
        def __init__(self, **fields):
            self.__dict__.update(fields)

    class FakeServer:
        def __init__(self, name, *, version, on_list_tools, on_call_tool):
            recorded["name"] = name
            recorded["list_tools"] = on_list_tools
            recorded["call_tool"] = on_call_tool

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
    monkeypatch.setattr(mcp_server, "Server", FakeServer, raising=False)
    monkeypatch.setattr(
        mcp_server, "ListToolsResult", FakeResult, raising=False
    )
    monkeypatch.setattr(
        mcp_server, "CallToolResult", FakeResult, raising=False
    )
    monkeypatch.setattr(mcp_server, "stdio_server", FakeStdio, raising=False)

    asyncio.run(mcp_server.serve())

    def call(tool, arguments):
        params = FakeResult(name=tool, arguments=arguments)
        return asyncio.run(recorded["call_tool"](None, params)).content

    tools = asyncio.run(recorded["list_tools"](None, None)).tools
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

    response = call("add_entry", {"text": "from mcp"})
    assert isinstance(response[0], FakeTextContent)

    suggestion_response = call(
        "suggest_kaydet_tags", {"path": str(mcp_env["log_dir"])}
    )
    assert isinstance(suggestion_response[0], FakeTextContent)
