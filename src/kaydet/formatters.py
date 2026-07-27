"""Output formatters for search results and entries."""

from __future__ import annotations

import re
import textwrap
from configparser import SectionProxy
from datetime import date
from itertools import groupby
from operator import attrgetter
from typing import List, Optional

from rich.console import Console

from .json_output import json_ok


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
        attachments: Optional[List[str]] = None,
    ):
        self.entry_id = entry_id
        self.day = day
        self.timestamp = timestamp
        self.lines = lines
        self.metadata = metadata or {}
        self.tags = tags or []
        self.attachments = attachments or []


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

        # break_long_words so URLs/paths cannot overflow the rail width
        wrapper = textwrap.TextWrapper(
            width=max(1, available_width),
            break_long_words=True,
            break_on_hyphens=True,
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
    """Formatter for search results with a tree/rail entry chrome.

    Layout::

        ==========
        2026-07-27
        ==========

        00:27 [1504]
        │ Split test_cli.py + add tests/test_service.py
        │
        │ priority:medium status:done
        │ #kaydet #todo
        └─────
    """

    # Content hangs under a vertical rail so each entry reads as one block.
    _RAIL = "│"
    _RAIL_LINE = "│ "  # rail + space before text
    _RAIL_END = "└─────"
    _RAIL_PREFIX_WIDTH = 2  # len("│ ")

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

        Groups entries by date; each entry is a rail-framed block.

        Parameters
        ----------
        matches : List[SearchResult]
            List of SearchResult objects to format
        """
        if not matches:
            return

        max_id_width = self._calculate_max_id_width(matches)

        for day, entries in groupby(matches, key=attrgetter("day")):
            self._print_date_separator(day)

            entries_list = list(entries)
            for i, entry in enumerate(entries_list):
                is_last = i == len(entries_list) - 1
                self._print_entry(entry, max_id_width, is_last)

    def _calculate_max_id_width(self, matches: List[SearchResult]) -> int:
        """Calculate maximum ID width for alignment within a result set."""
        if not matches:
            return 0
        return max(len(str(m.entry_id)) for m in matches if m.entry_id)

    def _format_entry_header(
        self, timestamp: str, entry_id: int, max_id_width: int
    ) -> str:
        """Format entry chrome: time + id only (body hangs on the rail)."""
        id_str = str(entry_id).rjust(max_id_width)
        color_id = self.config.get("COLOR_ID", "yellow")
        color_date = self.config.get("COLOR_DATE", "green")
        id_suffix = f"[[{color_id}]{id_str}[/{color_id}]]"
        return f"[{color_date}]{timestamp}[/{color_date}] {id_suffix}"

    def _format_metadata_line(self, metadata: dict) -> str:
        """Format metadata dictionary as a string."""
        return " ".join(f"{key}:{value}" for key, value in metadata.items())

    def _format_tags_line(self, tags: List[str]) -> str:
        """Format tags list as a string."""
        return " ".join(f"#{tag}" for tag in tags)

    def _rail_width(self) -> int:
        """Usable text width under the rail prefix."""
        return max(8, self.terminal_width - self._RAIL_PREFIX_WIDTH)

    def _print_rail(self, text: str = "", markup: bool = False) -> None:
        """Print one rail line; empty text yields a lone ``│``."""
        if text:
            # markup strings already include Rich tags
            self.console.print(f"{self._RAIL_LINE}{text}")
        else:
            self.console.print(self._RAIL)

    def _print_date_separator(self, day: Optional[date]) -> None:
        """Print left-aligned date separator (outside entry rails)."""
        day_label = day.isoformat() if day else "Undated"
        separator = "=" * len(day_label)
        color_header = self.config.get("COLOR_HEADER", "bold cyan")

        self.console.print(f"\n[{color_header}]{separator}[/{color_header}]")
        self.console.print(f"[{color_header}]{day_label}[/{color_header}]")
        self.console.print(f"[{color_header}]{separator}[/{color_header}]\n")

    def _print_entry(
        self,
        entry: SearchResult,
        max_id_width: int,
        is_last: bool,
    ) -> None:
        """Print a single search result as a rail-framed block."""
        header = self._format_entry_header(
            entry.timestamp, entry.entry_id, max_id_width
        )
        self.console.print(header)

        clean_lines = [TextUtils.clean_hashtags(line) for line in entry.lines]
        wrapped_lines = TextUtils.wrap_text_lines(
            clean_lines, self._rail_width()
        )
        for line in wrapped_lines:
            self._print_rail(line)

        has_meta = bool(entry.metadata)
        has_tags = bool(entry.tags)
        has_attach = bool(entry.attachments)
        has_footer = has_meta or has_tags or has_attach

        # One breathing rail between body and meta/tags when both exist
        if clean_lines and has_footer:
            self._print_rail()

        if has_meta:
            meta = self._format_metadata_line(entry.metadata)
            self._print_rail(f"[dim]{meta}[/dim]")

        if has_tags:
            tags_str = self._format_tags_line(entry.tags)
            color_tag = self.config.get("COLOR_TAG", "bold magenta")
            self._print_rail(f"[{color_tag}]{tags_str}[/{color_tag}]")

        if has_attach:
            for name in entry.attachments:
                self._print_rail(
                    f"[dim]attachment:[/dim] [underline]{name}[/underline]"
                )

        self.console.print(self._RAIL_END)

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
        return json_ok({"matches": results})

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

    def __init__(
        self,
        console: Console,
        config: Optional[SectionProxy] = None,
    ):
        """
        Initialize formatter.

        Parameters
        ----------
        console : Console
            Rich console for output
        config : SectionProxy, optional
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
            self.console.print(json_ok({"todos": todos}))
            return

        if not todos:
            self.console.print("\U0001f389 No todos found \u2014 all done!")
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
        if self.config is None:
            return "yellow"
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
        color_id = (
            self.config.get("COLOR_ID", "yellow") if self.config else "yellow"
        )
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

        # Body lines after the first (same content as --filter search view)
        body_lines = todo.get("lines") or []
        if len(body_lines) > 1:
            dim_start, dim_end = self._get_dim_markup(is_completed)
            for line in body_lines[1:]:
                self.console.print(f"    {dim_start}{line}{dim_end}")

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
