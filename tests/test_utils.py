"""Tests for utility functions."""

from __future__ import annotations

from configparser import ConfigParser
from datetime import datetime
from pathlib import Path

import pytest

from kaydet.utils import (
    ensure_day_file,
    get_file_glob_from_pattern,
    get_default_index_path,
    get_default_storage_path,
    load_last_entry_timestamp,
    migrate_storage,
    save_last_entry_timestamp,
)


class TestGetFileGlobFromPattern:
    """Tests for get_file_glob_from_pattern."""

    def test_txt_pattern(self):
        assert get_file_glob_from_pattern("%Y-%m-%d.txt") == "*.txt"

    def test_md_pattern(self):
        assert get_file_glob_from_pattern("%Y-%m-%d.md") == "*.md"

    def test_org_pattern(self):
        assert get_file_glob_from_pattern("notes-%Y%m%d.org") == "*.org"

    def test_no_extension(self):
        assert get_file_glob_from_pattern("%Y-%m-%d") == "*"

    def test_templated_extension(self):
        assert get_file_glob_from_pattern("%Y-%m-%d.%m") == "*"


class TestGetDefaultPaths:
    """Tests for default path getters."""

    def test_get_default_storage_path_returns_path(self):
        result = get_default_storage_path()
        assert isinstance(result, Path)
        assert result.name == "Kaydet"

    def test_get_default_index_path_returns_path(self):
        result = get_default_index_path()
        assert isinstance(result, Path)
        assert result.name == "kaydet"


class TestEnsureDayFile:
    """Tests for ensure_day_file."""

    def _make_config(self, tmp_path: Path) -> ConfigParser:
        config = ConfigParser(interpolation=None)
        config["SETTINGS"] = {
            "DAY_FILE_PATTERN": "%Y-%m-%d.txt",
            "DAY_TITLE_PATTERN": "%Y/%m/%d/ - %A",
        }
        return config

    def test_creates_new_file(self, tmp_path):
        config = self._make_config(tmp_path)
        now = datetime(2025, 6, 15, 14, 30)

        day_file = ensure_day_file(tmp_path, now, config["SETTINGS"])

        assert day_file.exists()
        assert day_file.name == "2025-06-15.txt"
        content = day_file.read_text(encoding="utf-8")
        assert "2025/06/15" in content

    def test_existing_file_not_overwritten(self, tmp_path):
        config = self._make_config(tmp_path)
        now = datetime(2025, 6, 15, 14, 30)
        day_file = ensure_day_file(tmp_path, now, config["SETTINGS"])
        day_file.write_text("custom content\n", encoding="utf-8")

        result = ensure_day_file(tmp_path, now, config["SETTINGS"])

        assert result.read_text(encoding="utf-8") == "custom content\n"

    def test_creates_subdirectory(self, tmp_path):
        config = self._make_config(tmp_path)
        sub = tmp_path / "subdir"
        now = datetime(2025, 6, 15, 14, 30)

        day_file = ensure_day_file(sub, now, config["SETTINGS"])

        assert day_file.exists()
        assert sub.exists()


class TestMigrateStorage:
    """Tests for migrate_storage."""

    def test_moves_txt_files(self, tmp_path):
        old = tmp_path / "old"
        new = tmp_path / "new"
        old.mkdir()
        (old / "2025-01-01.txt").write_text("a")
        (old / "2025-01-02.txt").write_text("b")

        migrate_storage(old, new)

        assert (new / "2025-01-01.txt").exists()
        assert (new / "2025-01-02.txt").exists()

    def test_skips_existing_in_target(self, tmp_path):
        old = tmp_path / "old"
        new = tmp_path / "new"
        old.mkdir()
        new.mkdir()
        (old / "2025-01-01.txt").write_text("old")
        (new / "2025-01-01.txt").write_text("new")

        migrate_storage(old, new)

        assert (new / "2025-01-01.txt").read_text() == "new"

    def test_nonexistent_old_path(self, tmp_path):
        old = tmp_path / "nonexistent"
        new = tmp_path / "new"

        migrate_storage(old, new)

        assert not new.exists()

    def test_empty_old_path(self, tmp_path):
        old = tmp_path / "old"
        new = tmp_path / "new"
        old.mkdir()

        migrate_storage(old, new)

        assert not list(new.iterdir())


class TestSaveLoadLastEntryTimestamp:
    """Tests for save/load last entry timestamp roundtrip."""

    def test_roundtrip(self, tmp_path):
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        moment = datetime(2025, 6, 15, 14, 30, 0)

        save_last_entry_timestamp(config_dir, moment)
        result = load_last_entry_timestamp(config_dir, tmp_path)

        assert result is not None
        assert result.year == moment.year
        assert result.month == moment.month
        assert result.day == moment.day

    def test_missing_file_fallback_to_mtime(self, tmp_path):
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        (log_dir / "2025-01-01.txt").write_text("entry")

        result = load_last_entry_timestamp(tmp_path, log_dir)

        assert result is not None

    def test_no_files_returns_none(self, tmp_path):
        log_dir = tmp_path / "empty_logs"
        log_dir.mkdir()

        result = load_last_entry_timestamp(tmp_path, log_dir)

        assert result is None
