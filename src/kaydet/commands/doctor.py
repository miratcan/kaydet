"""Doctor command - rebuild search index."""

import shutil
import sqlite3
from configparser import SectionProxy
from pathlib import Path

from .. import database
from ..parsers import TAG_PATTERN, extract_words_from_text
from ..utils import iter_diary_entries


def doctor_command(db: sqlite3.Connection, log_dir: Path, config: SectionProxy):
    """Rebuild the SQLite index from all existing diary files."""
    print("Rebuilding search index from diary files... This may take a moment.")
    for table in ["entries", "tags", "words", "metadata"]:
        db.execute(f"DELETE FROM {table}")
    db.commit()

    total_entries = 0
    for entry in iter_diary_entries(log_dir, config):
        words = extract_words_from_text(entry.text)
        full_metadata = {
            key: (value, num_value)
            for key, num_value in entry.metadata_numbers.items()
            if (value := entry.metadata.get(key)) is not None
        }
        database.add_entry(
            db=db,
            entry_uuid=entry.uuid,
            source_file=entry.source.name,
            timestamp=entry.timestamp,
            tags=entry.tags,
            words=words,
            metadata=full_metadata,
        )
        total_entries += 1

    if log_dir.exists():
        for child in log_dir.iterdir():
            if child.is_dir() and TAG_PATTERN.fullmatch(child.name):
                shutil.rmtree(child)

    print(f"Rebuilt search index for {total_entries} {'entry' if total_entries == 1 else 'entries'}.")

    # Print tag statistics
    cursor = db.cursor()
    cursor.execute("""
        SELECT tag_name, COUNT(*) as count
        FROM tags
        GROUP BY tag_name
        ORDER BY tag_name
    """)
    tag_stats = cursor.fetchall()
    if tag_stats:
        tag_list = ", ".join(f"#{tag}: {count}" for tag, count in tag_stats)
        print(f"Tags: {tag_list}")
