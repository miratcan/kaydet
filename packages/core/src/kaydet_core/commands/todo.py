"""Todo management commands."""

from __future__ import annotations

import sqlite3
from configparser import SectionProxy
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from rich.console import Console

from ..commands.add import create_entry
from ..parsers import (
    format_entry_header,
    parse_day_entries,
    parse_numeric_value,
    partition_entry_tokens,
    resolve_entry_date,
)


def todo_command(
    args,
    config: SectionProxy,
    config_dir: Path,
    storage_dir: Path,
    now: datetime,
    conn,
) -> None:
    """Create a new todo entry with status:pending and #todo tag."""
    tokens = list(args.todo or [])
    message_tokens, metadata, explicit_tags = partition_entry_tokens(tokens)
    message_text = " ".join(message_tokens)

    if not message_text:
        return {
            "success": False,
            "message": "Todo description cannot be empty.",
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
        storage_dir=storage_dir,
        now=now,
        conn=conn,
    )

    return {
        "success": True,
        **result,
        "message": (
            f"Todo created: {result['day_file']} "
            f"(ID: {result['entry_id']})\n"
            f"  [{result['entry_id']}] {message_text}\n"
            "  Status: pending"
        ),
    }


def done_command(
    conn: sqlite3.Connection,
    storage_dir: Path,
    config: SectionProxy,
    entry_id: str,
    now: datetime,
) -> dict[str, str]:
    """Mark a todo entry as done by updating its status metadata."""
    # Find the entry
    cursor = conn.cursor()
    cursor.execute("SELECT source_file FROM entries WHERE id = ?", (entry_id,))
    result = cursor.fetchone()

    if not result:
        raise ValueError(f"Entry {entry_id} not found.")

    source_file = result[0]
    day_file = storage_dir / source_file

    if not day_file.exists():
        raise FileNotFoundError(f"File {source_file} not found.")

    day_file_pattern = config.get("DAY_FILE_PATTERN", "")
    entry_date = resolve_entry_date(day_file, day_file_pattern)
    entries = parse_day_entries(day_file, entry_date)

    # Find and update the specific entry object
    target_entry = None
    for entry in entries:
        if entry.entry_id == entry_id:
            target_entry = entry
            break

    if not target_entry:
        raise ValueError(f"Entry {entry_id} not found in {source_file}.")

    # Update metadata
    completed_time = now.strftime("%H:%M")
    target_entry.metadata["status"] = "done"
    target_entry.metadata["completed_at"] = completed_time

    # Re-render the file
    from .entry_ops import read_day_file, write_day_file
    header_text, lines, had_trailing_newline = read_day_file(day_file)

    # We need to find where the entry block was in the original lines
    # and replace it with the new header + body.
    # This is slightly complex because parse_day_entries already parsed everything.
    # A cleaner way is to use find_entry_block.
    from .entry_ops import find_entry_block
    start, end = find_entry_block(lines, entry_id)

    # Prepare new entry block
    message = target_entry.lines[0] if target_entry.lines else ""
    # We want to keep tags as they are in the header or text
    # Deduplicate_tags in Entry.tags is good, but for writing back
    # we want to follow the format_entry_header convention.
    inline_tags = target_entry.tags # This might include hashtags from text
    # Actually format_entry_header takes extra_tag_markers
    # Let's just use the metadata and tags from the target_entry
    new_header = format_entry_header(
        target_entry.timestamp,
        message,
        target_entry.metadata,
        [], # extra tags - they are likely already in metadata or text
        entry_id=entry_id,
        attachments=target_entry.attachments
    )
    new_block = [new_header] + list(target_entry.lines[1:])

    # Replace block in lines
    lines[start:end] = new_block

    # Write back
    write_day_file(day_file, lines, had_trailing_newline)

    # Update database metadata (Index)
    cursor.execute(
        "INSERT OR REPLACE INTO metadata (entry_id, meta_key, meta_value) "
        "VALUES (?, 'status', 'done')",
        (entry_id,),
    )
    numeric_val = parse_numeric_value(completed_time)
    cursor.execute(
        "INSERT OR REPLACE INTO metadata "
        "(entry_id, meta_key, meta_value, numeric_value) "
        "VALUES (?, 'completed_at', ?, ?)",
        (entry_id, completed_time, numeric_val),
    )

    conn.commit()

    return {
        "success": True,
        "entry_id": entry_id,
        "completed_at": completed_time,
        "source_file": source_file,
        "message": f"✓ Todo {entry_id} marked as done at {completed_time}\n"
        f"  Entry updated in {source_file}",
    }


def list_todos_command(
    conn,
    storage_dir: Path,
    config: SectionProxy,
    output_format: str = "text",
    console: Optional[Console] = None,
) -> None:
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
        day_file = storage_dir / source_file
        if not day_file.exists():
            continue

        day_file_pattern = config.get("DAY_FILE_PATTERN", "")
        entry_date = resolve_entry_date(day_file, day_file_pattern)
        entries = parse_day_entries(day_file, entry_date)

        for entry in entries:
            if entry.entry_id == entry_id:
                status = entry.metadata.get("status", "pending")
                completed_at = entry.metadata.get("completed_at", "")

                # Get the first line as description
                description = (
                    entry.lines[0] if entry.lines else "(no description)"
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
                    }
                )
                break

    if not todos:
        return []

    return todos
