"""Tests for formatters module."""

import io
from datetime import date
from unittest.mock import patch

import pytest

from kaydet.formatters import SearchResult, format_todo_results


class TestSearchResult:
    """Tests for SearchResult class."""

    def test_create_minimal_search_result(self):
        """Test creating a SearchResult with minimal data."""
        result = SearchResult(
            entry_id=123,
            day=date(2025, 10, 29),
            timestamp="14:30",
            lines=["Test entry"],
        )
        assert result.entry_id == 123
        assert result.day == date(2025, 10, 29)
        assert result.timestamp == "14:30"
        assert result.lines == ["Test entry"]
        assert result.metadata == {}
        assert result.tags == []

    def test_create_full_search_result(self):
        """Test creating a SearchResult with all data."""
        result = SearchResult(
            entry_id=456,
            day=date(2025, 10, 29),
            timestamp="15:45",
            lines=["Another test entry"],
            metadata={"status": "done", "priority": "high"},
            tags=["todo", "urgent"],
        )
        assert result.entry_id == 456
        assert result.metadata == {"status": "done", "priority": "high"}
        assert result.tags == ["todo", "urgent"]


class TestFormatTodoResults:
    """Tests for format_todo_results function."""

    def test_format_empty_todos_text(self, capsys):
        """Test formatting empty todo list in text format."""
        format_todo_results([], "text")
        captured = capsys.readouterr()
        assert "No todos found" in captured.out

    def test_format_empty_todos_json(self, capsys):
        """Test formatting empty todo list in JSON format."""
        format_todo_results([], "json")
        captured = capsys.readouterr()
        assert '"todos": []' in captured.out

    def test_format_pending_todos_text(self, capsys):
        """Test formatting pending todos in text format."""
        todos = [
            {
                "id": 1,
                "date": "2025-10-29",
                "timestamp": "14:00",
                "status": "pending",
                "completed_at": "",
                "description": "Fix bug in authentication",
            },
            {
                "id": 2,
                "date": "2025-10-29",
                "timestamp": "15:00",
                "status": "pending",
                "completed_at": "",
                "description": "Write documentation",
            },
        ]
        format_todo_results(todos, "text")
        captured = capsys.readouterr()

        assert "Pending Todos" in captured.out
        assert "[ ]" in captured.out
        assert "[1]" in captured.out
        assert "[2]" in captured.out
        assert "Fix bug in authentication" in captured.out
        assert "Write documentation" in captured.out
        assert "2 pending" in captured.out
        assert "0 completed" in captured.out

    def test_format_completed_todos_text(self, capsys):
        """Test formatting completed todos in text format."""
        todos = [
            {
                "id": 3,
                "date": "2025-10-29",
                "timestamp": "14:00",
                "status": "done",
                "completed_at": "16:00",
                "description": "Implement feature X",
            },
        ]
        format_todo_results(todos, "text")
        captured = capsys.readouterr()

        assert "Completed Todos" in captured.out
        # Rich console strips [x] markup, just check for the ID
        assert "[3]" in captured.out
        assert "Implement feature X" in captured.out
        assert "Completed: 16:00" in captured.out
        assert "0 pending" in captured.out
        assert "1 completed" in captured.out

    def test_format_mixed_todos_text(self, capsys):
        """Test formatting mix of pending and completed todos."""
        todos = [
            {
                "id": 1,
                "date": "2025-10-29",
                "timestamp": "14:00",
                "status": "pending",
                "completed_at": "",
                "description": "Pending task",
            },
            {
                "id": 2,
                "date": "2025-10-29",
                "timestamp": "15:00",
                "status": "done",
                "completed_at": "16:00",
                "description": "Completed task",
            },
        ]
        format_todo_results(todos, "text")
        captured = capsys.readouterr()

        assert "Pending Todos" in captured.out
        assert "Completed Todos" in captured.out
        assert "[ ]" in captured.out
        # Rich console strips [x] markup, just verify content
        assert "[2]" in captured.out
        assert "Completed task" in captured.out
        assert "1 pending" in captured.out
        assert "1 completed" in captured.out

    def test_format_todos_json(self, capsys):
        """Test formatting todos in JSON format."""
        todos = [
            {
                "id": 1,
                "date": "2025-10-29",
                "timestamp": "14:00",
                "status": "pending",
                "completed_at": "",
                "description": "Test todo",
            },
        ]
        format_todo_results(todos, "json")
        captured = capsys.readouterr()

        assert '"todos"' in captured.out
        assert '"id": 1' in captured.out
        assert '"status": "pending"' in captured.out
        assert '"description": "Test todo"' in captured.out

    def test_todo_without_completed_at(self, capsys):
        """Test formatting todo without completed_at field."""
        todos = [
            {
                "id": 1,
                "date": "2025-10-29",
                "timestamp": "14:00",
                "status": "pending",
                "completed_at": "",
                "description": "Task without completion time",
            },
        ]
        format_todo_results(todos, "text")
        captured = capsys.readouterr()

        # Should not show "Completed:" line for pending tasks
        assert "Completed:" not in captured.out
        assert "Task without completion time" in captured.out
