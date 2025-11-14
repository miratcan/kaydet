"""Utilities for synchronizing diary files with the SQLite index."""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Dict, Iterable, List, Sequence

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
from .utils import DEFAULT_SETTINGS, get_file_glob_from_pattern

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


def _write_if_changed(
    day_file: Path, original_text: str, lines: List[str]
) -> bool:
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
    conn: sqlite3.Connection,
    day_file: Path,
    entries: List[Entry],
) -> List[Entry]:
    cursor = conn.cursor()
    assigned_ids: List[int] = []
    normalized: List[Entry] = []

    for entry in entries:
        entry_id_value: int | None = None

        if entry.entry_id and entry.entry_id.isdigit():
            candidate = int(entry.entry_id)
            cursor.execute(
                "SELECT source_file FROM entries WHERE id = ?",
                (candidate,),
            )
            row = cursor.fetchone()
            if row:
                (existing_source,) = row
                if existing_source == day_file.name:
                    entry_id_value = candidate
                    update_sql = (
                        "UPDATE entries "
                        "SET source_file = ?, timestamp = ? "
                        "WHERE id = ?"
                    )
                    cursor.execute(
                        update_sql,
                        (day_file.name, entry.timestamp, entry_id_value),
                    )
            else:
                entry_id_value = candidate
                insert_with_id_sql = (
                    "INSERT INTO entries (id, source_file, timestamp) "
                    "VALUES (?, ?, ?)"
                )
                cursor.execute(
                    insert_with_id_sql,
                    (entry_id_value, day_file.name, entry.timestamp),
                )
        if entry_id_value is None:
            insert_sql = (
                "INSERT INTO entries (source_file, timestamp) VALUES (?, ?)"
            )
            cursor.execute(insert_sql, (day_file.name, entry.timestamp))
            entry_id_value = cursor.lastrowid

        assigned_ids.append(entry_id_value)
        normalized.append(
            replace(
                entry,
                entry_id=str(entry_id_value),
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
    conn: sqlite3.Connection,
    entries: Iterable[Entry],
) -> None:
    """Refresh tags, words, and metadata rows for the provided entries."""

    cursor = conn.cursor()
    for entry in entries:
        if not entry.entry_id or not entry.entry_id.isdigit():
            continue
        entry_id_value = int(entry.entry_id)
        cursor.execute(
            "DELETE FROM tags WHERE entry_id = ?",
            (entry_id_value,),
        )
        cursor.execute(
            "DELETE FROM words WHERE entry_id = ?",
            (entry_id_value,),
        )
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


def sync_modified_diary_files(
    conn: sqlite3.Connection,
    log_dir: Path,
    config: Dict[str, str],
    now: datetime,
    *,
    force: bool = False,
) -> List[Path]:
    """Incrementally synchronize modified diary files with the SQLite index."""

    if not log_dir.exists():
        return []

    day_pattern = config.get(
        "DAY_FILE_PATTERN",
        DEFAULT_SETTINGS["DAY_FILE_PATTERN"],
    )
    glob_pattern = get_file_glob_from_pattern(day_pattern)

    cursor = conn.cursor()
    cursor.execute(
        "SELECT source_file, last_mtime FROM synced_files"
    )
    tracked: Dict[str, float] = {
        source_file: mtime for source_file, mtime in cursor.fetchall()
    }

    normalized_files: List[Path] = []

    for day_file in sorted(log_dir.glob(glob_pattern)):
        if not day_file.is_file():
            continue
        file_mtime = day_file.stat().st_mtime
        entry_date = resolve_entry_date(day_file, day_pattern)
        stored_mtime = tracked.get(day_file.name)
        needs_sync = force or stored_mtime is None or (
            abs(stored_mtime - file_mtime) > 1e-6
        )

        if not needs_sync:
            continue

        try:
            raw_text = day_file.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            raw_text = day_file.read_text(encoding="utf-8", errors="replace")
        lines = raw_text.splitlines()
        header_lines = _split_header(lines)
        entries = parse_day_entries(day_file, entry_date)
        conn.execute("BEGIN")
        try:
            normalized_entries = _normalize_entries(conn, day_file, entries)
            _reindex_entries(conn, normalized_entries)

            rendered_lines = list(header_lines)
            for entry in normalized_entries:
                rendered_lines.extend(_render_entry(entry))

            changed = _write_if_changed(day_file, raw_text, rendered_lines)
            if changed:
                normalized_files.append(day_file)
                file_mtime = day_file.stat().st_mtime

            cursor.execute(
                "INSERT INTO synced_files(source_file, last_mtime) "
                "VALUES(?, ?) "
                "ON CONFLICT(source_file) DO UPDATE SET "
                "last_mtime = excluded.last_mtime",
                (day_file.name, file_mtime),
            )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    if normalized_files:
        logger.info(
            "Normalized IDs in %s",
            ", ".join(str(path) for path in normalized_files),
        )
    return normalized_files
