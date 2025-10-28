"""Delete command for removing an existing diary entry."""

from __future__ import annotations

import sqlite3
from configparser import SectionProxy
from datetime import datetime
from pathlib import Path

from ..sync import sync_modified_diary_files
from .entry_ops import (
    EntryNotFoundError,
    find_entry_block,
    read_day_file,
    write_day_file,
)


def _confirm_delete(entry_id: int, preview: str, *, assume_yes: bool) -> bool:
    """Return True if the deletion should proceed."""
    if assume_yes:
        return True
    prompt = f"Delete entry {entry_id}? [y/N]\n{preview}\n> "
    response = input(prompt).strip().lower()
    return response in {"y", "yes"}


def delete_entry_command(
    db: sqlite3.Connection,
    log_dir: Path,
    config: SectionProxy,
    entry_id: int,
    *,
    assume_yes: bool,
    now: datetime,
) -> dict[str, str] | None:
    """Remove an entry by identifier and resynchronize the index."""
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

    _, lines, had_trailing_newline = read_day_file(day_file)
    try:
        start, end = find_entry_block(lines, entry_id)
    except EntryNotFoundError:
        print(
            f"Entry {entry_id} could not be located inside '{source_file}'. "
            "Run 'kaydet --doctor' to rebuild the index."
        )
        return

    entry_block = lines[start:end]
    preview_lines = entry_block[:5]
    preview = "\n".join(preview_lines)

    if not _confirm_delete(entry_id, preview, assume_yes=assume_yes):
        print("Deletion cancelled.")
        return

    del lines[start:end]

    ensure_newline = had_trailing_newline
    write_day_file(day_file, lines, ensure_newline)
    sync_modified_diary_files(db, log_dir, config, now)
    print(f"Deleted entry {entry_id} from {source_file}.")
    return {"entry_id": entry_id, "day_file": str(day_file)}
