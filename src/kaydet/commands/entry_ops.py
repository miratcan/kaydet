"""Shared helpers for manipulating diary entries stored on disk."""

from __future__ import annotations

from pathlib import Path
from typing import List, Sequence, Tuple

from ..parsers import ENTRY_LINE_PATTERN


class EntryNotFoundError(LookupError):
    """Raised when an entry cannot be located inside a diary file."""


def read_day_file(day_file: Path) -> Tuple[str, List[str], bool]:
    """Return the raw text, split lines, and trailing newline state."""
    try:
        raw_text = day_file.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raw_text = day_file.read_text(encoding="utf-8", errors="replace")
    lines = raw_text.splitlines()
    return raw_text, lines, raw_text.endswith("\n")


def find_entry_block(
    lines: Sequence[str], entry_id: int
) -> Tuple[int, int]:
    """Return the start (inclusive) and end (exclusive) indices."""
    entry_id_str = str(entry_id)
    start_index = None
    for index, line in enumerate(lines):
        match = ENTRY_LINE_PATTERN.match(line)
        if not match:
            continue
        matched_id = match.group(2)
        if matched_id == entry_id_str:
            start_index = index
            break
    if start_index is None:
        raise EntryNotFoundError(entry_id_str)
    end_index = start_index + 1
    while end_index < len(lines) and not ENTRY_LINE_PATTERN.match(
        lines[end_index]
    ):
        end_index += 1
    return start_index, end_index


def write_day_file(
    day_file: Path,
    lines: Sequence[str],
    ensure_trailing_newline: bool,
) -> None:
    """Persist the provided lines back to the diary file."""
    new_text = "\n".join(lines)
    if ensure_trailing_newline or not lines:
        new_text = f"{new_text}\n" if new_text else "\n"
    day_file.write_text(new_text, encoding="utf-8")
