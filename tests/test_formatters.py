"""Tests for formatters module."""

from datetime import date

from kaydet.formatters import (
    SearchResult,
    format_search_results,
    format_todo_results,
)


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
        format_todo_results(
            [], "text", config=mock_config, console=mock_console
        )
        assert "No todos found" in mock_console.printed_text[0]

    def test_format_empty_todos_json(self, mock_console, mock_config):
        """Test formatting empty todo list in JSON format."""
        format_todo_results(
            [], "json", config=mock_config, console=mock_console
        )
        out = mock_console.printed_text[0]
        assert '"success": true' in out
        assert '"todos": []' in out

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
        format_todo_results(
            todos, "text", config=mock_config, console=mock_console
        )

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
        format_todo_results(
            todos, "text", config=mock_config, console=mock_console
        )

        # Check for color markup for pending todo ID (yellow by default)
        assert "[yellow][1][/yellow]" in mock_console.printed_text[1]
        # Check color markup for summary (yellow for pending)
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
        format_todo_results(
            todos, "text", config=mock_config, console=mock_console
        )

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
        format_todo_results(
            todos, "text", config=mock_config, console=mock_console
        )

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
        format_todo_results(
            todos, "json", config=mock_config, console=mock_console
        )

        out = mock_console.printed_text[0]
        assert '"success": true' in out
        assert '"data"' in out
        assert '"todos"' in out
        assert '"id": 1' in out
        assert '"status": "pending"' in out
        assert '"description": "Test todo"' in out

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
        format_todo_results(
            todos, "text", config=mock_config, console=mock_console
        )

        # Should not show "Completed:" line for pending tasks
        assert "Completed:" not in mock_console.printed_text[3]
        assert "Task without completion time" in mock_console.printed_text[1]

    def test_todo_body_lines_are_printed(self, mock_console, mock_config):
        """Body lines after the first description line should appear."""
        todos = [
            {
                "id": 7,
                "date": "2025-10-29",
                "timestamp": "14:00",
                "status": "pending",
                "completed_at": "",
                "description": "Write the report",
                "lines": [
                    "Write the report",
                    "Include Q3 numbers",
                    "Send to finance",
                ],
            },
        ]
        format_todo_results(
            todos, "text", config=mock_config, console=mock_console
        )
        joined = "\n".join(mock_console.printed_text)
        assert "Write the report" in joined
        assert "Include Q3 numbers" in joined
        assert "Send to finance" in joined


class TestSearchResultFormatter:
    """Tests for SearchResultFormatter class."""

    def test_format_search_results_colors(self, mock_console, mock_config):
        """Test formatting search results with colors."""

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

        joined = "\n".join(mock_console.printed_text)
        # Date block left-aligned (no leading spaces before ===)
        assert "[bold cyan]==========[/bold cyan]" in joined
        assert "[bold cyan]2025-10-29[/bold cyan]" in joined
        # Chrome line: time + id only (body on following lines)
        assert "[green]14:00[/green]" in joined
        assert "[[yellow]1[/yellow]]" in joined
        assert "Test entry" in joined
        assert "[bold magenta]#tag1[/bold magenta]" in joined

    def test_search_layout_stacks_body_under_chrome(
        self, mock_console, mock_config
    ):
        """Body is not inlined after HH:MM [id]; date header is not padded."""
        matches = [
            SearchResult(
                entry_id=1500,
                day=date(2026, 7, 27),
                timestamp="13:30",
                lines=[
                    "Fix summarize_entries samples bug: m.source_date",
                ],
                metadata={"priority": "high"},
                tags=["kaydet"],
            ),
        ]
        format_search_results(matches, 80, mock_config, console=mock_console)
        lines = mock_console.printed_text

        # Date lines have no leading whitespace before markup
        date_lines = [ln for ln in lines if "2026-07-27" in ln or "===" in ln]
        for ln in date_lines:
            assert not ln.startswith(" "), ln

        # Header chrome alone (no body text on same printed line)
        chrome = next(ln for ln in lines if "13:30" in ln)
        assert "Fix summarize" not in chrome
        assert "1500" in chrome

        body = next(ln for ln in lines if "Fix summarize" in ln)
        assert "13:30" not in body
