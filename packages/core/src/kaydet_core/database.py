from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable

# Database schema version
# Increment when we intentionally drop and recreate the schema.
SCHEMA_VERSION = 5

INDEX_FILENAME = "index.db"

# Legacy migrations kept a user_version pragma, but SQLite is purely an
# index/cache for Kaydet. We can safely drop and recreate tables whenever the
# schema changes instead of juggling ALTER statements.
PRAGMA_USER_VERSION = "PRAGMA user_version"

DROP_TABLE_STATEMENTS = (
    "DROP TABLE IF EXISTS entries",
    "DROP TABLE IF EXISTS tags",
    "DROP TABLE IF EXISTS entries_fts",
    "DROP TABLE IF EXISTS metadata",
    "DROP TABLE IF EXISTS synced_files",
)

CREATE_TABLE_ENTRIES = """
CREATE TABLE entries (
    id TEXT PRIMARY KEY,
    source_file TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    updated_at TEXT
)
"""

CREATE_TABLE_TAGS = """
CREATE TABLE tags (
    entry_id TEXT NOT NULL,
    tag_name TEXT NOT NULL,
    FOREIGN KEY (entry_id) REFERENCES entries(id) ON DELETE CASCADE,
    UNIQUE(entry_id, tag_name)
)
"""

CREATE_VIRTUAL_TABLE_FTS = """
CREATE VIRTUAL TABLE entries_fts USING fts5(
    entry_id UNINDEXED,
    body,
)
"""

CREATE_TABLE_METADATA = """
CREATE TABLE metadata (
    entry_id TEXT NOT NULL,
    meta_key TEXT NOT NULL,
    meta_value TEXT NOT NULL,
    numeric_value REAL,
    FOREIGN KEY (entry_id) REFERENCES entries(id) ON DELETE CASCADE,
    UNIQUE(entry_id, meta_key)
)
"""

CREATE_TABLE_SYNCED_FILES = """
CREATE TABLE IF NOT EXISTS synced_files (
    source_file TEXT PRIMARY KEY,
    last_mtime REAL NOT NULL
)
"""

CREATE_TABLE_SYNC_LOG = """
CREATE TABLE IF NOT EXISTS sync_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id TEXT NOT NULL,
    action TEXT NOT NULL,
    device_id TEXT,
    created_at TEXT NOT NULL
)
"""

CREATE_TABLE_SYNC_KEYS = """
CREATE TABLE IF NOT EXISTS sync_keys (
    key TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    last_used_at TEXT
)
"""

LOG_SYNC_ACTION_SQL = (
    "INSERT INTO sync_log (entry_id, action, device_id, created_at) "
    "VALUES (?, ?, ?, datetime('now'))"
)

CREATE_INDEX_STATEMENTS = (
    "CREATE INDEX idx_tags_tag_name ON tags(tag_name)",
    "CREATE INDEX idx_metadata_key_value ON metadata(meta_key, meta_value)",
    "CREATE INDEX idx_metadata_key_numeric "
    "ON metadata(meta_key, numeric_value)",
)

INSERT_ENTRY_SQL = (
    "INSERT INTO entries (id, source_file, timestamp, updated_at) "
    "VALUES (?, ?, ?, datetime('now'))"
)
SELECT_ENTRY_BY_ID_SQL = "SELECT source_file FROM entries WHERE id = ?"
UPDATE_ENTRY_SQL = (
    "UPDATE entries SET source_file = ?, timestamp = ?, "
    "updated_at = datetime('now') WHERE id = ?"
)

INSERT_TAG_SQL = "INSERT INTO tags (entry_id, tag_name) VALUES (?, ?)"
INSERT_FTS_SQL = "INSERT INTO entries_fts (entry_id, body) VALUES (?, ?)"
INSERT_METADATA_SQL = (
    "INSERT INTO metadata (entry_id, meta_key, meta_value, numeric_value) "
    "VALUES (?, ?, ?, ?)"
)

UPSERT_SYNCED_FILE_SQL = (
    "INSERT INTO synced_files(source_file, last_mtime) VALUES (?, ?) "
    "ON CONFLICT(source_file) DO UPDATE SET last_mtime = excluded.last_mtime"
)
SELECT_SYNCED_FILES_SQL = "SELECT source_file, last_mtime FROM synced_files"


def log_sync_action(
    conn: sqlite3.Connection,
    entry_id: str,
    action: str,
    device_id: str | None = None,
) -> None:
    """Record a mutation in the sync log."""
    conn.execute(LOG_SYNC_ACTION_SQL, (entry_id, action, device_id))


def get_db_connection(db_path: Path) -> sqlite3.Connection:
    """Establishes a connection to the SQLite database."""
    connection = sqlite3.connect(db_path, isolation_level=None)
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_database(conn: sqlite3.Connection):
    """
    Initializes the database with the required schema, including tables for
    entries, tags, FTS, and metadata. Also sets up a versioning system.
    """
    cursor = conn.cursor()

    # 1. Check and set schema version
    cursor.execute(PRAGMA_USER_VERSION)
    db_version = cursor.fetchone()[0]

    if db_version != SCHEMA_VERSION:
        for statement in DROP_TABLE_STATEMENTS:
            cursor.execute(statement)

        cursor.execute(CREATE_TABLE_ENTRIES)
        cursor.execute(CREATE_TABLE_TAGS)
        cursor.execute(CREATE_VIRTUAL_TABLE_FTS)
        cursor.execute(CREATE_TABLE_METADATA)
        cursor.execute(CREATE_TABLE_SYNCED_FILES)
        cursor.execute(CREATE_TABLE_SYNC_LOG)
        cursor.execute(CREATE_TABLE_SYNC_KEYS)

        for statement in CREATE_INDEX_STATEMENTS:
            cursor.execute(statement)

        cursor.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        conn.commit()
        return

    cursor.execute(CREATE_TABLE_SYNCED_FILES)
    cursor.execute(CREATE_TABLE_SYNC_LOG)
    cursor.execute(CREATE_TABLE_SYNC_KEYS)


def _ensure_entry_id(
    cursor: sqlite3.Cursor,
    source_file: str,
    timestamp: str,
    entry_id: str,
) -> tuple[str, bool]:
    """
    Ensure an entry exists in the database and return its ID.

    Returns:
        tuple[str, bool]: (entry_id, is_created) where is_created indicates
                         whether a new entry was created (True) or an existing
                         entry was updated (False).
    """
    cursor.execute(SELECT_ENTRY_BY_ID_SQL, (entry_id,))
    entry_on_db = cursor.fetchone()

    if entry_on_db:
        cursor.execute(UPDATE_ENTRY_SQL, (source_file, timestamp, entry_id))
        return entry_id, False

    cursor.execute(
        INSERT_ENTRY_SQL, (entry_id, source_file, timestamp)
    )
    return entry_id, True


def _upsert_source_records(
    cursor: sqlite3.Cursor,
    entry_id: str,
    tags: Iterable[str],
    body: str,
    metadata: dict[str, tuple[str, float | None]],
) -> None:
    """Upsert tags, FTS data, and metadata for an entry."""
    if tags:
        tag_data = [(entry_id, tag) for tag in set(tags)]
        cursor.executemany(INSERT_TAG_SQL, tag_data)

    if body:
        cursor.execute(INSERT_FTS_SQL, (entry_id, body))

    if metadata:
        meta_data = [
            (entry_id, key, value, num_value)
            for key, (value, num_value) in metadata.items()
        ]
        cursor.executemany(INSERT_METADATA_SQL, meta_data)


def _add_entry_to_cursor(
    cursor: sqlite3.Cursor,
    source_file: str,
    timestamp: str,
    tags: Iterable[str],
    body: str,
    metadata: dict[str, tuple[str, float | None]],
    *,
    entry_id: str,
) -> str:
    """Internal helper to add entry data to a cursor without committing."""
    # Ensure entry exists and get its ID
    entry_id, _ = _ensure_entry_id(cursor, source_file, timestamp, entry_id)

    # Upsert source records (tags, FTS, metadata)
    _upsert_source_records(cursor, entry_id, tags, body, metadata)

    return entry_id


def add_entry(
    conn: sqlite3.Connection,
    source_file: str,
    timestamp: str,
    tags: Iterable[str],
    body: str,
    metadata: dict[str, tuple[str, float | None]],
    *,
    entry_id: str,
) -> str:
    """Add an entry in a single atomic database transaction."""
    cursor = conn.cursor()
    try:
        cursor.execute("BEGIN")
        eid = _add_entry_to_cursor(
            cursor,
            source_file,
            timestamp,
            tags,
            body,
            metadata,
            entry_id=entry_id,
        )
        cursor.execute("COMMIT")
        return eid
    except sqlite3.Error as e:
        cursor.execute("ROLLBACK")
        raise e
