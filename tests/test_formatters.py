"""Tests for formatters module."""

from datetime import date
from unittest.mock import Mock

from rich.console import Console
from rich.text import Text

from kaydet.formatters import SearchResult, format_todo_results, format_search_results


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

    def test_format_empty_todos_text(self, mock_console, mock_config):
        """Test formatting empty todo list in text format."""
        format_todo_results([], "text", config=mock_config, console=mock_console)
        assert "No todos found" in mock_console.printed_text[0]

    def test_format_empty_todos_json(self, mock_console, mock_config):
        """Test formatting empty todo list in JSON format."""
        format_todo_results([], "json", config=mock_config, console=mock_console)
        assert '"todos": []' in mock_console.printed_text[0]

    def test_format_pending_todos_text(self, mock_console, mock_config):
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
        format_todo_results(todos, "text", config=mock_config, console=mock_console)

        assert "Pending Todos" in mock_console.printed_text[0]
        assert "[ ]" in mock_console.printed_text[1]
        assert "[1]" in mock_console.printed_text[1]
        assert "[ ]" in mock_console.printed_text[3]
        assert "[2]" in mock_console.printed_text[3]
        assert "Fix bug in authentication" in mock_console.printed_text[1]
        assert "Write documentation" in mock_console.printed_text[3]
        assert "[yellow]2[/yellow] pending" in mock_console.printed_text[-1]
        assert "[green]0[/green] completed" in mock_console.printed_text[-1]

    def test_format_pending_todos_text_colors(self, mock_console, mock_config):
        """Test formatting pending todos in text format with colors."""
        todos = [
            {
                "id": 1,
                "date": "2025-10-29",
                "timestamp": "14:00",
                "status": "pending",
                "completed_at": "",
                "description": "Fix bug in authentication",
            },
        ]
        format_todo_results(todos, "text", config=mock_config, console=mock_console)

        # Check for color markup for pending todo ID (yellow by default)
        assert "[yellow][1][/yellow]" in mock_console.printed_text[1]
        # Check for color markup for summary (yellow by default for pending count)
        assert "[yellow]1[/yellow] pending" in mock_console.printed_text[-1]

    def test_format_completed_todos_text(self, mock_console, mock_config):
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
        format_todo_results(todos, "text", config=mock_config, console=mock_console)

        assert "Completed Todos" in mock_console.printed_text[0]
        assert "[3]" in mock_console.printed_text[1]
        assert "Implement feature X" in mock_console.printed_text[1]
        assert "Completed: 16:00" in mock_console.printed_text[3]
        assert "[yellow]0[/yellow] pending" in mock_console.printed_text[-1]
        assert "[green]1[/green] completed" in mock_console.printed_text[-1]

    def test_format_mixed_todos_text(self, mock_console, mock_config):
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
        format_todo_results(todos, "text", config=mock_config, console=mock_console)

        assert "Pending Todos" in mock_console.printed_text[0]
        assert "Completed Todos" in mock_console.printed_text[3]
        assert "[ ]" in mock_console.printed_text[1]
        assert "[green][2][/green]" in mock_console.printed_text[4]
        assert "Completed task" in mock_console.printed_text[4]
        assert "[yellow]1[/yellow] pending" in mock_console.printed_text[-1]
        assert "[green]1[/green] completed" in mock_console.printed_text[-1]

    def test_format_todos_json(self, mock_console, mock_config):
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
        format_todo_results(todos, "json", config=mock_config, console=mock_console)

        assert '"todos"' in mock_console.printed_text[0]
        assert '"id": 1' in mock_console.printed_text[0]
        assert '"status": "pending"' in mock_console.printed_text[0]
        assert '"description": "Test todo"' in mock_console.printed_text[0]

    def test_todo_without_completed_at(self, mock_console, mock_config):
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
        format_todo_results(todos, "text", config=mock_config, console=mock_console)

        # Should not show "Completed:" line for pending tasks
        assert "Completed:" not in mock_console.printed_text[3]
        assert "Task without completion time" in mock_console.printed_text[1]


class TestSearchResultFormatter:
    """Tests for SearchResultFormatter class."""

    def test_format_search_results_colors(self, mock_console, mock_config):
        """Test formatting search results with colors."""
        from kaydet.formatters import format_search_results

        matches = [
            SearchResult(
                entry_id=1,
                day=date(2025, 10, 29),
                timestamp="14:00",
                lines=["Test entry #tag1"],
                tags=["tag1"],
            ),
        ]
        format_search_results(matches, 80, mock_config, console=mock_console)

        # Check for color markup for header (bold cyan by default)
        assert "[bold cyan]==========[/bold cyan]" in mock_console.printed_text[0]
        assert "[bold cyan]2025-10-29[/bold cyan]" in mock_console.printed_text[1]
        # Check for color markup for date (green by default)
        assert "[green]14:00[/green]" in mock_console.printed_text[3]
        # Check for color markup for ID (yellow by default)
        assert "[[yellow]1[/yellow]]:" in mock_console.printed_text[3]
        # Check for color markup for tags (bold magenta by default)
        assert "[bold magenta]#tag1[/bold magenta]" in mock_console.printed_text[4]
