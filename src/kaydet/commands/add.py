"""Add entry command."""

from __future__ import annotations

import argparse
from configparser import SectionProxy
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


def add_entry_command(args, config, config_dir, log_dir, now, db):
    """Handle the add entry command."""
    day_file = ensure_day_file(log_dir, now, config)
    raw_entry, metadata, explicit_tags = get_entry(args, config)
    entry_body = raw_entry.strip()
    if not any((entry_body, metadata, explicit_tags)):
        print("Nothing to save.")
        return

    timestamp = now.strftime("%H:%M")

    message_lines = tuple(entry_body.splitlines() or [entry_body])
    embedded_tags = extract_tags_from_text(entry_body)
    unique_explicit = sorted(list(set(t.lower() for t in explicit_tags if t)))
    extra_tag_markers = [
        tag for tag in unique_explicit if tag not in set(embedded_tags)
    ]
    all_tags = deduplicate_tags(unique_explicit, message_lines)

    words = extract_words_from_text(entry_body)
    full_metadata = {
        k: (v, parse_numeric_value(v)) for k, v in metadata.items()
    }

    entry_id = database.add_entry(
        db=db,
        source_file=day_file.name,
        timestamp=timestamp,
        tags=all_tags,
        words=words,
        metadata=full_metadata,
    )

    try:
        append_entry(
            day_file=day_file,
            entry_id=entry_id,
            timestamp=timestamp,
            message_lines=message_lines,
            metadata=metadata,
            extra_tag_markers=extra_tag_markers,
        )
    except Exception:
        cleanup_payload = (entry_id,)
        db.execute("DELETE FROM tags WHERE entry_id = ?", cleanup_payload)
        db.execute("DELETE FROM words WHERE entry_id = ?", cleanup_payload)
        db.execute("DELETE FROM metadata WHERE entry_id = ?", cleanup_payload)
        db.execute("DELETE FROM entries WHERE id = ?", cleanup_payload)
        raise

    save_last_entry_timestamp(config_dir, now)
    print("Entry added to:", day_file)
