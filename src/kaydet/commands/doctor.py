"""Doctor command - rebuild search index."""

import shutil
import sqlite3
from configparser import SectionProxy
from datetime import datetime
from pathlib import Path

from ..parsers import TAG_PATTERN
from ..sync import sync_modified_diary_files

DELETE_INDEX_TABLES = ("tags", "words", "metadata")
DELETE_TABLE_TEMPLATE = "DELETE FROM {table}"
DELETE_ENTRIES_SQL = "DELETE FROM entries"
DELETE_SYNCED_FILES_SQL = "DELETE FROM synced_files"
SELECT_ENTRY_COUNT_SQL = "SELECT COUNT(*) FROM entries"
SELECT_TAG_STATS_SQL = """
SELECT tag_name, COUNT(*) as count
FROM tags
GROUP BY tag_name
ORDER BY tag_name
"""


def doctor_command(
    db: sqlite3.Connection, log_dir: Path, config: SectionProxy, now: datetime
):
    """Rebuild the SQLite index while normalizing diary entry IDs."""
    print(
        "Rebuilding search index from diary files... This may take a moment."
    )

    for table in DELETE_INDEX_TABLES:
        db.execute(DELETE_TABLE_TEMPLATE.format(table=table))
    db.execute(DELETE_ENTRIES_SQL)
    db.execute(DELETE_SYNCED_FILES_SQL)
    db.commit()

    normalized = sync_modified_diary_files(
        db,
        log_dir,
        config,
        now,
        force=True,
    )
    for changed in normalized:
        print(f"Normalized IDs in {changed}")

    cursor = db.cursor()
    cursor.execute(SELECT_ENTRY_COUNT_SQL)
    total_entries = cursor.fetchone()[0]

    if log_dir.exists():
        for child in log_dir.iterdir():
            if child.is_dir() and TAG_PATTERN.fullmatch(child.name):
                shutil.rmtree(child)

    entry_label = "entry" if total_entries == 1 else "entries"
    print(f"Rebuilt search index for {total_entries} {entry_label}.")

    cursor.execute(SELECT_TAG_STATS_SQL)
    tag_stats = cursor.fetchall()
    if tag_stats:
        tag_list = ", ".join(f"#{tag}: {count}" for tag, count in tag_stats)
        print(f"Tags: {tag_list}")
