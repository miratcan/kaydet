"""Output formatters for search results and entries."""

from __future__ import annotations

import json
import re
import textwrap
from datetime import date
from itertools import groupby
from operator import attrgetter
from typing import List, Optional

from rich.console import Console

console = Console()


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


def _clean_hashtags(text: str) -> str:
    """Remove hashtags from text."""
    return re.sub(r"#([a-z-]+)", "", text).strip()


def _calculate_max_id_width(matches: List[SearchResult]) -> int:
    """Calculate maximum ID width for alignment."""
    if not matches:
        return 0
    return max(len(str(m.entry_id)) for m in matches if m.entry_id)


def _calculate_date_padding_width(max_id_width: int) -> int:
    """Calculate padding width for date separators."""
    timestamp_width = 5  # "HH:MM"
    # timestamp + space + [ + id + ] + : + space
    return timestamp_width + 1 + 1 + max_id_width + 1 + 1 + 1


def _wrap_text_lines(
    lines: List[str], available_width: int
) -> List[str]:
    """Wrap text lines to available width, preserving newlines."""
    wrapper = textwrap.TextWrapper(
        width=available_width,
        break_long_words=False,
        break_on_hyphens=False,
    )

    wrapped_lines = []
    for line in lines:
        if line:
            wrapped = wrapper.wrap(line)
            wrapped_lines.extend(wrapped if wrapped else [""])
        else:
            wrapped_lines.append("")

    return wrapped_lines


def _print_date_separator(day: Optional[date], padding_width: int) -> None:
    """Print date separator with proper formatting."""
    day_label = day.isoformat() if day else "Undated"
    separator = "=" * len(day_label)
    padding = " " * padding_width

    console.print(f"\n{padding}[bold cyan]{separator}[/bold cyan]")
    console.print(f"{padding}[bold cyan]{day_label}[/bold cyan]")
    console.print(f"{padding}[bold cyan]{separator}[/bold cyan]\n")


def _print_entry(
    entry: SearchResult,
    max_id_width: int,
    terminal_width: int,
    is_last: bool,
) -> None:
    """Print a single search result entry."""
    # Format header
    id_str = str(entry.entry_id).rjust(max_id_width)
    id_suffix = f"[[dim]{id_str}[/dim]]"
    header = f"[yellow]{entry.timestamp}[/yellow] {id_suffix}:"
    header_len = len(entry.timestamp) + 2 + max_id_width + 3

    # Clean and wrap text
    clean_lines = [_clean_hashtags(line) for line in entry.lines]
    available_width = terminal_width - header_len
    wrapped_lines = _wrap_text_lines(clean_lines, available_width)

    # Print entry text
    if wrapped_lines:
        console.print(f"{header} {wrapped_lines[0]}")
        for line in wrapped_lines[1:]:
            console.print(" " * header_len + line)
    else:
        console.print(header)

    # Print metadata and tags
    indentation = " " * header_len
    if entry.metadata:
        metadata_str = " ".join(
            f"{key}:{value}" for key, value in entry.metadata.items()
        )
        console.print(f"{indentation}[dim]{metadata_str}[/dim]")

    if entry.tags:
        tags_str = " ".join(f"#{tag}" for tag in entry.tags)
        console.print(f"{indentation}[dim]{tags_str}[/dim]")

    # Add spacing between entries
    if not is_last:
        console.print()


def format_search_results(
    matches: List[SearchResult],
    terminal_width: int,
) -> None:
    """
    Format and print search results in a human-readable format.

    Groups entries by date and formats them with proper alignment.

    Args:
        matches: List of SearchResult objects to format
        terminal_width: Width of the terminal for text wrapping
    """
    if not matches:
        return

    max_id_width = _calculate_max_id_width(matches)
    date_padding_width = _calculate_date_padding_width(max_id_width)

    for day, entries in groupby(matches, key=attrgetter("day")):
        _print_date_separator(day, date_padding_width)

        entries_list = list(entries)
        for i, entry in enumerate(entries_list):
            is_last = i == len(entries_list) - 1
            _print_entry(entry, max_id_width, terminal_width, is_last)


def _print_todo(todo: dict, is_completed: bool) -> None:
    """Print a single todo item."""
    checkbox = "[x]" if is_completed else "[ ]"
    color = "green" if is_completed else "cyan"
    dim = "[dim]" if is_completed else ""
    end_dim = "[/dim]" if is_completed else ""

    console.print(
        f"{checkbox} [{color}][{todo['id']}][/{color}] "
        f"{dim}{todo['description']}{end_dim}"
    )
    console.print(
        f"    [dim]Created: {todo['date']} {todo['timestamp']}[/dim]"
    )

    if todo.get("completed_at"):
        console.print(f"    [dim]Completed: {todo['completed_at']}[/dim]")

    console.print()


def format_todo_results(
    todos: List[dict],
    output_format: str = "text",
) -> None:
    """
    Format and print todo list results.

    Args:
        todos: List of todo dictionaries with keys: id, date, timestamp,
               status, completed_at, description
        output_format: Either "text" or "json"
    """
    if output_format == "json":
        console.print(
            json.dumps({"todos": todos}, indent=2, ensure_ascii=False)
        )
        return

    if not todos:
        console.print("No todos found.")
        return

    pending_todos = [t for t in todos if t["status"] == "pending"]
    done_todos = [t for t in todos if t["status"] == "done"]

    if pending_todos:
        console.print("\n📋 [bold]Pending Todos:[/bold]\n")
        for todo in pending_todos:
            _print_todo(todo, is_completed=False)

    if done_todos:
        console.print("\n✓ [bold]Completed Todos:[/bold]\n")
        for todo in done_todos:
            _print_todo(todo, is_completed=True)

    console.print(
        f"\nTotal: [cyan]{len(pending_todos)}[/cyan] pending, "
        f"[green]{len(done_todos)}[/green] completed"
    )


def format_json_search_results(matches: List[SearchResult]) -> str:
    """
    Format search results as JSON.

    Args:
        matches: List of SearchResult objects to format

    Returns:
        JSON string representation of the search results
    """
    results = []
    for match in matches:
        # Extract tags and clean text
        tags = []
        text_lines = []

        for line in match.lines:
            found_tags = re.findall(r"#([a-z-]+)", line)
            tags.extend(found_tags)

            clean_line = _clean_hashtags(line)
            if clean_line:
                text_lines.append(clean_line)

        results.append(
            {
                "id": match.entry_id,
                "date": match.day.isoformat() if match.day else None,
                "timestamp": match.timestamp,
                "text": " ".join(text_lines),
                "tags": list(set(tags)),
            }
        )

    return json.dumps({"matches": results}, indent=2, ensure_ascii=False)
