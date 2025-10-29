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
    """
    Remove hashtags from text.

    Examples:
        >>> _clean_hashtags("Meeting with #team about #project")
        'Meeting with about'
        >>> _clean_hashtags("No tags here")
        'No tags here'
    """
    return re.sub(r"#([a-z-]+)", "", text).strip()


def _extract_hashtags(text: str) -> List[str]:
    """
    Extract hashtags from text.

    Examples:
        >>> _extract_hashtags("Meeting with #team about #project")
        ['team', 'project']
        >>> _extract_hashtags("No tags here")
        []
    """
    return re.findall(r"#([a-z-]+)", text)


def _calculate_max_id_width(matches: List[SearchResult]) -> int:
    """
    Calculate maximum ID width for alignment.

    Examples:
        >>> matches = [SearchResult(5, None, "10:00", []),
        ...            SearchResult(123, None, "11:00", [])]
        >>> _calculate_max_id_width(matches)
        3
        >>> _calculate_max_id_width([])
        0
    """
    if not matches:
        return 0
    return max(len(str(m.entry_id)) for m in matches if m.entry_id)


def _calculate_date_padding_width(max_id_width: int) -> int:
    """
    Calculate padding width for date separators.

    Examples:
        >>> _calculate_date_padding_width(3)  # ID width of 3
        13
        >>> _calculate_date_padding_width(1)  # ID width of 1
        11
    """
    timestamp_width = 5  # "HH:MM"
    # timestamp + space + [ + id + ] + : + space
    return timestamp_width + 1 + 1 + max_id_width + 1 + 1 + 1


def _calculate_header_length(timestamp: str, max_id_width: int) -> int:
    """
    Calculate length of entry header without markup.

    Examples:
        >>> _calculate_header_length("14:30", 3)
        12
        >>> _calculate_header_length("09:15", 1)
        10
    """
    # timestamp + space + [ + id + ] + : + space
    return len(timestamp) + 2 + max_id_width + 3


def _wrap_single_line(line: str, available_width: int) -> List[str]:
    """
    Wrap a single line to available width.

    Examples:
        >>> _wrap_single_line("Short text", 50)
        ['Short text']
        >>> _wrap_single_line("Very long text that needs wrapping", 15)
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


def _wrap_text_lines(lines: List[str], available_width: int) -> List[str]:
    """
    Wrap text lines to available width, preserving newlines.

    Examples:
        >>> _wrap_text_lines(["First", "Second line"], 50)
        ['First', 'Second line']
        >>> _wrap_text_lines(["Very long line here", "Short"], 10)
        ['Very long', 'line here', 'Short']
    """
    wrapped_lines = []
    for line in lines:
        wrapped_lines.extend(_wrap_single_line(line, available_width))
    return wrapped_lines


def _format_entry_header(
    timestamp: str, entry_id: int, max_id_width: int
) -> str:
    """
    Format entry header with timestamp and ID.

    Examples:
        >>> _format_entry_header("14:30", 42, 3)
        '[yellow]14:30[/yellow] [[dim] 42[/dim]]:'
        >>> _format_entry_header("09:00", 5, 2)
        '[yellow]09:00[/yellow] [[dim] 5[/dim]]:'
    """
    id_str = str(entry_id).rjust(max_id_width)
    id_suffix = f"[[dim]{id_str}[/dim]]"
    return f"[yellow]{timestamp}[/yellow] {id_suffix}:"


def _format_metadata_line(metadata: dict) -> str:
    """
    Format metadata dictionary as a string.

    Examples:
        >>> _format_metadata_line({"status": "done", "priority": "high"})
        'status:done priority:high'
        >>> _format_metadata_line({})
        ''
    """
    return " ".join(f"{key}:{value}" for key, value in metadata.items())


def _format_tags_line(tags: List[str]) -> str:
    """
    Format tags list as a string.

    Examples:
        >>> _format_tags_line(["work", "urgent"])
        '#work #urgent'
        >>> _format_tags_line([])
        ''
    """
    return " ".join(f"#{tag}" for tag in tags)


def _print_wrapped_text(
    header: str, wrapped_lines: List[str], indentation: int
) -> None:
    """
    Print wrapped text with header and indentation.

    Examples:
        >>> _print_wrapped_text("Header:", ["First", "Second"], 8)
        # Prints:
        # Header: First
        #         Second
        >>> _print_wrapped_text("ID:", [], 4)
        # Prints:
        # ID:
    """
    if wrapped_lines:
        console.print(f"{header} {wrapped_lines[0]}")
        for line in wrapped_lines[1:]:
            console.print(" " * indentation + line)
    else:
        console.print(header)


def _print_metadata(metadata: dict, indentation: int) -> None:
    """
    Print metadata with proper indentation.

    Examples:
        >>> _print_metadata({"status": "done"}, 8)
        # Prints (with 8 spaces):
        #         [dim]status:done[/dim]
        >>> _print_metadata({}, 8)
        # Prints nothing
    """
    if not metadata:
        return
    metadata_str = _format_metadata_line(metadata)
    padding = " " * indentation
    console.print(f"{padding}[dim]{metadata_str}[/dim]")


def _print_tags(tags: List[str], indentation: int) -> None:
    """
    Print tags with proper indentation.

    Examples:
        >>> _print_tags(["work", "urgent"], 8)
        # Prints (with 8 spaces):
        #         [dim]#work #urgent[/dim]
        >>> _print_tags([], 8)
        # Prints nothing
    """
    if not tags:
        return
    tags_str = _format_tags_line(tags)
    padding = " " * indentation
    console.print(f"{padding}[dim]{tags_str}[/dim]")


def _print_date_separator(day: Optional[date], padding_width: int) -> None:
    """
    Print date separator with proper formatting.

    Examples:
        >>> _print_date_separator(date(2025, 10, 29), 10)
        # Prints:
        #
        #           ==========
        #           2025-10-29
        #           ==========
        >>> _print_date_separator(None, 10)
        # Prints:
        #
        #           =======
        #           Undated
        #           =======
    """
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
    """
    Print a single search result entry.

    Examples:
        >>> entry = SearchResult(42, date(2025, 10, 29), "14:30",
        ...                      ["Test entry"], {"status": "done"}, ["work"])
        >>> _print_entry(entry, 3, 80, False)
        # Prints formatted entry with header, text, metadata, tags, and spacing
        >>> _print_entry(entry, 3, 80, True)
        # Same but without trailing newline (last entry)
    """
    # Format and print header with text
    header = _format_entry_header(
        entry.timestamp, entry.entry_id, max_id_width
    )
    header_len = _calculate_header_length(entry.timestamp, max_id_width)

    clean_lines = [_clean_hashtags(line) for line in entry.lines]
    available_width = terminal_width - header_len
    wrapped_lines = _wrap_text_lines(clean_lines, available_width)

    _print_wrapped_text(header, wrapped_lines, header_len)
    _print_metadata(entry.metadata, header_len)
    _print_tags(entry.tags, header_len)

    if not is_last:
        console.print()


def format_search_results(
    matches: List[SearchResult],
    terminal_width: int,
) -> None:
    """
    Format and print search results in a human-readable format.

    Groups entries by date and formats them with proper alignment.

    Examples:
        >>> matches = [
        ...     SearchResult(1, date(2025, 10, 29), "10:00", ["Entry 1"]),
        ...     SearchResult(2, date(2025, 10, 29), "11:00", ["Entry 2"]),
        ... ]
        >>> format_search_results(matches, 80)
        # Prints date header followed by formatted entries
        >>> format_search_results([], 80)
        # Prints nothing

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


def _get_todo_checkbox(is_completed: bool) -> str:
    """
    Get checkbox string for todo item.

    Examples:
        >>> _get_todo_checkbox(True)
        '[x]'
        >>> _get_todo_checkbox(False)
        '[ ]'
    """
    return "[x]" if is_completed else "[ ]"


def _get_todo_color(is_completed: bool) -> str:
    """
    Get color for todo item.

    Examples:
        >>> _get_todo_color(True)
        'green'
        >>> _get_todo_color(False)
        'cyan'
    """
    return "green" if is_completed else "cyan"


def _get_todo_dim_markup(is_completed: bool) -> tuple[str, str]:
    """
    Get dim markup tags for todo item.

    Examples:
        >>> _get_todo_dim_markup(True)
        ('[dim]', '[/dim]')
        >>> _get_todo_dim_markup(False)
        ('', '')
    """
    if is_completed:
        return "[dim]", "[/dim]"
    return "", ""


def _format_todo_header(
    todo_id: int, description: str, is_completed: bool
) -> str:
    """
    Format todo item header.

    Examples:
        >>> _format_todo_header(42, "Fix bug", False)
        '[ ] [cyan][42][/cyan] Fix bug'
        >>> _format_todo_header(5, "Done task", True)
        '[x] [green][5][/green] [dim]Done task[/dim]'
    """
    checkbox = _get_todo_checkbox(is_completed)
    color = _get_todo_color(is_completed)
    dim_start, dim_end = _get_todo_dim_markup(is_completed)

    return (
        f"{checkbox} [{color}][{todo_id}][/{color}] "
        f"{dim_start}{description}{dim_end}"
    )


def _format_todo_created_line(todo_date: str, timestamp: str) -> str:
    """
    Format todo creation date line.

    Examples:
        >>> _format_todo_created_line("2025-10-29", "14:30")
        '    [dim]Created: 2025-10-29 14:30[/dim]'
        >>> _format_todo_created_line("2025-10-28", "09:00")
        '    [dim]Created: 2025-10-28 09:00[/dim]'
    """
    return f"    [dim]Created: {todo_date} {timestamp}[/dim]"


def _format_todo_completed_line(completed_at: str) -> str:
    """
    Format todo completion date line.

    Examples:
        >>> _format_todo_completed_line("16:45")
        '    [dim]Completed: 16:45[/dim]'
        >>> _format_todo_completed_line("10:30")
        '    [dim]Completed: 10:30[/dim]'
    """
    return f"    [dim]Completed: {completed_at}[/dim]"


def _print_todo(todo: dict, is_completed: bool) -> None:
    """
    Print a single todo item.

    Examples:
        >>> todo = {"id": 42, "description": "Fix bug",
        ...         "date": "2025-10-29", "timestamp": "14:30"}
        >>> _print_todo(todo, False)
        # Prints:
        # [ ] [cyan][42][/cyan] Fix bug
        #     [dim]Created: 2025-10-29 14:30[/dim]
        >>> todo_done = {**todo, "completed_at": "16:45"}
        >>> _print_todo(todo_done, True)
        # Prints with completion line and green color
    """
    header = _format_todo_header(
        todo["id"], todo["description"], is_completed
    )
    console.print(header)

    created_line = _format_todo_created_line(todo["date"], todo["timestamp"])
    console.print(created_line)

    if todo.get("completed_at"):
        completed_line = _format_todo_completed_line(todo["completed_at"])
        console.print(completed_line)

    console.print()


def _format_todo_summary(pending_count: int, done_count: int) -> str:
    """
    Format todo summary line.

    Examples:
        >>> _format_todo_summary(5, 3)
        '\\nTotal: [cyan]5[/cyan] pending, [green]3[/green] completed'
        >>> _format_todo_summary(0, 10)
        '\\nTotal: [cyan]0[/cyan] pending, [green]10[/green] completed'
    """
    return (
        f"\nTotal: [cyan]{pending_count}[/cyan] pending, "
        f"[green]{done_count}[/green] completed"
    )


def _partition_todos_by_status(
    todos: List[dict],
) -> tuple[List[dict], List[dict]]:
    """
    Partition todos into pending and done lists.

    Examples:
        >>> todos = [
        ...     {"status": "pending", "id": 1},
        ...     {"status": "done", "id": 2},
        ...     {"status": "pending", "id": 3}
        ... ]
        >>> pending, done = _partition_todos_by_status(todos)
        >>> len(pending), len(done)
        (2, 1)
    """
    pending = [t for t in todos if t["status"] == "pending"]
    done = [t for t in todos if t["status"] == "done"]
    return pending, done


def format_todo_results(
    todos: List[dict],
    output_format: str = "text",
) -> None:
    """
    Format and print todo list results.

    Examples:
        >>> todos = [
        ...     {"id": 1, "status": "pending", "description": "Task 1",
        ...      "date": "2025-10-29", "timestamp": "14:30"}
        ... ]
        >>> format_todo_results(todos, "text")
        # Prints formatted todo list with headers and summary
        >>> format_todo_results(todos, "json")
        # Prints JSON representation
        >>> format_todo_results([], "text")
        # Prints: No todos found.

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

    pending_todos, done_todos = _partition_todos_by_status(todos)

    if pending_todos:
        console.print("\n📋 [bold]Pending Todos:[/bold]\n")
        for todo in pending_todos:
            _print_todo(todo, is_completed=False)

    if done_todos:
        console.print("\n✓ [bold]Completed Todos:[/bold]\n")
        for todo in done_todos:
            _print_todo(todo, is_completed=True)

    summary = _format_todo_summary(len(pending_todos), len(done_todos))
    console.print(summary)


def _extract_tags_from_lines(lines: List[str]) -> List[str]:
    """
    Extract all tags from list of lines.

    Examples:
        >>> _extract_tags_from_lines(["Meeting #work", "Review #code #urgent"])
        ['code', 'urgent', 'work']
        >>> _extract_tags_from_lines(["No tags"])
        []
    """
    tags = []
    for line in lines:
        found_tags = _extract_hashtags(line)
        tags.extend(found_tags)
    return list(set(tags))


def _clean_text_from_lines(lines: List[str]) -> str:
    """
    Clean and join text lines, removing hashtags.

    Examples:
        >>> _clean_text_from_lines(["Meeting #work", "Review #code"])
        'Meeting Review'
        >>> _clean_text_from_lines(["Plain text", "No tags"])
        'Plain text No tags'
    """
    text_lines = []
    for line in lines:
        clean_line = _clean_hashtags(line)
        if clean_line:
            text_lines.append(clean_line)
    return " ".join(text_lines)


def _format_search_result_as_dict(match: SearchResult) -> dict:
    """
    Format a single SearchResult as a dictionary.

    Examples:
        >>> result = SearchResult(42, date(2025, 10, 29), "14:30",
        ...                       ["Test #work"], {"status": "done"}, ["work"])
        >>> d = _format_search_result_as_dict(result)
        >>> d['id'], d['text'], d['tags']
        (42, 'Test', ['work'])
    """
    return {
        "id": match.entry_id,
        "date": match.day.isoformat() if match.day else None,
        "timestamp": match.timestamp,
        "text": _clean_text_from_lines(match.lines),
        "tags": _extract_tags_from_lines(match.lines),
    }


def format_json_search_results(matches: List[SearchResult]) -> str:
    """
    Format search results as JSON.

    Examples:
        >>> results = [
        ...     SearchResult(1, date(2025, 10, 29), "10:00", ["Entry 1"])
        ... ]
        >>> json_str = format_json_search_results(results)
        >>> "matches" in json_str and "Entry 1" in json_str
        True

    Args:
        matches: List of SearchResult objects to format

    Returns:
        JSON string representation of the search results
    """
    results = [_format_search_result_as_dict(match) for match in matches]
    return json.dumps({"matches": results}, indent=2, ensure_ascii=False)
