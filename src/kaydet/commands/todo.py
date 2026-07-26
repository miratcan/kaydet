"""Todo management commands."""

from __future__ import annotations

from configparser import SectionProxy
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from rich.console import Console

from ..commands.add import create_entry
from ..commands.entry_ops import (
    EntryNotFoundError,
    find_entry_block,
    read_day_file,
    write_day_file,
)
from ..parsers import (
    ENTRY_LINE_PATTERN,
    format_entry_header,
    parse_day_entries,
    parse_stored_entry_remainder,
    partition_entry_tokens,
    resolve_entry_date,
)
from ..sync import sync_modified_diary_files


def todo_command(
    args,
    config: SectionProxy,
    config_dir: Path,
    log_dir: Path,
    now: datetime,
    conn,
) -> dict:
    """Create a new todo entry with status:pending and #todo tag."""
    tokens = list(args.todo or [])
    message_tokens, metadata, explicit_tags = partition_entry_tokens(tokens)
    message_text = " ".join(message_tokens)

    if not message_text:
        return {
            "success": False,
            "message": "\U0001f914 Todo description cannot be empty",
        }

    # Add status:pending metadata
    metadata["status"] = "pending"

    # Add #todo tag if not already present
    explicit_tags = list(explicit_tags)
    if "todo" not in [tag.lower() for tag in explicit_tags]:
        explicit_tags.append("todo")

    result = create_entry(
        raw_entry=message_text,
        metadata=metadata,
        explicit_tags=explicit_tags,
        config=config,
        config_dir=config_dir,
        log_dir=log_dir,
        now=now,
        conn=conn,
    )

    return {
        "success": True,
        **result,
        "message": (
            f"\U0001f4dd Todo Created (ID: {result['entry_id']})\n"
            f"  [{result['entry_id']}] {message_text}"
        ),
    }


def done_command(
    conn,
    log_dir: Path,
    config: SectionProxy,
    entry_id: int,
    now: datetime,
) -> dict:
    """Mark a todo entry as done by updating its status metadata."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT source_file FROM entries WHERE id = ?",
        (entry_id,),
    )
    result = cursor.fetchone()

    if not result:
        raise ValueError(f"\U0001f937 Entry {entry_id} not found")

    source_file = result[0]
    day_file = log_dir / source_file

    if not day_file.exists():
        raise FileNotFoundError(f"\U0001f937 File {source_file} not found")

    raw_text, lines, had_trailing_newline = read_day_file(day_file)
    try:
        start, end = find_entry_block(lines, entry_id)
    except EntryNotFoundError as err:
        raise ValueError(
            f"\U0001f937 Entry {entry_id} could not be located inside "
            f"'{source_file}'. Run 'kaydet --doctor' to rebuild the index."
        ) from err

    header_line = lines[start].rstrip()
    match = ENTRY_LINE_PATTERN.match(header_line)
    if not match:
        raise ValueError(f"\U0001f937 Entry {entry_id} has an invalid header")

    original_timestamp, _, remainder = match.groups()
    (
        message,
        metadata,
        explicit_tags,
        attachments,
    ) = parse_stored_entry_remainder(remainder)
    existing_body_lines = lines[start + 1 : end]

    completed_time = now.strftime("%H:%M")
    metadata["status"] = "done"
    metadata["completed_at"] = completed_time

    normalized_header = format_entry_header(
        original_timestamp,
        message,
        metadata,
        explicit_tags,
        entry_id=str(entry_id),
        attachments=attachments,
    )

    new_block = [normalized_header, *existing_body_lines]
    lines[start:end] = new_block
    write_day_file(day_file, lines, had_trailing_newline)
    sync_modified_diary_files(conn, log_dir, config, now)

    return {
        "success": True,
        "entry_id": entry_id,
        "completed_at": completed_time,
        "source_file": source_file,
        "message": f"\u2705 Todo {entry_id} Done",
    }


def list_todos_command(
    conn,
    log_dir: Path,
    config: SectionProxy,
    output_format: str = "text",
    console: Optional[Console] = None,
) -> list[dict]:
    """List all todos with their status."""
    # Find all pending entries with #todo tag (exclude done)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT DISTINCT e.id, e.source_file "
        "FROM entries e "
        "JOIN tags t ON e.id = t.entry_id "
        "LEFT JOIN metadata m ON e.id = m.entry_id AND m.meta_key = 'status' "
        "WHERE t.tag_name = 'todo' "
        "AND COALESCE(m.meta_value, 'pending') != 'done' "
        "ORDER BY e.source_file, e.id"
    )

    results = cursor.fetchall()

    if not results:
        return []

    todos: List[dict] = []

    for entry_id, source_file in results:
        day_file = log_dir / source_file
        if not day_file.exists():
            continue

        day_file_pattern = config.get("DAY_FILE_PATTERN", "")
        entry_date = resolve_entry_date(day_file, day_file_pattern)
        entries = parse_day_entries(day_file, entry_date)

        for entry in entries:
            if entry.entry_id == str(entry_id):
                status = entry.metadata.get("status", "pending")
                completed_at = entry.metadata.get("completed_at", "")

                lines = list(entry.lines)
                description = (
                    lines[0] if lines else "(no description)"
                )

                todos.append(
                    {
                        "id": entry_id,
                        "date": entry.day.isoformat()
                        if entry.day
                        else "unknown",
                        "timestamp": entry.timestamp,
                        "status": status,
                        "completed_at": completed_at,
                        "description": description,
                        "lines": lines,
                        "text": entry.text,
                        "tags": list(entry.tags),
                        "metadata": dict(entry.metadata),
                    }
                )
                break

    if not todos:
        return []

    return todos
