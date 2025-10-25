"""Utilities for synchronizing diary files with the SQLite index."""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Dict, Iterable, List, Sequence, Tuple

from . import database
from .models import Entry
from .parsers import (
    ENTRY_LINE_PATTERN,
    deduplicate_tags,
    extract_words_from_text,
    format_entry_header,
    parse_day_entries,
    resolve_entry_date,
)
from .utils import DEFAULT_SETTINGS


logger = logging.getLogger(__name__)


def _split_header(lines: Sequence[str]) -> List[str]:
    """Return the header lines preceding the first diary entry."""

    for index, line in enumerate(lines):
        if ENTRY_LINE_PATTERN.match(line):
            return list(lines[:index])
    return list(lines)


def _render_entry(entry: Entry) -> List[str]:
    """Return normalized lines for a diary entry with an ID block."""

    message = entry.lines[0] if entry.lines else ""
    inline_tags = set(deduplicate_tags([], entry.lines))
    explicit_markers = [
        tag for tag in entry.tags if tag not in inline_tags
    ]
    header_line = format_entry_header(
        entry.timestamp,
        message,
        entry.metadata,
        explicit_markers,
        entry_id=entry.entry_id,
    )
    rendered = [header_line]
    rendered.extend(entry.lines[1:])
    return rendered


def _write_if_changed(day_file: Path, original_text: str, lines: List[str]) -> bool:
    """Write the provided lines back to disk when content changes."""

    new_text = "\n".join(lines)
    if original_text.endswith("\n"):
        new_text = f"{new_text}\n"
    if new_text == original_text:
        return False
    temp_path = None
    try:
        with NamedTemporaryFile(
            "w", encoding="utf-8", dir=day_file.parent, delete=False
        ) as handle:
            handle.write(new_text)
            temp_path = Path(handle.name)
        temp_path.replace(day_file)
        return True
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink(missing_ok=True)


def _normalize_entries(
    db: sqlite3.Connection,
    day_file: Path,
    entries: List[Entry],
) -> List[Entry]:
    """Ensure each entry has an ID recorded in SQLite and return updates."""

    cursor = db.cursor()
    assigned_ids: List[int] = []
    normalized: List[Entry] = []

    for entry in entries:
        entry_id_value: int | None = None

        if entry.entry_id and entry.entry_id.isdigit():
            candidate = int(entry.entry_id)
            cursor.execute(
                "SELECT entry_uuid, source_file FROM entries WHERE id = ?",
                (candidate,),
            )
            row = cursor.fetchone()
            expected_uuid = entry.uuid
            expected_source = day_file.name
            if row:
                existing_uuid, existing_source = row
                if (
                    existing_uuid == expected_uuid
                    and existing_source == expected_source
                ):
                    entry_id_value = candidate
            else:
                cursor.execute(
                    "INSERT INTO entries (id, entry_uuid, source_file, timestamp) "
                    "VALUES (?, ?, ?, ?)",
                    (candidate, entry.uuid, day_file.name, entry.timestamp),
                )
                entry_id_value = candidate

        if entry_id_value is None:
            cursor.execute(
                "SELECT id FROM entries WHERE entry_uuid = ?",
                (entry.uuid,),
            )
            match = cursor.fetchone()
            if match:
                entry_id_value = match[0]
            else:
                cursor.execute(
                    "INSERT INTO entries (entry_uuid, source_file, timestamp) "
                    "VALUES (?, ?, ?)",
                    (entry.uuid, day_file.name, entry.timestamp),
                )
                entry_id_value = cursor.lastrowid

        entry_uuid_value = f"{day_file.name}:{entry_id_value}"
        cursor.execute(
            "UPDATE entries SET entry_uuid = ?, source_file = ?, timestamp = ? "
            "WHERE id = ?",
            (entry_uuid_value, day_file.name, entry.timestamp, entry_id_value),
        )

        assigned_ids.append(entry_id_value)
        normalized.append(
            replace(
                entry,
                entry_id=str(entry_id_value),
                uuid=entry_uuid_value,
            )
        )

    existing_ids: set[int] = set(
        row[0]
        for row in cursor.execute(
            "SELECT id FROM entries WHERE source_file = ?",
            (day_file.name,),
        )
    )
    missing = existing_ids.difference(assigned_ids)
    if missing:
        payload = [(entry_id,) for entry_id in missing]
        cursor.executemany("DELETE FROM tags WHERE entry_id = ?", payload)
        cursor.executemany("DELETE FROM words WHERE entry_id = ?", payload)
        cursor.executemany("DELETE FROM metadata WHERE entry_id = ?", payload)
        cursor.executemany("DELETE FROM entries WHERE id = ?", payload)

    return normalized


def _reindex_entries(
    db: sqlite3.Connection,
    entries: Iterable[Entry],
) -> None:
    """Refresh tags, words, and metadata rows for the provided entries."""

    cursor = db.cursor()
    for entry in entries:
        if not entry.entry_id or not entry.entry_id.isdigit():
            continue
        entry_id_value = int(entry.entry_id)
        cursor.execute("DELETE FROM tags WHERE entry_id = ?", (entry_id_value,))
        cursor.execute("DELETE FROM words WHERE entry_id = ?", (entry_id_value,))
        cursor.execute(
            "DELETE FROM metadata WHERE entry_id = ?",
            (entry_id_value,),
        )

        if entry.tags:
            cursor.executemany(
                database.INSERT_TAG_SQL,
                [(entry_id_value, tag) for tag in set(entry.tags)],
            )

        words = extract_words_from_text(entry.text)
        if words:
            cursor.executemany(
                database.INSERT_WORD_SQL,
                [(entry_id_value, word) for word in set(words)],
            )

        if entry.metadata:
            cursor.executemany(
                database.INSERT_METADATA_SQL,
                [
                    (
                        entry_id_value,
                        key,
                        value,
                        entry.metadata_numbers.get(key),
                    )
                    for key, value in entry.metadata.items()
                ],
            )


def synchronize_diary(
    db: sqlite3.Connection,
    log_dir: Path,
    config: Dict[str, str],
    now: datetime,
    *,
    force: bool = False,
    process_today: bool = False,
) -> List[Path]:
    """Synchronize modified diary files with the SQLite index."""

    if not log_dir.exists():
        return []

    day_pattern = config.get(
        "DAY_FILE_PATTERN",
        DEFAULT_SETTINGS["DAY_FILE_PATTERN"],
    )

    cursor = db.cursor()
    cursor.execute(
        "SELECT path, mtime, needs_final_sync FROM synced_files"
    )
    tracked: Dict[str, Tuple[float, int]] = {
        path: (mtime, needs)
        for path, mtime, needs in cursor.fetchall()
    }

    normalized_files: List[Path] = []

    for day_file in sorted(log_dir.glob("*.txt")):
        if not day_file.is_file():
            continue
        file_mtime = day_file.stat().st_mtime
        entry_date = resolve_entry_date(day_file, day_pattern)
        record = tracked.get(day_file.name)
        needs_sync = force or record is None
        pending_flag = 0

        if not needs_sync and record is not None:
            stored_mtime, pending = record
            pending_flag = pending
            if abs(stored_mtime - file_mtime) > 1e-6:
                needs_sync = True
            elif pending and entry_date and entry_date < now.date():
                needs_sync = True

        if not needs_sync:
            continue

        try:
            raw_text = day_file.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            raw_text = day_file.read_text(encoding="utf-8", errors="replace")
        lines = raw_text.splitlines()
        header_lines = _split_header(lines)
        entries = parse_day_entries(day_file, entry_date)
        had_missing_ids = any(
            not (entry.entry_id and entry.entry_id.isdigit()) for entry in entries
        )

        db.execute("BEGIN")
        try:
            normalized_entries = _normalize_entries(db, day_file, entries)
            _reindex_entries(db, normalized_entries)

            rendered_lines = list(header_lines)
            for entry in normalized_entries:
                rendered_lines.extend(_render_entry(entry))

            skip_today = False
            if (
                entry_date
                and entry_date == now.date()
                and not process_today
                and had_missing_ids
            ):
                skip_today = True

            if skip_today:
                pending_flag = 1
            else:
                changed = _write_if_changed(day_file, raw_text, rendered_lines)
                if changed:
                    normalized_files.append(day_file)
                    file_mtime = day_file.stat().st_mtime
                pending_flag = 0

            cursor.execute(
                "INSERT INTO synced_files(path, mtime, needs_final_sync) "
                "VALUES(?, ?, ?) "
                "ON CONFLICT(path) DO UPDATE SET mtime=excluded.mtime, "
                "needs_final_sync=excluded.needs_final_sync",
                (day_file.name, file_mtime, pending_flag),
            )
            db.execute("COMMIT")
        except Exception:
            db.execute("ROLLBACK")
            raise
    if normalized_files:
        logger.info(
            "Normalized IDs in %s",
            ", ".join(str(path) for path in normalized_files),
        )
    return normalized_files
