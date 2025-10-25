"""Doctor command - rebuild search index."""

import shutil
import sqlite3
from configparser import SectionProxy
from datetime import datetime
from pathlib import Path

from ..parsers import TAG_PATTERN
from ..sync import synchronize_diary


def doctor_command(
    db: sqlite3.Connection, log_dir: Path, config: SectionProxy, now: datetime
):
    """Rebuild the SQLite index while normalizing diary entry IDs."""
    print(
        "Rebuilding search index from diary files... This may take a moment."
    )

    for table in ["tags", "words", "metadata"]:
        db.execute(f"DELETE FROM {table}")
    db.commit()

    synchronize_diary(
        db,
        log_dir,
        config,
        now,
        force=True,
        process_today=True,
    )

    cursor = db.cursor()
    cursor.execute("SELECT COUNT(*) FROM entries")
    total_entries = cursor.fetchone()[0]

    if log_dir.exists():
        for child in log_dir.iterdir():
            if child.is_dir() and TAG_PATTERN.fullmatch(child.name):
                shutil.rmtree(child)

    entry_label = "entry" if total_entries == 1 else "entries"
    print(f"Rebuilt search index for {total_entries} {entry_label}.")

    cursor.execute(
        """
        SELECT tag_name, COUNT(*) as count
        FROM tags
        GROUP BY tag_name
        ORDER BY tag_name
        """
    )
    tag_stats = cursor.fetchall()
    if tag_stats:
        tag_list = ", ".join(f"#{tag}: {count}" for tag, count in tag_stats)
        print(f"Tags: {tag_list}")
