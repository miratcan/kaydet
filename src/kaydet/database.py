
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable

# Database schema version
# Increment this when making non-backward-compatible changes to the schema.
SCHEMA_VERSION = 1

def get_db_connection(db_path: Path) -> sqlite3.Connection:
    """Establishes a connection to the SQLite database."""
    return sqlite3.connect(db_path, isolation_level=None) # Autocommit mode

def initialize_database(db: sqlite3.Connection):
    """
    Initializes the database with the required schema, including tables for
    entries, tags, words, and metadata. Also sets up a versioning system.
    """
    cursor = db.cursor()

    # 1. Check and set schema version
    cursor.execute("PRAGMA user_version")
    db_version = cursor.fetchone()[0]

    if db_version >= SCHEMA_VERSION:
        return # Database is already up to date

    # For a fresh start or upgrade, we drop old tables and recreate.
    # A more complex migration system could be built here for future versions.
    cursor.execute("DROP TABLE IF EXISTS entries")
    cursor.execute("DROP TABLE IF EXISTS tags")
    cursor.execute("DROP TABLE IF EXISTS words")
    cursor.execute("DROP TABLE IF EXISTS metadata")

    # 2. Create tables
    # entries: Core table linking a unique ID to a physical location in a text file.
    cursor.execute("""
        CREATE TABLE entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_uuid TEXT NOT NULL UNIQUE,
            source_file TEXT NOT NULL,
            timestamp TEXT NOT NULL
        )
    """)

    # tags: Associates tags with entries.
    cursor.execute("""
        CREATE TABLE tags (
            entry_id INTEGER NOT NULL,
            tag_name TEXT NOT NULL,
            FOREIGN KEY (entry_id) REFERENCES entries(id) ON DELETE CASCADE,
            UNIQUE(entry_id, tag_name)
        )
    """)
    cursor.execute("CREATE INDEX idx_tags_tag_name ON tags(tag_name)")

    # words: For full-text search indexing.
    cursor.execute("""
        CREATE TABLE words (
            entry_id INTEGER NOT NULL,
            word TEXT NOT NULL,
            FOREIGN KEY (entry_id) REFERENCES entries(id) ON DELETE CASCADE
        )
    """)
    cursor.execute("CREATE INDEX idx_words_word ON words(word)")

    # metadata: Stores key-value pairs, including a pre-calculated numeric value.
    cursor.execute("""
        CREATE TABLE metadata (
            entry_id INTEGER NOT NULL,
            meta_key TEXT NOT NULL,
            meta_value TEXT NOT NULL,
            numeric_value REAL,
            FOREIGN KEY (entry_id) REFERENCES entries(id) ON DELETE CASCADE,
            UNIQUE(entry_id, meta_key)
        )
    """)
    cursor.execute("CREATE INDEX idx_metadata_key_value ON metadata(meta_key, meta_value)")
    cursor.execute("CREATE INDEX idx_metadata_key_numeric ON metadata(meta_key, numeric_value)")


    # 3. Set the new schema version
    cursor.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    db.commit()

def add_entry(
    db: sqlite3.Connection,
    entry_uuid: str,
    source_file: str,
    timestamp: str,
    tags: Iterable[str],
    words: Iterable[str],
    metadata: dict[str, tuple[str, float | None]]
) -> int:
    """
    Adds a new entry and its associated tags, words, and metadata to the database
    within a single transaction.

    Returns:
        The ID of the newly inserted entry.
    """
    cursor = db.cursor()
    
    try:
        cursor.execute("BEGIN")

        # Insert the main entry record
        cursor.execute(
            "INSERT INTO entries (entry_uuid, source_file, timestamp) VALUES (?, ?, ?)",
            (entry_uuid, source_file, timestamp)
        )
        entry_id = cursor.lastrowid

        # Insert tags
        if tags:
            tag_data = [(entry_id, tag) for tag in set(tags)]
            cursor.executemany("INSERT INTO tags (entry_id, tag_name) VALUES (?, ?)", tag_data)

        # Insert words
        if words:
            word_data = [(entry_id, word) for word in set(words)]
            cursor.executemany("INSERT INTO words (entry_id, word) VALUES (?, ?)", word_data)

        # Insert metadata
        if metadata:
            meta_data = [
                (entry_id, key, value, num_value)
                for key, (value, num_value) in metadata.items()
            ]
            cursor.executemany(
                "INSERT INTO metadata (entry_id, meta_key, meta_value, numeric_value) VALUES (?, ?, ?, ?)",
                meta_data
            )
        
        cursor.execute("COMMIT")
        return entry_id
    except sqlite3.Error as e:
        cursor.execute("ROLLBACK")
        raise e

