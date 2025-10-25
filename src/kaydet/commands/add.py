"""Add entry command."""

from __future__ import annotations

import argparse
from configparser import SectionProxy
from pathlib import Path
from typing import Dict, Iterable, Tuple

import shortuuid

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
    uuid: str,
    timestamp: str,
    entry_text: str,
    metadata: Dict[str, str],
    explicit_tags: Iterable[str],
) -> Tuple[str, ...]:
    """Append a timestamped entry with a UUID and return all tags."""
    message_lines = entry_text.splitlines() or [entry_text]
    first_line = message_lines[0] if message_lines else ""
    extra_lines = tuple(message_lines[1:])
    embedded_tags = extract_tags_from_text(entry_text)
    unique_explicit = sorted(list(set(t.lower() for t in explicit_tags if t)))
    extra_tag_markers = [
        t for t in unique_explicit if t not in set(embedded_tags)
    ]
    all_tags = deduplicate_tags(unique_explicit, message_lines)

    formatted_header = format_entry_header(
        timestamp, first_line, metadata, extra_tag_markers
    )
    header_line = f"{uuid}:{formatted_header}"

    with day_file.open("a", encoding="utf-8") as handle:
        handle.write(f"{header_line}\n")
        for line in extra_lines:
            handle.write(f"{line}\n")
    return all_tags


def add_entry_command(args, config, config_dir, log_dir, now, db):
    """Handle the add entry command."""
    day_file = ensure_day_file(log_dir, now, config)
    raw_entry, metadata, explicit_tags = get_entry(args, config)
    entry_body = raw_entry.strip()
    if not entry_body and not metadata and not explicit_tags:
        print("Nothing to save.")
        return

    entry_uuid = shortuuid.uuid()
    timestamp = now.strftime("%H:%M")

    tags = append_entry(
        day_file=day_file,
        uuid=entry_uuid,
        timestamp=timestamp,
        entry_text=entry_body,
        metadata=metadata,
        explicit_tags=explicit_tags,
    )
    save_last_entry_timestamp(config_dir, now)

    words = extract_words_from_text(entry_body)
    full_metadata = {
        k: (v, parse_numeric_value(v)) for k, v in metadata.items()
    }

    database.add_entry(
        db=db,
        entry_uuid=entry_uuid,
        source_file=day_file.name,
        timestamp=timestamp,
        tags=tags,
        words=words,
        metadata=full_metadata,
    )
    print("Entry added to:", day_file)
