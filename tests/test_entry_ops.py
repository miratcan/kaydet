"""Tests for shared entry manipulation helpers."""

from __future__ import annotations

import pytest

from kaydet.commands.entry_ops import (
    EntryNotFoundError,
    find_entry_block,
    read_day_file,
    write_day_file,
)


class TestReadDayFile:
    """Tests for read_day_file."""

    def test_reads_normal_file(self, tmp_path):
        day_file = tmp_path / "2025-01-15.txt"
        day_file.write_text("header\n14:30 [1]: hello\n", encoding="utf-8")

        raw, lines, trailing = read_day_file(day_file)

        assert raw == "header\n14:30 [1]: hello\n"
        assert lines == ["header", "14:30 [1]: hello"]
        assert trailing is True

    def test_no_trailing_newline(self, tmp_path):
        day_file = tmp_path / "2025-01-15.txt"
        day_file.write_text("header\n14:30 [1]: hello", encoding="utf-8")

        raw, lines, trailing = read_day_file(day_file)

        assert trailing is False

    def test_handles_bad_encoding(self, tmp_path):
        day_file = tmp_path / "2025-01-15.txt"
        day_file.write_bytes(b"header\n\xff\xfe data\n")

        raw, lines, trailing = read_day_file(day_file)

        assert "header" in lines[0]
        assert len(lines) == 2


class TestFindEntryBlock:
    """Tests for find_entry_block."""

    def test_finds_single_entry(self):
        lines = [
            "header line",
            "14:30 [1]: first entry #work",
            "  continuation line",
            "15:00 [2]: second entry",
        ]

        start, end = find_entry_block(lines, 1)

        assert start == 1
        assert end == 3

    def test_finds_last_entry(self):
        lines = [
            "14:30 [1]: first entry",
            "15:00 [2]: second entry",
            "  body line",
        ]

        start, end = find_entry_block(lines, 2)

        assert start == 1
        assert end == 3

    def test_raises_for_missing_entry(self):
        lines = [
            "14:30 [1]: first entry",
            "15:00 [2]: second entry",
        ]

        with pytest.raises(EntryNotFoundError):
            find_entry_block(lines, 99)

    def test_skips_non_entry_lines(self):
        lines = [
            "header",
            "---",
            "",
            "14:30 [5]: the entry",
        ]

        start, end = find_entry_block(lines, 5)

        assert start == 3
        assert end == 4

    def test_entry_without_body(self):
        lines = [
            "14:30 [1]: solo entry",
            "15:00 [2]: next entry",
        ]

        start, end = find_entry_block(lines, 1)

        assert start == 0
        assert end == 1


class TestWriteDayFile:
    """Tests for write_day_file."""

    def test_writes_with_trailing_newline(self, tmp_path):
        day_file = tmp_path / "test.txt"
        lines = ["header", "14:30 [1]: hello"]

        write_day_file(day_file, lines, ensure_trailing_newline=True)

        content = day_file.read_text(encoding="utf-8")
        assert content == "header\n14:30 [1]: hello\n"

    def test_writes_without_trailing_newline(self, tmp_path):
        day_file = tmp_path / "test.txt"
        lines = ["header", "14:30 [1]: hello"]

        write_day_file(day_file, lines, ensure_trailing_newline=False)

        content = day_file.read_text(encoding="utf-8")
        assert content == "header\n14:30 [1]: hello"

    def test_empty_lines_gets_newline(self, tmp_path):
        day_file = tmp_path / "test.txt"

        write_day_file(day_file, [], ensure_trailing_newline=True)

        content = day_file.read_text(encoding="utf-8")
        assert content == "\n"

    def test_overwrites_existing_content(self, tmp_path):
        day_file = tmp_path / "test.txt"
        day_file.write_text("old content\n", encoding="utf-8")

        write_day_file(day_file, ["new content"], ensure_trailing_newline=True)

        content = day_file.read_text(encoding="utf-8")
        assert content == "new content\n"
        assert "old" not in content
