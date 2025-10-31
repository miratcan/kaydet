"""Add entry command."""

from __future__ import annotations

import argparse
import re
from configparser import SectionProxy
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, Tuple

from .. import database
from ..parsers import (
    deduplicate_tags,
    extract_tags_from_text,
    extract_words_from_text,
    format_entry_header,
    parse_numeric_value,
    partition_entry_tokens,
)
from ..utils import ensure_day_file, open_editor, save_last_entry_timestamp


class EmptyEntryError(ValueError):
    """Raised when an entry save attempt lacks content, metadata, and tags."""


def _parse_at_str(at_str: str, now: datetime) -> datetime:
    """Parse a custom timestamp string into a datetime object."""
    at_str = at_str.strip()
    try:
        # Is it just time? e.g., "14:30"
        t = datetime.strptime(at_str, "%H:%M").time()
        return now.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0)
    except ValueError:
        # Is it a full datetime? e.g., "2025-10-28:14:30"
        try:
            return datetime.strptime(at_str, "%Y-%m-%d:%H:%M")
        except ValueError:
            raise ValueError(
                f"Invalid --at format: '{at_str}'. Use 'HH:MM' or 'YYYY-MM-DD:HH:MM'."
            )


def insert_entry_chronologically(
    day_file: Path,
    entry_id: int,
    timestamp: str,
    message_lines: Tuple[str, ...],
    metadata: Dict[str, str],
    extra_tag_markers: Iterable[str],
) -> None:
    """Insert an entry into a day file, maintaining chronological order."""
    header_line = format_entry_header(
        timestamp,
        message_lines[0] if message_lines else "",
        metadata,
        extra_tag_markers,
        entry_id=str(entry_id),
    )
    new_entry_content = [header_line] + [f"  {line}" for line in message_lines[1:]]


    if not day_file.exists():
        with day_file.open("w", encoding="utf-8") as handle:
            for line in new_entry_content:
                handle.write(f"{line}\n")
        return

    lines = day_file.read_text(encoding="utf-8").splitlines()
    output_lines = []
    inserted = False

    for line in lines:
        match = re.match(r"(\d{2}:\d{2})", line)
        if not inserted and match:
            line_timestamp = match.group(1)
            if timestamp < line_timestamp:
                output_lines.extend(new_entry_content)
                inserted = True
        output_lines.append(line)

    if not inserted:
        output_lines.extend(new_entry_content)

    with day_file.open("w", encoding="utf-8") as handle:
        for line in output_lines:
            handle.write(f"{line}\n")


def create_entry(
    *,
    raw_entry: str,
    config: SectionProxy,
    metadata: Dict[str, str],
    explicit_tags: Iterable[str],
    config_dir: Path,
    log_dir: Path,
    now: datetime,
    conn,
    at_str: str | None = None,
) -> Dict[str, str]:
    """Persist an entry using shared logic for CLI and programmatic callers."""

    entry_body = raw_entry.strip()
    unique_explicit = sorted(
        {tag.strip().lower() for tag in explicit_tags if tag}
    )
    if not any((entry_body, metadata, unique_explicit)):
        raise EmptyEntryError("An entry must include text, metadata, or tags.")

    day_file = ensure_day_file(log_dir, now, config)
    timestamp = now.strftime("%H:%M")

    message_lines = tuple(entry_body.splitlines() or [entry_body])
    embedded_tags = extract_tags_from_text(entry_body)
    extra_tag_markers = [
        tag for tag in unique_explicit if tag not in set(embedded_tags)
    ]
    all_tags = deduplicate_tags(unique_explicit, message_lines)

    words = extract_words_from_text(entry_body)
    full_metadata = {
        key: (value, parse_numeric_value(value))
        for key, value in metadata.items()
    }

    entry_id = database.add_entry(
        conn=conn,
        source_file=day_file.name,
        timestamp=timestamp,
        tags=all_tags,
        words=words,
        metadata=full_metadata,
    )

    try:
        write_func = (
            insert_entry_chronologically if at_str else append_entry
        )
        write_func(
            day_file=day_file,
            entry_id=entry_id,
            timestamp=timestamp,
            message_lines=message_lines,
            metadata=metadata,
            extra_tag_markers=extra_tag_markers,
        )
    except Exception:
        cleanup_payload = (entry_id,)
        conn.execute("DELETE FROM tags WHERE entry_id = ?", cleanup_payload)
        conn.execute("DELETE FROM words WHERE entry_id = ?", cleanup_payload)
        conn.execute(
            "DELETE FROM metadata WHERE entry_id = ?", cleanup_payload
        )
        conn.execute("DELETE FROM entries WHERE id = ?", cleanup_payload)
        raise

    save_last_entry_timestamp(config_dir, now)
    return {
        "entry_id": entry_id,
        "day_file": str(day_file),
        "timestamp": timestamp,
    }


def get_entry(
    args: argparse.Namespace, config: SectionProxy
) -> Tuple[str, Dict[str, str], Tuple[str, ...]]:
    """Resolve entry text, metadata, and tags from CLI args or the editor."""
    tokens = list(args.entry or [])
    message_tokens, metadata, explicit_tags = partition_entry_tokens(tokens)
    message_text = " ".join(message_tokens)
    if args.use_editor or not (message_text or metadata or explicit_tags):
        editor_text = open_editor(message_text, config["EDITOR"])
        # Editor text is returned as-is; metadata and tags can be embedded with
        # hashes and key:value pairs.
        return editor_text, {}, ()
    return message_text, metadata, tuple(explicit_tags)


def append_entry(
    day_file: Path,
    entry_id: int,
    timestamp: str,
    message_lines: Tuple[str, ...],
    metadata: Dict[str, str],
    extra_tag_markers: Iterable[str],
) -> None:
    """Append a timestamped entry with its numeric identifier."""
    first_line = message_lines[0] if message_lines else ""
    header_line = format_entry_header(
        timestamp,
        first_line,
        metadata,
        extra_tag_markers,
        entry_id=str(entry_id),
    )

    with day_file.open("a", encoding="utf-8") as handle:
        handle.write(f"{header_line}\n")
        for line in message_lines[1:]:
            handle.write(f"{line}\n")


def add_entry_command(args, config, config_dir, log_dir, now, conn):
    """Handle the add entry command."""
    entry_now = _parse_at_str(args.at, now) if args.at else now

    # Prevent future entries
    if entry_now > now:
        print("Cannot create entries in the future.")
        return

    ensure_day_file(log_dir, entry_now, config)
    raw_entry, metadata, explicit_tags = get_entry(args, config)
    entry_body = raw_entry.strip()
    if not any((entry_body, metadata, explicit_tags)):
        print("Nothing to save.")
        return

    result = create_entry(
        raw_entry=raw_entry,
        metadata=metadata,
        explicit_tags=explicit_tags,
        config=config,
        config_dir=config_dir,
        log_dir=log_dir,
        now=entry_now,
        conn=conn,
        at_str=args.at,
    )

    print(f"Entry added to: {result['day_file']} (ID: {result['entry_id']})")
    return result
