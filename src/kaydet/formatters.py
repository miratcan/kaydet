"""Output formatters for search results and entries."""

from __future__ import annotations

import json
import re
import textwrap
from configparser import SectionProxy
from datetime import date
from itertools import groupby
from operator import attrgetter
from typing import List, Optional

from rich.console import Console


class SearchResult:
    """Represents a single search result entry."""

    def __init__(
        self,
        entry_id: Optional[int],
        day: Optional[date],
        timestamp: str,
        lines: List[str],
        metadata: Optional[dict] = None,
        tags: Optional[List[str]] = None,
    ):
        self.entry_id = entry_id
        self.day = day
        self.timestamp = timestamp
        self.lines = lines
        self.metadata = metadata or {}
        self.tags = tags or []


class TextUtils:
    """Common text manipulation utilities."""

    @staticmethod
    def clean_hashtags(text: str) -> str:
        """
        Remove hashtags from text.

        Examples
        --------
        >>> TextUtils.clean_hashtags("Meeting with #team about #project")
        'Meeting with about'
        >>> TextUtils.clean_hashtags("No tags here")
        'No tags here'
        """
        return re.sub(r"#([a-z-]+)", "", text).strip()

    @staticmethod
    def extract_hashtags(text: str) -> List[str]:
        """
        Extract hashtags from text.

        Examples
        --------
        >>> TextUtils.extract_hashtags("Meeting with #team about #project")
        ['team', 'project']
        >>> TextUtils.extract_hashtags("No tags here")
        []
        """
        return re.findall(r"#([a-z-]+)", text)

    @staticmethod
    def wrap_single_line(line: str, available_width: int) -> List[str]:
        """
        Wrap a single line to available width.

        Examples
        --------
        >>> TextUtils.wrap_single_line("Short text", 50)
        ['Short text']
        >>> TextUtils.wrap_single_line(
        ...     "Very long text that needs wrapping", 15
        ... )
        ['Very long text', 'that needs', 'wrapping']
        """
        if not line:
            return [""]

        wrapper = textwrap.TextWrapper(
            width=available_width,
            break_long_words=False,
            break_on_hyphens=False,
        )
        wrapped = wrapper.wrap(line)
        return wrapped if wrapped else [""]

    @staticmethod
    def wrap_text_lines(lines: List[str], available_width: int) -> List[str]:
        """
        Wrap text lines to available width, preserving newlines.

        Examples
        --------
        >>> TextUtils.wrap_text_lines(["First", "Second line"], 50)
        ['First', 'Second line']
        >>> TextUtils.wrap_text_lines(["Very long line here", "Short"], 10)
        ['Very long', 'line here', 'Short']
        """
        wrapped_lines = []
        for line in lines:
            wrapped_lines.extend(
                TextUtils.wrap_single_line(line, available_width)
            )
        return wrapped_lines


class SearchResultFormatter:
    """Formatter for search results with proper alignment and wrapping."""

    def __init__(
        self, console: Console, terminal_width: int, config: SectionProxy
    ):
        """
        Initialize formatter.

        Parameters
        ----------
        console : Console
            Rich console for output
        terminal_width : int
            Terminal width for text wrapping
        config : SectionProxy
            Configuration object with color settings
        """
        self.console = console
        self.terminal_width = terminal_width
        self.config = config

    def format(self, matches: List[SearchResult]) -> None:
        """
        Format and print search results in a human-readable format.

        Groups entries by date and formats them with proper alignment.

        Examples
        --------
        >>> console = Console()
        >>> formatter = SearchResultFormatter(console, 80)
        >>> matches = [
        ...     SearchResult(1, date(2025, 10, 29), "10:00", ["Entry 1"]),
        ...     SearchResult(2, date(2025, 10, 29), "11:00", ["Entry 2"]),
        ... ]
        >>> formatter.format(matches)
        # Prints date header followed by formatted entries

        Parameters
        ----------
        matches : List[SearchResult]
            List of SearchResult objects to format
        """
        if not matches:
            return

        max_id_width = self._calculate_max_id_width(matches)
        date_padding_width = self._calculate_date_padding_width(max_id_width)

        for day, entries in groupby(matches, key=attrgetter("day")):
            self._print_date_separator(day, date_padding_width)

            entries_list = list(entries)
            for i, entry in enumerate(entries_list):
                is_last = i == len(entries_list) - 1
                self._print_entry(entry, max_id_width, is_last)

    def _calculate_max_id_width(self, matches: List[SearchResult]) -> int:
        """
        Calculate maximum ID width for alignment.

        Examples
        --------
        >>> console = Console()
        >>> formatter = SearchResultFormatter(console, 80)
        >>> matches = [SearchResult(5, None, "10:00", []),
        ...            SearchResult(123, None, "11:00", [])]
        >>> formatter._calculate_max_id_width(matches)
        3
        """
        if not matches:
            return 0
        return max(len(str(m.entry_id)) for m in matches if m.entry_id)

    def _calculate_date_padding_width(self, max_id_width: int) -> int:
        """
        Calculate padding width for date separators.

        Examples
        --------
        >>> console = Console()
        >>> formatter = SearchResultFormatter(console, 80)
        >>> formatter._calculate_date_padding_width(3)
        13
        """
        timestamp_width = 5  # "HH:MM"
        return timestamp_width + 1 + 1 + max_id_width + 1 + 1 + 1

    def _calculate_header_length(
        self, timestamp: str, max_id_width: int
    ) -> int:
        """
        Calculate length of entry header without markup.

        Examples
        --------
        >>> console = Console()
        >>> formatter = SearchResultFormatter(console, 80)
        >>> formatter._calculate_header_length("14:30", 3)
        12
        """
        return len(timestamp) + 2 + max_id_width + 3

    def _format_entry_header(
        self, timestamp: str, entry_id: int, max_id_width: int
    ) -> str:
        """
        Format entry header with timestamp and ID.

        Examples
        --------
        >>> from configparser import ConfigParser
        >>> console = Console()
        >>> config = ConfigParser()
        >>> config["SETTINGS"] = {}
        >>> formatter = SearchResultFormatter(console, 80, config["SETTINGS"])
        >>> formatter._format_entry_header("14:30", 42, 3)
        '[green]14:30[/green] [[yellow] 42[/yellow]]:'
        """
        id_str = str(entry_id).rjust(max_id_width)
        color_id = self.config.get("COLOR_ID", "yellow")
        color_date = self.config.get("COLOR_DATE", "green")
        id_suffix = f"[[{color_id}]{id_str}[/{color_id}]]"
        return f"[{color_date}]{timestamp}[/{color_date}] {id_suffix}:"

    def _format_metadata_line(self, metadata: dict) -> str:
        """
        Format metadata dictionary as a string.

        Examples
        --------
        >>> console = Console()
        >>> formatter = SearchResultFormatter(console, 80)
        >>> formatter._format_metadata_line(
        ...     {"status": "done", "priority": "high"}
        ... )
        'status:done priority:high'
        """
        return " ".join(f"{key}:{value}" for key, value in metadata.items())

    def _format_tags_line(self, tags: List[str]) -> str:
        """
        Format tags list as a string.

        Examples
        --------
        >>> console = Console()
        >>> formatter = SearchResultFormatter(console, 80)
        >>> formatter._format_tags_line(["work", "urgent"])
        '#work #urgent'
        """
        return " ".join(f"#{tag}" for tag in tags)

    def _print_wrapped_text(
        self, header: str, wrapped_lines: List[str], indentation: int
    ) -> None:
        """
        Print wrapped text with header and indentation.

        Examples
        --------
        >>> console = Console()
        >>> formatter = SearchResultFormatter(console, 80)
        >>> formatter._print_wrapped_text("Header:", ["First", "Second"], 8)
        # Prints:
        # Header: First
        #         Second
        """
        if wrapped_lines:
            self.console.print(f"{header} {wrapped_lines[0]}")
            for line in wrapped_lines[1:]:
                self.console.print(" " * indentation + line)
        else:
            self.console.print(header)

    def _print_metadata(self, metadata: dict, indentation: int) -> None:
        """Print metadata with proper indentation."""
        if not metadata:
            return
        metadata_str = self._format_metadata_line(metadata)
        padding = " " * indentation
        self.console.print(f"{padding}[dim]{metadata_str}[/dim]")

    def _print_tags(self, tags: List[str], indentation: int) -> None:
        """Print tags with proper indentation."""
        if not tags:
            return
        tags_str = self._format_tags_line(tags)
        padding = " " * indentation
        color_tag = self.config.get("COLOR_TAG", "bold magenta")
        self.console.print(f"{padding}[{color_tag}]{tags_str}[/{color_tag}]")

    def _print_date_separator(
        self, day: Optional[date], padding_width: int
    ) -> None:
        """Print date separator with proper formatting."""
        day_label = day.isoformat() if day else "Undated"
        separator = "=" * len(day_label)
        padding = " " * padding_width
        color_header = self.config.get("COLOR_HEADER", "bold cyan")

        self.console.print(f"\n{padding}[{color_header}]{separator}[/{color_header}]")
        self.console.print(f"{padding}[{color_header}]{day_label}[/{color_header}]")
        self.console.print(f"{padding}[{color_header}]{separator}[/{color_header}]\n")

    def _print_entry(
        self,
        entry: SearchResult,
        max_id_width: int,
        is_last: bool,
    ) -> None:
        """Print a single search result entry."""
        header = self._format_entry_header(
            entry.timestamp, entry.entry_id, max_id_width
        )
        header_len = self._calculate_header_length(
            entry.timestamp, max_id_width
        )

        clean_lines = [TextUtils.clean_hashtags(line) for line in entry.lines]
        available_width = self.terminal_width - header_len
        wrapped_lines = TextUtils.wrap_text_lines(clean_lines, available_width)

        self._print_wrapped_text(header, wrapped_lines, header_len)
        self._print_metadata(entry.metadata, header_len)
        self._print_tags(entry.tags, header_len)

        if not is_last:
            self.console.print()


class SearchResultJSONFormatter:
    """JSON formatter for search results."""

    @staticmethod
    def format(matches: List[SearchResult]) -> str:
        """
        Format search results as JSON.

        Examples
        --------
        >>> results = [
        ...     SearchResult(1, date(2025, 10, 29), "10:00", ["Entry 1"])
        ... ]
        >>> json_str = SearchResultJSONFormatter.format(results)
        >>> "matches" in json_str and "Entry 1" in json_str
        True

        Parameters
        ----------
        matches : List[SearchResult]
            List of SearchResult objects to format

        Returns
        -------
        str
            JSON string representation of the search results
        """
        results = [
            SearchResultJSONFormatter._format_as_dict(match)
            for match in matches
        ]
        return json.dumps({"matches": results}, indent=2, ensure_ascii=False)

    @staticmethod
    def _extract_tags_from_lines(lines: List[str]) -> List[str]:
        """
        Extract all tags from list of lines.

        Examples
        --------
        >>> SearchResultJSONFormatter._extract_tags_from_lines(
        ...     ["Meeting #work", "Review #code #urgent"])
        ['code', 'urgent', 'work']
        """
        tags = []
        for line in lines:
            found_tags = TextUtils.extract_hashtags(line)
            tags.extend(found_tags)
        return list(set(tags))

    @staticmethod
    def _clean_text_from_lines(lines: List[str]) -> str:
        """
        Clean and join text lines, removing hashtags.

        Examples
        --------
        >>> SearchResultJSONFormatter._clean_text_from_lines(
        ...     ["Meeting #work", "Review #code"])
        'Meeting Review'
        """
        text_lines = []
        for line in lines:
            clean_line = TextUtils.clean_hashtags(line)
            if clean_line:
                text_lines.append(clean_line)
        return " ".join(text_lines)

    @staticmethod
    def _format_as_dict(match: SearchResult) -> dict:
        """
        Format a single SearchResult as a dictionary.

        Examples
        --------
        >>> result = SearchResult(42, date(2025, 10, 29), "14:30",
        ...                       ["Test #work"], {"status": "done"}, ["work"])
        >>> d = SearchResultJSONFormatter._format_as_dict(result)
        >>> d['id'], d['text'], d['tags']
        (42, 'Test', ['work'])
        """
        return {
            "id": match.entry_id,
            "date": match.day.isoformat() if match.day else None,
            "timestamp": match.timestamp,
            "text": SearchResultJSONFormatter._clean_text_from_lines(
                match.lines
            ),
            "tags": SearchResultJSONFormatter._extract_tags_from_lines(
                match.lines
            ),
        }


class TodoFormatter:
    """Formatter for todo list with status-based formatting."""

    def __init__(self, console: Console, config: SectionProxy):
        """
        Initialize formatter.

        Parameters
        ----------
        console : Console
            Rich console for output
        config : SectionProxy
            Configuration object with color settings
        """
        self.console = console
        self.config = config

    def format(self, todos: List[dict], output_format: str = "text") -> None:
        """
        Format and print todo list results.

        Examples
        --------
        >>> console = Console()
        >>> formatter = TodoFormatter(console)
        >>> todos = [
        ...     {"id": 1, "status": "pending", "description": "Task 1",
        ...      "date": "2025-10-29", "timestamp": "14:30"}
        ... ]
        >>> formatter.format(todos, "text")
        # Prints formatted todo list with headers and summary

        Parameters
        ----------
        todos : List[dict]
            List of todo dictionaries
        output_format : str
            Either "text" or "json"
        """
        if output_format == "json":
            self.console.print(
                json.dumps({"todos": todos}, indent=2, ensure_ascii=False)
            )
            return

        if not todos:
            self.console.print("No todos found.")
            return

        pending_todos, done_todos = self._partition_by_status(todos)

        if pending_todos:
            self.console.print("\n📋 [bold]Pending Todos:[/bold]\n")
            for todo in pending_todos:
                self._print_todo(todo, is_completed=False)

        if done_todos:
            self.console.print("\n✓ [bold]Completed Todos:[/bold]\n")
            for todo in done_todos:
                self._print_todo(todo, is_completed=True)

        summary = self._format_summary(len(pending_todos), len(done_todos))
        self.console.print(summary)

    def _partition_by_status(
        self, todos: List[dict]
    ) -> tuple[List[dict], List[dict]]:
        """
        Partition todos into pending and done lists.

        Examples
        --------
        >>> console = Console()
        >>> formatter = TodoFormatter(console)
        >>> todos = [
        ...     {"status": "pending", "id": 1},
        ...     {"status": "done", "id": 2},
        ...     {"status": "pending", "id": 3}
        ... ]
        >>> pending, done = formatter._partition_by_status(todos)
        >>> len(pending), len(done)
        (2, 1)
        """
        pending = [t for t in todos if t["status"] == "pending"]
        done = [t for t in todos if t["status"] == "done"]
        return pending, done

    def _get_checkbox(self, is_completed: bool) -> str:
        """
        Get checkbox string for todo item.

        Examples
        --------
        >>> console = Console()
        >>> formatter = TodoFormatter(console)
        >>> formatter._get_checkbox(True)
        '[x]'
        >>> formatter._get_checkbox(False)
        '[ ]'
        """
        return "[x]" if is_completed else "[ ]"

    def _get_color(self, is_completed: bool) -> str:
        """
        Get color for todo item.

        Examples
        --------
        >>> from configparser import ConfigParser
        >>> console = Console()
        >>> config = ConfigParser()
        >>> config["SETTINGS"] = {}
        >>> formatter = TodoFormatter(console, config["SETTINGS"])
        >>> formatter._get_color(True)
        'green'
        >>> formatter._get_color(False)
        'yellow'
        """
        if is_completed:
            return "green"
        return self.config.get("COLOR_ID", "yellow")

    def _get_dim_markup(self, is_completed: bool) -> tuple[str, str]:
        """
        Get dim markup tags for todo item.

        Examples
        --------
        >>> console = Console()
        >>> formatter = TodoFormatter(console)
        >>> formatter._get_dim_markup(True)
        ('[dim]', '[/dim]')
        >>> formatter._get_dim_markup(False)
        ('', '')
        """
        if is_completed:
            return "[dim]", "[/dim]"
        return "", ""

    def _format_header(
        self, todo_id: int, description: str, is_completed: bool
    ) -> str:
        """
        Format todo item header.

        Examples
        --------
        >>> console = Console()
        >>> formatter = TodoFormatter(console)
        >>> formatter._format_header(42, "Fix bug", False)
        '[ ] [cyan][42][/cyan] Fix bug'
        >>> formatter._format_header(5, "Done task", True)
        '[x] [green][5][/green] [dim]Done task[/dim]'
        """
        checkbox = self._get_checkbox(is_completed)
        color = self._get_color(is_completed)
        dim_start, dim_end = self._get_dim_markup(is_completed)

        return (
            f"{checkbox} [{color}][{todo_id}][/{color}] "
            f"{dim_start}{description}{dim_end}"
        )

    def _format_created_line(self, todo_date: str, timestamp: str) -> str:
        """
        Format todo creation date line.

        Examples
        --------
        >>> console = Console()
        >>> formatter = TodoFormatter(console)
        >>> formatter._format_created_line("2025-10-29", "14:30")
        '    [dim]Created: 2025-10-29 14:30[/dim]'
        """
        return f"    [dim]Created: {todo_date} {timestamp}[/dim]"

    def _format_completed_line(self, completed_at: str) -> str:
        """
        Format todo completion date line.

        Examples
        --------
        >>> console = Console()
        >>> formatter = TodoFormatter(console)
        >>> formatter._format_completed_line("16:45")
        '    [dim]Completed: 16:45[/dim]'
        """
        return f"    [dim]Completed: {completed_at}[/dim]"

    def _format_summary(self, pending_count: int, done_count: int) -> str:
        """
        Format todo summary line.

        Examples
        --------
        >>> from configparser import ConfigParser
        >>> console = Console()
        >>> config = ConfigParser()
        >>> config["SETTINGS"] = {}
        >>> formatter = TodoFormatter(console, config["SETTINGS"])
        >>> formatter._format_summary(5, 3)
        '\\nTotal: [yellow]5[/yellow] pending, [green]3[/green] completed'
        """
        color_id = self.config.get("COLOR_ID", "yellow")
        return (
            f"\nTotal: [{color_id}]{pending_count}[/{color_id}] pending, "
            f"[green]{done_count}[/green] completed"
        )

    def _print_todo(self, todo: dict, is_completed: bool) -> None:
        """
        Print a single todo item.

        Examples
        --------
        >>> console = Console()
        >>> formatter = TodoFormatter(console)
        >>> todo = {"id": 42, "description": "Fix bug",
        ...         "date": "2025-10-29", "timestamp": "14:30"}
        >>> formatter._print_todo(todo, False)
        # Prints:
        # [ ] [cyan][42][/cyan] Fix bug
        #     [dim]Created: 2025-10-29 14:30[/dim]
        """
        header = self._format_header(
            todo["id"], todo["description"], is_completed
        )
        self.console.print(header)

        created_line = self._format_created_line(
            todo["date"], todo["timestamp"]
        )
        self.console.print(created_line)

        if todo.get("completed_at"):
            completed_line = self._format_completed_line(todo["completed_at"])
            self.console.print(completed_line)

        self.console.print()


# Backward compatibility: module-level functions
def format_search_results(
    matches: List[SearchResult],
    terminal_width: int,
    config: SectionProxy,
    console: Console,
) -> None:
    """Format and print search results (backward compatible API)."""
    formatter = SearchResultFormatter(console, terminal_width, config)
    formatter.format(matches)


def format_json_search_results(matches: List[SearchResult]) -> str:
    """Format search results as JSON (backward compatible API)."""
    return SearchResultJSONFormatter.format(matches)


def format_todo_results(
    todos: List[dict],
    output_format: str = "text",
    config: Optional[SectionProxy] = None,
    console: Optional[Console] = None,
) -> None:
    """Format and print todo results (backward compatible API)."""
    console = console or Console()
    formatter = TodoFormatter(console, config)
    formatter.format(todos, output_format)
