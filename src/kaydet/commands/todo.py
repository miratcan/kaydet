"""Todo management commands."""

from __future__ import annotations

from configparser import SectionProxy
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from rich.console import Console

from ..commands.add import create_entry
from ..formatters import format_todo_results
from ..parsers import partition_entry_tokens


def todo_command(
    args,
    config: SectionProxy,
    config_dir: Path,
    log_dir: Path,
    now: datetime,
    db,
) -> None:
    """Create a new todo entry with status:pending and #todo tag."""
    tokens = list(args.todo or [])
    message_tokens, metadata, explicit_tags = partition_entry_tokens(tokens)
    message_text = " ".join(message_tokens)

    if not message_text:
        print("Todo description cannot be empty.")
        return

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
        db=db,
    )

    print(f"Todo created: {result['day_file']} (ID: {result['entry_id']})")
    print(f"  [{result['entry_id']}] {message_text}")
    print("  Status: pending")


def done_command(
    db,
    log_dir: Path,
    config: SectionProxy,
    entry_id: int,
    now: datetime,
) -> None:
    """Mark a todo entry as done by updating its status metadata."""
    # Find the entry
    cursor = db.cursor()
    cursor.execute(
        "SELECT source_file FROM entries WHERE id = ?",
        (entry_id,)
    )
    result = cursor.fetchone()

    if not result:
        print(f"Entry {entry_id} not found.")
        return

    # Use edit_entry_command to update the entry
    # We'll need to add completed_at metadata and change status to done
    # For now, let's use a simpler approach: directly edit the file

    from ..parsers import parse_day_entries, resolve_entry_date

    source_file = result[0]
    day_file = log_dir / source_file

    if not day_file.exists():
        print(f"File {source_file} not found.")
        return

    day_file_pattern = config.get("DAY_FILE_PATTERN", "")
    entry_date = resolve_entry_date(day_file, day_file_pattern)
    entries = parse_day_entries(day_file, entry_date)

    # Find the specific entry
    target_entry = None
    for entry in entries:
        if entry.entry_id == str(entry_id):
            target_entry = entry
            break

    if not target_entry:
        print(f"Entry {entry_id} not found in {source_file}.")
        return

    # Read the entire file
    with day_file.open("r", encoding="utf-8") as f:
        lines = f.readlines()

    # Find and update the entry
    completed_time = now.strftime("%H:%M")
    updated_lines = []
    found_entry = False

    for _i, line in enumerate(lines):
        # Check if this line starts a new entry
        if line.strip() and line[0].isdigit() and ":" in line[:5]:
            # Extract entry ID from line if it has one
            if f"[{entry_id}]" in line:
                found_entry = True

                # Update the line with new metadata
                # Format: "timestamp [id]: text | metadata items | #tags"
                if " | " in line:
                    # Has metadata
                    parts = line.split(" | ")
                    timestamp_and_text = parts[0]

                    # Metadata is in parts[1], tags in parts[2] (if exists)
                    metadata_section = parts[1] if len(parts) > 1 else ""
                    tags_section = parts[2] if len(parts) > 2 else ""

                    # Split metadata by spaces
                    metadata_items = metadata_section.split()
                    new_metadata_items = []
                    has_status = False
                    has_completed_at = False

                    for item in metadata_items:
                        if item.startswith("status:"):
                            new_metadata_items.append("status:done")
                            has_status = True
                        elif item.startswith("completed_at:"):
                            new_metadata_items.append(
                                f"completed_at:{completed_time}"
                            )
                            has_completed_at = True
                        else:
                            new_metadata_items.append(item)

                    if not has_status:
                        new_metadata_items.insert(0, "status:done")
                    if not has_completed_at:
                        new_metadata_items.insert(
                            1, f"completed_at:{completed_time}"
                        )

                    # Reconstruct line
                    new_metadata_section = " ".join(new_metadata_items)
                    if tags_section:
                        new_line = (
                            f"{timestamp_and_text} | "
                            f"{new_metadata_section} | {tags_section}"
                        )
                    else:
                        new_line = (
                            f"{timestamp_and_text} | "
                            f"{new_metadata_section} |"
                        )

                    if not new_line.endswith("\n"):
                        new_line += "\n"
                    updated_lines.append(new_line)
                else:
                    # No metadata, add it
                    line = line.rstrip("\n")
                    new_line = (
                        f"{line} | status:done "
                        f"completed_at:{completed_time} |\n"
                    )
                    updated_lines.append(new_line)
            else:
                updated_lines.append(line)
        else:
            updated_lines.append(line)

    if not found_entry:
        print(f"Could not find entry {entry_id} in the file.")
        return

    # Write back to file
    with day_file.open("w", encoding="utf-8") as f:
        f.writelines(updated_lines)

    # Update database metadata
    cursor.execute(
        "UPDATE metadata SET meta_value = 'done' "
        "WHERE entry_id = ? AND meta_key = 'status'",
        (entry_id,),
    )
    cursor.execute(
        "SELECT COUNT(*) FROM metadata "
        "WHERE entry_id = ? AND meta_key = 'status'",
        (entry_id,),
    )
    if cursor.fetchone()[0] == 0:
        # Status doesn't exist, insert it
        cursor.execute(
            "INSERT INTO metadata (entry_id, meta_key, meta_value) "
            "VALUES (?, 'status', 'done')",
            (entry_id,),
        )

    # Add completed_at metadata
    from ..parsers import parse_numeric_value

    numeric_val = parse_numeric_value(completed_time)
    cursor.execute(
        "INSERT OR REPLACE INTO metadata "
        "(entry_id, meta_key, meta_value, numeric_value) "
        "VALUES (?, 'completed_at', ?, ?)",
        (entry_id, completed_time, numeric_val),
    )

    db.commit()

    print(f"✓ Todo {entry_id} marked as done at {completed_time}")
    print(f"  Entry updated in {source_file}")


def list_todos_command(
    db,
    log_dir: Path,
    config: SectionProxy,
    output_format: str = "text",
    console: Optional[Console] = None,
) -> None:
    """List all todos with their status."""
    from ..parsers import parse_day_entries, resolve_entry_date

    # Find all entries with #todo tag
    cursor = db.cursor()
    cursor.execute(
        "SELECT DISTINCT e.id, e.source_file "
        "FROM entries e "
        "JOIN tags t ON e.id = t.entry_id "
        "WHERE t.tag_name = 'todo' "
        "ORDER BY e.source_file, e.id"
    )

    results = cursor.fetchall()

    if not results:
        print("No todos found.")
        return

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

                # Get the first line as description
                description = (
                    entry.lines[0] if entry.lines else "(no description)"
                )

                todos.append({
                    "id": entry_id,
                    "date": entry.day.isoformat() if entry.day else "unknown",
                    "timestamp": entry.timestamp,
                    "status": status,
                    "completed_at": completed_at,
                    "description": description,
                })
                break

    # Use the formatter to display todos
    format_todo_results(todos, output_format, config=config, console=console)
