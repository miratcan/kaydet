from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable

# Database schema version
# Increment this when making non-backward-compatible changes to the schema.
SCHEMA_VERSION = 2

PRAGMA_USER_VERSION = "PRAGMA user_version"

DROP_TABLE_STATEMENTS = (
    "DROP TABLE IF EXISTS entries",
    "DROP TABLE IF EXISTS tags",
    "DROP TABLE IF EXISTS words",
    "DROP TABLE IF EXISTS metadata",
    "DROP TABLE IF EXISTS synced_files",
)

CREATE_TABLE_ENTRIES = """
CREATE TABLE entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_uuid TEXT NOT NULL UNIQUE,
    source_file TEXT NOT NULL,
    timestamp TEXT NOT NULL
)
"""

CREATE_TABLE_TAGS = """
CREATE TABLE tags (
    entry_id INTEGER NOT NULL,
    tag_name TEXT NOT NULL,
    FOREIGN KEY (entry_id) REFERENCES entries(id) ON DELETE CASCADE,
    UNIQUE(entry_id, tag_name)
)
"""

CREATE_TABLE_WORDS = """
CREATE TABLE words (
    entry_id INTEGER NOT NULL,
    word TEXT NOT NULL,
    FOREIGN KEY (entry_id) REFERENCES entries(id) ON DELETE CASCADE
)
"""

CREATE_TABLE_METADATA = """
CREATE TABLE metadata (
    entry_id INTEGER NOT NULL,
    meta_key TEXT NOT NULL,
    meta_value TEXT NOT NULL,
    numeric_value REAL,
    FOREIGN KEY (entry_id) REFERENCES entries(id) ON DELETE CASCADE,
    UNIQUE(entry_id, meta_key)
)
"""

CREATE_TABLE_SYNCED_FILES = """
CREATE TABLE IF NOT EXISTS synced_files (
    path TEXT PRIMARY KEY,
    mtime REAL NOT NULL,
    needs_final_sync INTEGER NOT NULL DEFAULT 0
)
"""

CREATE_INDEX_STATEMENTS = (
    "CREATE INDEX idx_tags_tag_name ON tags(tag_name)",
    "CREATE INDEX idx_words_word ON words(word)",
    "CREATE INDEX idx_metadata_key_value "
    "ON metadata(meta_key, meta_value)",
    "CREATE INDEX idx_metadata_key_numeric "
    "ON metadata(meta_key, numeric_value)",
)

INSERT_TAG_SQL = "INSERT INTO tags (entry_id, tag_name) VALUES (?, ?)"
INSERT_WORD_SQL = "INSERT INTO words (entry_id, word) VALUES (?, ?)"
INSERT_METADATA_SQL = (
    "INSERT INTO metadata (entry_id, meta_key, meta_value, numeric_value) "
    "VALUES (?, ?, ?, ?)"
)


def get_db_connection(db_path: Path) -> sqlite3.Connection:
    """Establishes a connection to the SQLite database."""
    connection = sqlite3.connect(db_path, isolation_level=None)
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_database(db: sqlite3.Connection):
    """
    Initializes the database with the required schema, including tables for
    entries, tags, words, and metadata. Also sets up a versioning system.
    """
    cursor = db.cursor()

    # 1. Check and set schema version
    cursor.execute(PRAGMA_USER_VERSION)
    db_version = cursor.fetchone()[0]

    if db_version == 0:
        for statement in DROP_TABLE_STATEMENTS:
            cursor.execute(statement)

        cursor.execute(CREATE_TABLE_ENTRIES)
        cursor.execute(CREATE_TABLE_TAGS)
        cursor.execute(CREATE_TABLE_WORDS)
        cursor.execute(CREATE_TABLE_METADATA)
        cursor.execute(CREATE_TABLE_SYNCED_FILES)
        for statement in CREATE_INDEX_STATEMENTS:
            cursor.execute(statement)

        cursor.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        db.commit()
        return

    if db_version < 1:
        raise RuntimeError("Unsupported database version")

    if db_version < 2:
        cursor.execute(CREATE_TABLE_SYNCED_FILES)
        cursor.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        db.commit()
        return

    cursor.execute(CREATE_TABLE_SYNCED_FILES)


def add_entry(
    db: sqlite3.Connection,
    source_file: str,
    timestamp: str,
    tags: Iterable[str],
    words: Iterable[str],
    metadata: dict[str, tuple[str, float | None]],
    *,
    entry_id: int | None = None,
    entry_uuid: str | None = None,
) -> int:
    """Add an entry, with its tags, words, and metadata, in one transaction."""
    cursor = db.cursor()

    try:
        cursor.execute("BEGIN")

        # Insert the main entry record
        if entry_id is None:
            cursor.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM entries")
            entry_id = cursor.fetchone()[0]

        if entry_uuid is None:
            entry_uuid = f"{source_file}:{entry_id}"

        cursor.execute(
            "INSERT INTO entries (id, entry_uuid, source_file, timestamp) "
            "VALUES (?, ?, ?, ?)",
            (entry_id, entry_uuid, source_file, timestamp),
        )

        # Insert tags
        if tags:
            tag_data = [(entry_id, tag) for tag in set(tags)]
            cursor.executemany(INSERT_TAG_SQL, tag_data)

        # Insert words
        if words:
            word_data = [(entry_id, word) for word in set(words)]
            cursor.executemany(INSERT_WORD_SQL, word_data)

        # Insert metadata
        if metadata:
            meta_data = [
                (entry_id, key, value, num_value)
                for key, (value, num_value) in metadata.items()
            ]
            cursor.executemany(
                INSERT_METADATA_SQL,
                meta_data,
            )

        cursor.execute("COMMIT")
        return entry_id
    except sqlite3.Error as e:
        cursor.execute("ROLLBACK")
        raise e
