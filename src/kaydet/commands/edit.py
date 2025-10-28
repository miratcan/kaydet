"""Edit command for updating an existing diary entry."""

from __future__ import annotations

import sqlite3
from configparser import SectionProxy
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from ..parsers import (
    ENTRY_LINE_PATTERN,
    deduplicate_tags,
    extract_tags_from_text,
    format_entry_header,
    parse_stored_entry_remainder,
)
from ..sync import sync_modified_diary_files
from ..utils import DEFAULT_SETTINGS, open_editor
from .entry_ops import (
    EntryNotFoundError,
    find_entry_block,
    read_day_file,
    write_day_file,
)


class InvalidEntryEdit(Exception):
    """Raised when the edited block cannot be parsed into a diary entry."""


def _normalize_edited_block(entry_id: int, lines: List[str]) -> List[str]:
    """Return canonical diary lines after validating the edited block."""
    if not lines:
        raise InvalidEntryEdit("Entry content cannot be empty.")

    header_line = lines[0].rstrip()
    match = ENTRY_LINE_PATTERN.match(header_line)
    if not match:
        raise InvalidEntryEdit(
            "First line must include a timestamp in 'HH:MM' form."
        )
    timestamp, _, remainder = match.groups()

    message, metadata, explicit_tags = parse_stored_entry_remainder(remainder)
    body_lines = lines[1:]
    inline_tags = set(deduplicate_tags([], [message, *body_lines]))
    explicit_markers = [
        tag for tag in explicit_tags if tag not in inline_tags
    ]

    normalized_header = format_entry_header(
        timestamp,
        message,
        metadata,
        explicit_markers,
        entry_id=str(entry_id),
    )
    return [normalized_header, *body_lines]


def edit_entry_command(
    db: sqlite3.Connection,
    log_dir: Path,
    config: SectionProxy,
    entry_id: int,
    now: datetime,
) -> None:
    """Launch the configured editor to update an existing entry."""
    cursor = db.cursor()
    cursor.execute(
        "SELECT source_file FROM entries WHERE id = ?",
        (entry_id,),
    )
    result = cursor.fetchone()
    if result is None:
        print(f"Entry {entry_id} was not found in the index.")
        return

    (source_file,) = result
    day_file = log_dir / source_file
    if not day_file.exists():
        print(
            f"Entry {entry_id} references missing file '{source_file}'. "
            "Run 'kaydet --doctor' to repair the index."
        )
        return

    raw_text, lines, had_trailing_newline = read_day_file(day_file)
    try:
        start, end = find_entry_block(lines, entry_id)
    except EntryNotFoundError:
        print(
            f"Entry {entry_id} could not be located inside '{source_file}'. "
            "Run 'kaydet --doctor' to rebuild the index."
        )
        return

    original_block = lines[start:end]
    initial_text = "\n".join(original_block)
    if raw_text.endswith("\n") and original_block:
        initial_text = f"{initial_text}\n"

    editor_command = config.get("EDITOR", DEFAULT_SETTINGS["EDITOR"])
    edited_text = open_editor(initial_text, editor_command)
    edited_lines = edited_text.splitlines()

    if edited_lines == original_block:
        print(f"No changes made to entry {entry_id}.")
        return

    try:
        normalized_block = _normalize_edited_block(entry_id, edited_lines)
    except InvalidEntryEdit as error:
        print(f"Edit aborted: {error}")
        return

    lines[start:end] = normalized_block
    ensure_newline = had_trailing_newline or edited_text.endswith("\n")
    write_day_file(day_file, lines, ensure_newline)
    sync_modified_diary_files(db, log_dir, config, now)
    print(f"Updated entry {entry_id} in {source_file}.")


def update_entry_inline(
    db: sqlite3.Connection,
    log_dir: Path,
    config: SectionProxy,
    entry_id: int,
    *,
    text: Optional[str] = None,
    metadata: Optional[Dict[str, str]] = None,
    tags: Optional[Iterable[str]] = None,
    timestamp: Optional[str] = None,
    now: datetime,
) -> Dict[str, str] | None:
    """Update an entry without launching an editor."""

    cursor = db.cursor()
    cursor.execute(
        "SELECT source_file FROM entries WHERE id = ?",
        (entry_id,),
    )
    result = cursor.fetchone()
    if result is None:
        print(f"Entry {entry_id} was not found in the index.")
        return None

    (source_file,) = result
    day_file = log_dir / source_file
    if not day_file.exists():
        print(
            f"Entry {entry_id} references missing file '{source_file}'. "
            "Run 'kaydet --doctor' to repair the index."
        )
        return None

    raw_text, lines, had_trailing_newline = read_day_file(day_file)
    try:
        start, end = find_entry_block(lines, entry_id)
    except EntryNotFoundError:
        print(
            f"Entry {entry_id} could not be located inside '{source_file}'. "
            "Run 'kaydet --doctor' to rebuild the index."
        )
        return None

    original_block = lines[start:end]
    if not original_block:
        print(f"Entry {entry_id} is empty and cannot be updated.")
        return None

    header_line = original_block[0].rstrip()
    match = ENTRY_LINE_PATTERN.match(header_line)
    if not match:
        print(f"Entry {entry_id} has an invalid header and cannot be updated.")
        return None

    original_timestamp, _, remainder = match.groups()
    current_message, current_metadata, current_explicit_tags = (
        parse_stored_entry_remainder(remainder)
    )
    existing_body_lines = original_block[1:]

    timestamp_value = timestamp or original_timestamp

    new_text = text if text is not None else "\n".join(
        [current_message, *existing_body_lines]
    )
    entry_body = new_text.strip()

    metadata_map = dict(metadata or current_metadata)
    explicit_tags = list(tags) if tags is not None else list(current_explicit_tags)
    unique_explicit = sorted(
        {tag.strip().lower() for tag in explicit_tags if tag}
    )

    message_lines = tuple(entry_body.splitlines() or [""])
    embedded_tags = extract_tags_from_text(entry_body)
    extra_tag_markers = [
        tag for tag in unique_explicit if tag not in set(embedded_tags)
    ]

    normalized_header = format_entry_header(
        timestamp_value,
        message_lines[0] if message_lines else "",
        metadata_map,
        extra_tag_markers,
        entry_id=str(entry_id),
    )

    normalized_block = [normalized_header, *message_lines[1:]]
    lines[start:end] = normalized_block
    ensure_newline = had_trailing_newline or (
        text is not None and text.endswith("\n")
    )
    write_day_file(day_file, lines, ensure_newline)
    sync_modified_diary_files(db, log_dir, config, now)
    print(f"Updated entry {entry_id} in {source_file}.")
    return {
        "entry_id": entry_id,
        "day_file": str(day_file),
        "timestamp": timestamp_value,
    }
