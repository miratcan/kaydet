"""Output formatters for search results and entries."""

from __future__ import annotations

from datetime import date
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


def format_search_results(
    matches: List[SearchResult],
    terminal_width: int,
) -> None:
    """
    Format and print search results in a human-readable format.

    Groups entries by date and formats them with proper alignment and wrapping.

    Args:
        matches: List of SearchResult objects to format
        terminal_width: Width of the terminal for text wrapping
    """
    import re
    import textwrap
    from itertools import groupby
    from operator import attrgetter

    if not matches:
        return

    # Calculate maximum ID width for alignment
    max_id_width = max(len(str(m.entry_id)) for m in matches if m.entry_id) if matches else 0

    # Calculate padding: timestamp (5 chars) + space + [id] + : + 1 space
    timestamp_width = 5  # "HH:MM"
    date_padding_width = timestamp_width + 1 + 1 + max_id_width + 1 + 1 + 1  # +1 for the extra character

    for day, entries in groupby(matches, key=attrgetter("day")):
        day_label = day.isoformat() if day else "Undated"
        separator = "=" * len(day_label)
        padding = " " * date_padding_width
        console.print(f"\n{padding}[bold cyan]{separator}[/bold cyan]")
        console.print(f"{padding}[bold cyan]{day_label}[/bold cyan]")
        console.print(f"{padding}[bold cyan]{separator}[/bold cyan]\n")

        entries_list = list(entries)
        for i, entry in enumerate(entries_list):
            id_str = str(entry.entry_id).rjust(max_id_width)
            id_suffix = f"[[dim]{id_str}[/dim]]"

            header = f"[yellow]{entry.timestamp}[/yellow] {id_suffix}:"
            header_len_no_markup = len(entry.timestamp) + 2 + max_id_width + 3

            # Clean lines by removing hashtags
            clean_lines = [re.sub(r'#([a-z-]+)', '', line).strip() for line in entry.lines]

            # Available width for text
            available_width = terminal_width - header_len_no_markup

            wrapper = textwrap.TextWrapper(
                width=available_width,
                break_long_words=False,
                break_on_hyphens=False,
            )

            # Wrap each line separately to preserve newlines
            all_wrapped_lines = []
            for line in clean_lines:
                if line:
                    wrapped = wrapper.wrap(line)
                    all_wrapped_lines.extend(wrapped if wrapped else [''])
                else:
                    all_wrapped_lines.append('')

            if all_wrapped_lines:
                console.print(f"{header} {all_wrapped_lines[0]}")
                for line in all_wrapped_lines[1:]:
                    console.print(" " * header_len_no_markup + line)
            else:
                console.print(header)

            # Print metadata and tags
            indentation = " " * header_len_no_markup
            if entry.metadata:
                metadata_str = " ".join(
                    f"{key}:{value}" for key, value in entry.metadata.items()
                )
                console.print(f"{indentation}[dim]{metadata_str}[/dim]")

            if entry.tags:
                tags_str = " ".join(f"#{tag}" for tag in entry.tags)
                console.print(f"{indentation}[dim]{tags_str}[/dim]")

            # Add spacing between entries except for the last one
            if i < len(entries_list) - 1:
                console.print()


def format_todo_results(
    todos: List[dict],
    output_format: str = "text",
) -> None:
    """
    Format and print todo list results.

    Args:
        todos: List of todo dictionaries with keys: id, date, timestamp, status,
               completed_at, description
        output_format: Either "text" or "json"
    """
    import json

    if output_format == "json":
        console.print(json.dumps({"todos": todos}, indent=2, ensure_ascii=False))
        return

    if not todos:
        console.print("No todos found.")
        return

    pending_todos = [t for t in todos if t["status"] == "pending"]
    done_todos = [t for t in todos if t["status"] == "done"]

    if pending_todos:
        console.print("\n📋 [bold]Pending Todos:[/bold]\n")
        for todo in pending_todos:
            checkbox = "[ ]"
            console.print(f"{checkbox} [cyan][{todo['id']}][/cyan] {todo['description']}")
            console.print(f"    [dim]Created: {todo['date']} {todo['timestamp']}[/dim]")
            if todo.get("completed_at"):
                console.print(f"    [dim]Completed: {todo['completed_at']}[/dim]")
            console.print()

    if done_todos:
        console.print("\n✓ [bold]Completed Todos:[/bold]\n")
        for todo in done_todos:
            checkbox = "[x]"
            console.print(f"{checkbox} [green][{todo['id']}][/green] [dim]{todo['description']}[/dim]")
            console.print(f"    [dim]Created: {todo['date']} {todo['timestamp']}[/dim]")
            if todo.get("completed_at"):
                console.print(f"    [dim]Completed: {todo['completed_at']}[/dim]")
            console.print()

    console.print(f"\nTotal: [cyan]{len(pending_todos)}[/cyan] pending, [green]{len(done_todos)}[/green] completed")


def format_json_search_results(matches: List[SearchResult]) -> str:
    """
    Format search results as JSON.

    Args:
        matches: List of SearchResult objects to format

    Returns:
        JSON string representation of the search results
    """
    import json
    import re

    results = []
    for match in matches:
        # Extract tags and metadata from lines
        tags = []
        text_lines = []

        for line in match.lines:
            # Extract tags
            found_tags = re.findall(r'#([a-z-]+)', line)
            tags.extend(found_tags)

            # Clean line (remove tags)
            clean_line = re.sub(r'#([a-z-]+)', '', line).strip()
            if clean_line:
                text_lines.append(clean_line)

        results.append({
            "id": match.entry_id,
            "date": match.day.isoformat() if match.day else None,
            "timestamp": match.timestamp,
            "text": " ".join(text_lines),
            "tags": list(set(tags)),  # Deduplicate tags
        })

    return json.dumps({"matches": results}, indent=2, ensure_ascii=False)
