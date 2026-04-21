"""Utilities for synchronizing day files with the SQLite index."""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import List, Sequence

from .models import Entry
from .parsers import (
    ENTRY_LINE_PATTERN,
    deduplicate_tags,
    format_entry_header,
    parse_day_entries,
    resolve_entry_date,
)
from .utils import DEFAULT_SETTINGS, get_file_glob_from_pattern

logger = logging.getLogger(__name__)


def _split_header(lines: Sequence[str]) -> List[str]:
    """Return the header lines preceding the first entry."""
    for index, line in enumerate(lines):
        if ENTRY_LINE_PATTERN.match(line):
            return list(lines[:index])
    return list(lines)


def _render_entry(entry: Entry) -> List[str]:
    """Return normalized lines for a entry with an ID block."""
    message = entry.lines[0] if entry.lines else ""
    inline_tags = set(deduplicate_tags([], entry.lines))
    explicit_markers = [tag for tag in entry.tags if tag not in inline_tags]
    header = format_entry_header(
        entry.timestamp,
        message,
        entry.metadata,
        explicit_markers,
        entry_id=entry.entry_id,
        attachments=entry.attachments,
    )
    return [header] + list(entry.lines[1:])


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
        if temp_path and temp_path.exists():
            temp_path.unlink(missing_ok=True)


def _upsert_entry_record(
    cursor: sqlite3.Cursor,
    day_file_name: str,
    entry: Entry,
    updated_at: str | None = None,
    config: SectionProxy | None = None,
    config_dir: Path | None = None,
) -> str:
    """Ensure an entry record exists in the database and return its ID."""
    entry_id = entry.entry_id
    if not entry_id:
        if config and config_dir:
            from .utils import generate_next_id
            entry_id = generate_next_id(config, config_dir)
        else:
            # Fallback for transient environments (e.g. some tests)
            import hashlib
            content = f"{day_file_name}:{entry.timestamp}:{entry.text}"
            entry_id = "transient_" + hashlib.md5(content.encode()).hexdigest()[:8]

    cursor.execute(
        "SELECT source_file FROM entries WHERE id = ?",
        (entry_id,),
    )
    if row := cursor.fetchone():
        if row[0] == day_file_name:
            sql = (
                "UPDATE entries SET source_file = ?, "
                "timestamp = ? WHERE id = ?"
            )
            params: list[Any] = [day_file_name, entry.timestamp, entry_id]
            if updated_at:
                sql = (
                    "UPDATE entries SET source_file = ?, "
                    "timestamp = ?, updated_at = ? WHERE id = ?"
                )
                params = [
                    day_file_name,
                    entry.timestamp,
                    updated_at,
                    entry_id,
                ]
            cursor.execute(sql, params)
            return entry_id
        else:
            # ID exists but in a different file — conflict.
            # Generate a new unique ID to resolve it.
            if config and config_dir:
                from .utils import generate_next_id
                entry_id = generate_next_id(config, config_dir)
            else:
                import hashlib
                content = f"{day_file_name}:{entry.timestamp}:{entry.text}"
                entry_id = "x_" + hashlib.sha256(
                    content.encode()
                ).hexdigest()[:10]
            return _upsert_entry_record(
                cursor, day_file_name,
                replace(entry, entry_id=entry_id),
                updated_at, config, config_dir,
            )

    sql = (
        "INSERT INTO entries (id, source_file, timestamp) "
        "VALUES (?, ?, ?)"
    )
    params = [entry_id, day_file_name, entry.timestamp]
    if updated_at:
        sql = (
            "INSERT INTO entries (id, source_file, timestamp, updated_at) "
            "VALUES (?, ?, ?, ?)"
        )
        params.append(updated_at)
    cursor.execute(sql, params)
    return entry_id


def _cleanup_missing_entries(
    cursor: sqlite3.Cursor, day_file_name: str, assigned_ids: List[str]
) -> None:
    """Remove records for entries that no longer exist in the file."""
    cursor.execute(
        "SELECT id FROM entries WHERE source_file = ?",
        (day_file_name,),
    )
    existing_ids = {row[0] for row in cursor.fetchall()}
    missing = existing_ids.difference(assigned_ids)

    if not missing:
        return

    payload = [(eid,) for eid in missing]
    cursor.executemany("DELETE FROM tags WHERE entry_id = ?", payload)
    cursor.executemany("DELETE FROM entries_fts WHERE entry_id = ?", payload)
    cursor.executemany("DELETE FROM metadata WHERE entry_id = ?", payload)
    cursor.executemany("DELETE FROM entries WHERE id = ?", payload)


def _normalize_entries(
    conn: sqlite3.Connection,
    day_file: Path,
    entries: List[Entry],
    updated_at: str | None = None,
    config: SectionProxy | None = None,
    config_dir: Path | None = None,
) -> List[Entry]:
    """Sync entries with database and clean up the database."""
    cursor = conn.cursor()
    assigned_ids: List[str] = []
    normalized: List[Entry] = []

    for entry in entries:
        eid = _upsert_entry_record(
            cursor, 
            day_file.name, 
            entry, 
            updated_at=updated_at,
            config=config,
            config_dir=config_dir
        )
        assigned_ids.append(eid)
        normalized.append(replace(entry, entry_id=eid))

    _cleanup_missing_entries(cursor, day_file.name, assigned_ids)
    return normalized




def _sync_single_file(
    conn: sqlite3.Connection,
    day_file: Path,
    day_pattern: str,
    config: SectionProxy | None = None,
    config_dir: Path | None = None,
) -> bool:
    """Sync a single day file. Returns True if file was modified on disk."""
    try:
        raw_text = day_file.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raw_text = day_file.read_text(encoding="utf-8", errors="replace")

    entry_date = resolve_entry_date(day_file, day_pattern)
    entries = parse_day_entries(day_file, entry_date)
    header_lines = _split_header(raw_text.splitlines())

    # Use file mtime as the updated_at timestamp for entries
    mtime = day_file.stat().st_mtime
    updated_at = datetime.fromtimestamp(mtime).isoformat()

    conn.execute("BEGIN")
    try:
        normalized = _normalize_entries(
            conn,
            day_file,
            entries,
            updated_at=updated_at,
            config=config,
            config_dir=config_dir
        )

        rendered = list(header_lines)
        for entry in normalized:
            rendered.extend(_render_entry(entry))

        changed = _write_if_changed(day_file, raw_text, rendered)

        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO synced_files(source_file, last_mtime) VALUES(?, ?) "
            "ON CONFLICT(source_file) DO UPDATE "
            "SET last_mtime = excluded.last_mtime",
            (day_file.name, mtime),
        )
        conn.execute("COMMIT")
        return changed
    except Exception:
        conn.execute("ROLLBACK")
        raise


def sync_modified_day_files(
    conn: sqlite3.Connection,
    storage_dir: Path,
    config: SectionProxy,
    now: datetime,
    *,
    config_dir: Path | None = None,
    force: bool = False,
) -> List[Path]:
    """Incrementally synchronize modified day files with the SQLite index.

    No-op when the Rust core is active (it maintains its own in-memory index).
    """
    try:
        import kaydet_core_rs  # noqa: F401
        return []
    except ImportError:
        pass

    if not storage_dir.exists():
        return []

    day_pattern = config.get(
        "DAY_FILE_PATTERN", DEFAULT_SETTINGS["DAY_FILE_PATTERN"]
    )
    glob_pattern = get_file_glob_from_pattern(day_pattern)

    cursor = conn.cursor()
    cursor.execute("SELECT source_file, last_mtime FROM synced_files")
    tracked = {row[0]: row[1] for row in cursor.fetchall()}

    normalized_files: List[Path] = []

    for day_file in sorted(storage_dir.glob(glob_pattern)):
        if not day_file.is_file():
            continue

        stored_mtime = tracked.get(day_file.name)
        needs_sync = (
            force
            or stored_mtime is None
            or (
                abs(stored_mtime - day_file.stat().st_mtime)
                > 1e-6
            )
        )

        if not needs_sync:
            continue

        if _sync_single_file(
            conn, 
            day_file, 
            day_pattern, 
            config=config, 
            config_dir=config_dir
        ):
            normalized_files.append(day_file)

    if normalized_files:
        logger.info(
            "Normalized IDs in %s",
            ", ".join(str(p) for p in normalized_files),
        )

    return normalized_files
