"""Tests for file-to-DB synchronization."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

import pytest

from kaydet import database
from kaydet.sync import (
    _cleanup_missing_entries,
    _split_header,
    _sync_single_file,
    _write_if_changed,
    sync_modified_diary_files,
)


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    """Create an initialized in-memory-like DB connection."""
    db_path = tmp_path / "index.db"
    connection = database.get_db_connection(db_path)
    database.initialize_database(connection)
    return connection


@pytest.fixture
def log_dir(tmp_path: Path) -> Path:
    """Create a temporary log directory with a diary file."""
    log = tmp_path / "diary"
    log.mkdir()
    return log


@pytest.fixture
def config(tmp_path: Path) -> dict:
    """Return a minimal config dict."""
    return {
        "DAY_FILE_PATTERN": "%Y-%m-%d.txt",
        "DAY_TITLE_PATTERN": "%Y/%m/%d/ - %A",
    }


class TestSplitHeader:
    def test_header_before_entries(self):
        lines = [
            "2025/06/15/ - Sunday",
            "-------------------",
            "14:30 [1]: first entry",
        ]
        assert _split_header(lines) == [
            "2025/06/15/ - Sunday",
            "-------------------",
        ]

    def test_no_header(self):
        lines = ["14:30 [1]: first entry"]
        assert _split_header(lines) == []

    def test_empty_file(self):
        assert _split_header([]) == []


class TestWriteIfChanged:
    def test_returns_false_when_no_change(self, tmp_path):
        day_file = tmp_path / "test.txt"
        original = "header\n14:30 [1]: hello\n"
        day_file.write_text(original, encoding="utf-8")

        lines = ["header", "14:30 [1]: hello"]
        changed = _write_if_changed(day_file, original, lines)

        assert changed is False
        assert day_file.read_text(encoding="utf-8") == original

    def test_returns_true_when_changed(self, tmp_path):
        day_file = tmp_path / "test.txt"
        original = "old content\n"
        day_file.write_text(original, encoding="utf-8")

        changed = _write_if_changed(day_file, original, ["new content"])

        assert changed is True
        assert "new content" in day_file.read_text(encoding="utf-8")

    def test_preserves_trailing_newline(self, tmp_path):
        day_file = tmp_path / "test.txt"
        original = "header\n"
        day_file.write_text(original, encoding="utf-8")

        _write_if_changed(day_file, original, ["header", "extra"])

        content = day_file.read_text(encoding="utf-8")
        assert content.endswith("\n")


class TestCleanupMissingEntries:
    def test_removes_orphaned_records(self, conn):
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO entries (id, source_file, timestamp) "
            "VALUES (1, '2025-01-01.txt', '14:30')"
        )
        cursor.execute(
            "INSERT INTO entries (id, source_file, timestamp) "
            "VALUES (2, '2025-01-01.txt', '15:00')"
        )
        conn.commit()

        _cleanup_missing_entries(cursor, "2025-01-01.txt", [1])

        cursor.execute("SELECT id FROM entries")
        remaining = {row[0] for row in cursor.fetchall()}
        assert remaining == {1}

    def test_noop_when_all_present(self, conn):
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO entries (id, source_file, timestamp) "
            "VALUES (1, '2025-01-01.txt', '14:30')"
        )
        conn.commit()

        _cleanup_missing_entries(cursor, "2025-01-01.txt", [1])

        cursor.execute("SELECT id FROM entries")
        assert cursor.fetchall() == [(1,)]


class TestSyncSingleFile:
    def test_syncs_entries_to_db(
        self, conn, log_dir, config
    ):
        day_file = log_dir / "2025-06-15.txt"
        day_file.write_text(
            "2025/06/15/ - Sunday\n"
            "---\n"
            "14:30 [1]: first entry #work\n"
            "15:00 [2]: second entry #personal\n",
            encoding="utf-8",
        )

        _sync_single_file(conn, day_file, config["DAY_FILE_PATTERN"])

        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM entries")
        assert cursor.fetchone()[0] == 2

        cursor.execute("SELECT tag_name FROM tags ORDER BY tag_name")
        tags = {row[0] for row in cursor.fetchall()}
        assert tags == {"personal", "work"}


class TestSyncModifiedDiaryFiles:
    def test_syncs_new_files(
        self, conn, log_dir, config
    ):
        day_file = log_dir / "2025-06-15.txt"
        day_file.write_text(
            "14:30: hello #test\n", encoding="utf-8"
        )

        result = sync_modified_diary_files(
            conn, log_dir, config, datetime(2025, 6, 15, 14, 30)
        )

        assert len(result) == 1
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM entries")
        assert cursor.fetchone()[0] == 1

    def test_skips_unmodified_files(
        self, conn, log_dir, config
    ):
        day_file = log_dir / "2025-06-15.txt"
        day_file.write_text(
            "14:30 [1]: hello\n", encoding="utf-8"
        )

        sync_modified_diary_files(
            conn, log_dir, config, datetime(2025, 6, 15, 14, 30)
        )

        result = sync_modified_diary_files(
            conn, log_dir, config, datetime(2025, 6, 15, 14, 30)
        )

        assert len(result) == 0

    def test_force_reprocess(
        self, conn, log_dir, config
    ):
        day_file = log_dir / "2025-06-15.txt"
        day_file.write_text(
            "14:30: hello\n", encoding="utf-8"
        )

        sync_modified_diary_files(
            conn, log_dir, config, datetime(2025, 6, 15, 14, 30)
        )

        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM entries")
        count_before = cursor.fetchone()[0]

        sync_modified_diary_files(
            conn, log_dir, config, datetime(2025, 6, 15, 14, 30),
            force=True,
        )

        cursor.execute("SELECT COUNT(*) FROM entries")
        assert cursor.fetchone()[0] == count_before

    def test_nonexistent_log_dir(self, conn, tmp_path, config):
        fake = tmp_path / "nonexistent"

        result = sync_modified_diary_files(
            conn, fake, config, datetime(2025, 6, 15)
        )

        assert result == []

    def test_skips_directories(self, conn, log_dir, config):
        (log_dir / "subdir").mkdir()

        result = sync_modified_diary_files(
            conn, log_dir, config, datetime(2025, 6, 15)
        )

        assert result == []
