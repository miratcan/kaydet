"""Shared pytest fixtures for kaydet tests."""

from __future__ import annotations

from configparser import ConfigParser, SectionProxy
from datetime import datetime
from pathlib import Path

import pytest
from rich.console import Console
from rich.text import Text

from kaydet import cli
from kaydet import service as service_module


class MockConsole(Console):
    """A mock Rich Console to capture printed content."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.printed_text = []

    def print(self, *objects, **kwargs):
        for obj in objects:
            if isinstance(obj, Text):
                self.printed_text.append(obj.markup)
            else:
                self.printed_text.append(str(obj))


@pytest.fixture
def mock_config() -> SectionProxy:
    config = ConfigParser()
    config["SETTINGS"] = {
        "COLOR_HEADER": "bold cyan",
        "COLOR_TAG": "bold magenta",
        "COLOR_DATE": "green",
        "COLOR_ID": "yellow",
    }
    return config["SETTINGS"]


@pytest.fixture
def mock_console() -> MockConsole:
    return MockConsole()


@pytest.fixture
def setup_kaydet(monkeypatch, tmp_path: Path) -> dict:
    """Configured Kaydet env for CLI tests (patches cli + service)."""
    fake_home = tmp_path
    fake_config_dir = fake_home / ".config" / "kaydet"
    fake_config_dir.mkdir(parents=True)
    fake_config_path = fake_config_dir / "config.ini"
    fake_log_dir = fake_home / ".kaydet"
    fake_log_dir.mkdir(parents=True, exist_ok=True)

    config = ConfigParser(interpolation=None)
    config.add_section("SETTINGS")
    config["SETTINGS"]["LOG_DIR"] = str(fake_log_dir)
    config["SETTINGS"]["STORAGE_DIR"] = str(fake_log_dir)
    config["SETTINGS"]["DAY_FILE_PATTERN"] = "%Y-%m-%d.txt"
    config["SETTINGS"]["DAY_TITLE_PATTERN"] = "%Y/%m/%d/ - %A"
    config["SETTINGS"]["EDITOR"] = "vim"

    fake_index_dir = fake_home / ".local" / "share" / "kaydet"
    fake_index_dir.mkdir(parents=True, exist_ok=True)

    def fake_load_config():
        return (
            config["SETTINGS"],
            fake_config_path,
            fake_config_dir,
            fake_log_dir,
            fake_index_dir,
        )

    monkeypatch.setattr(cli, "load_config", fake_load_config)
    monkeypatch.setattr(service_module, "load_config", fake_load_config)

    return {
        "monkeypatch": monkeypatch,
        "fake_log_dir": fake_log_dir,
        "fake_config_dir": fake_config_dir,
        "fake_index_dir": fake_index_dir,
    }


@pytest.fixture
def mock_datetime_factory(monkeypatch):
    """Factory fixture to mock datetime.now() to a specific time."""

    def factory(now_fixed: datetime):
        class MockDateTime(datetime):
            @classmethod
            def now(cls, tz=None):
                return now_fixed

        monkeypatch.setattr(cli, "datetime", MockDateTime)
        monkeypatch.setattr(service_module, "datetime", MockDateTime)

    return factory


@pytest.fixture
def service_env(monkeypatch, tmp_path: Path) -> dict:
    """Isolated env for KaydetService / MCP tests."""
    fake_home = tmp_path
    fake_config_dir = fake_home / ".config" / "kaydet"
    fake_config_dir.mkdir(parents=True)
    fake_config_path = fake_config_dir / "config.ini"
    fake_log_dir = fake_home / ".kaydet"
    fake_log_dir.mkdir(parents=True, exist_ok=True)
    fake_index_dir = fake_home / ".kaydet_index"
    fake_index_dir.mkdir(parents=True, exist_ok=True)

    config = ConfigParser(interpolation=None)
    config.add_section("SETTINGS")
    config["SETTINGS"]["LOG_DIR"] = str(fake_log_dir)
    config["SETTINGS"]["STORAGE_DIR"] = str(fake_log_dir)
    config["SETTINGS"]["INDEX_DIR"] = str(fake_index_dir)
    config["SETTINGS"]["DAY_FILE_PATTERN"] = "%Y-%m-%d.txt"
    config["SETTINGS"]["DAY_TITLE_PATTERN"] = "%Y/%m/%d/ - %A"
    config["SETTINGS"]["EDITOR"] = "vim"

    def fake_load_config():
        return (
            config["SETTINGS"],
            fake_config_path,
            fake_config_dir,
            fake_log_dir,
            fake_index_dir,
        )

    monkeypatch.setattr(service_module, "load_config", fake_load_config)

    fixed_now = datetime(2025, 10, 27, 9, 30, 0)

    class MockDateTime(datetime):
        @classmethod
        def now(cls, tz=None):  # type: ignore[override]
            return fixed_now

    monkeypatch.setattr(service_module, "datetime", MockDateTime)

    return {
        "config_dir": fake_config_dir,
        "log_dir": fake_log_dir,
        "index_dir": fake_index_dir,
        "config": config,
        "monkeypatch": monkeypatch,
    }


# Backward-compatible alias used by older MCP tests
@pytest.fixture
def mcp_env(service_env):
    return service_env
