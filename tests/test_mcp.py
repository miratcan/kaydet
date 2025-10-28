from __future__ import annotations

import asyncio
from configparser import ConfigParser
from datetime import datetime
from pathlib import Path

import pytest

from kaydet import mcp_server


@pytest.fixture
def mcp_env(monkeypatch, tmp_path: Path):
    """Set up a fake Kaydet environment for MCP tests."""

    fake_home = tmp_path
    fake_config_dir = fake_home / ".config" / "kaydet"
    fake_config_dir.mkdir(parents=True)
    fake_config_path = fake_config_dir / "config.ini"
    fake_log_dir = fake_home / ".kaydet"
    fake_log_dir.mkdir(parents=True, exist_ok=True)

    config = ConfigParser(interpolation=None)
    config.add_section("SETTINGS")
    config["SETTINGS"]["LOG_DIR"] = str(fake_log_dir)
    config["SETTINGS"]["DAY_FILE_PATTERN"] = "%Y-%m-%d.txt"
    config["SETTINGS"]["DAY_TITLE_PATTERN"] = "%Y/%m/%d/ - %A"
    config["SETTINGS"]["EDITOR"] = "vim"

    def fake_load_config():
        return config["SETTINGS"], fake_config_path, fake_config_dir, fake_log_dir

    monkeypatch.setattr(mcp_server, "load_config", fake_load_config)

    fixed_now = datetime(2025, 10, 27, 9, 30, 0)

    class MockDateTime(datetime):
        @classmethod
        def now(cls):  # type: ignore[override]
            return fixed_now

    monkeypatch.setattr(mcp_server, "datetime", MockDateTime)

    return {
        "config_dir": fake_config_dir,
        "log_dir": fake_log_dir,
        "config": config,
        "monkeypatch": monkeypatch,
    }


def test_service_add_search_and_delete(mcp_env):
    service = mcp_server.KaydetService.initialize()

    result = service.add_entry(
        text="First note #work",
        metadata={"status": "wip"},
        tags=["focus"],
    )
    assert result["success"] is True
    entry_id = result["entry_id"]

    search = service.search_entries("#work")
    assert search["total"] == 1
    match = search["matches"][0]
    assert match["id"] == str(entry_id)
    assert "First note" in match["text"]

    tags = service.list_tags()
    assert {t["tag"] for t in tags["tags"]} == {"focus", "work"}

    delete = service.delete_entry(entry_id)
    assert delete["success"] is True


def test_service_update_and_recent(mcp_env):
    service = mcp_server.KaydetService.initialize()

    a = service.add_entry(text="Morning run #fitness", metadata={"time": "1h"})
    b = service.add_entry(text="Lunch with team #work", metadata={"mood": "happy"})

    updated = service.update_entry(
        b["entry_id"],
        text="Lunch with team and client #work",
        metadata={"mood": "energized"},
        tags=["team"],
    )
    assert updated["success"] is True

    recent = service.list_recent_entries(limit=2)
    assert len(recent["entries"]) == 2
    ids = [int(entry["id"]) for entry in recent["entries"]]
    assert ids[0] > ids[1]

    by_tag = service.entries_by_tag("team")
    assert len(by_tag["entries"]) == 1
    assert "Lunch with team" in by_tag["entries"][0]["text"]


def test_service_get_stats(mcp_env):
    service = mcp_server.KaydetService.initialize()

    service.add_entry(text="Note one")
    service.add_entry(text="Note two")

    stats = service.get_stats()
    assert stats["success"] is True
    assert stats["total_entries"] == 2


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
    monkeypatch.setattr(mcp_server, "TextContent", FakeTextContent, raising=False)
    monkeypatch.setattr(mcp_server, "Server", FakeServer(), raising=False)
    monkeypatch.setattr(mcp_server, "stdio_server", FakeStdio, raising=False)

    asyncio.run(mcp_server.serve())

    tools = asyncio.run(recorded["list_tools"]())
    names = {tool.name for tool in tools}
    assert {"add_entry", "update_entry", "delete_entry", "search_entries"} <= names

    response = asyncio.run(
        recorded["call_tool"]("add_entry", {"text": "from mcp"})
    )
    assert isinstance(response[0], FakeTextContent)
