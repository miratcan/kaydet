from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_VERSION = 6
INDEX_FILENAME = "index.db"

PRAGMA_USER_VERSION = "PRAGMA user_version"

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

CREATE_TABLE_SYNCED_FILES = """
CREATE TABLE IF NOT EXISTS synced_files (
    source_file TEXT PRIMARY KEY,
    last_mtime REAL NOT NULL
)
"""

LOG_SYNC_ACTION_SQL = (
    "INSERT INTO sync_log (entry_id, action, device_id, created_at) "
    "VALUES (?, ?, ?, datetime('now'))"
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


def get_db_connection(db_path: Path, check_same_thread: bool = True) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path, isolation_level=None, check_same_thread=check_same_thread)
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_database(conn: sqlite3.Connection) -> None:
    cursor = conn.cursor()
    cursor.execute(PRAGMA_USER_VERSION)
    db_version = cursor.fetchone()[0]

    if db_version != SCHEMA_VERSION:
        # Drop legacy index tables — Rust core owns the index now.
        for table in ("entries", "tags", "entries_fts", "metadata", "synced_files"):
            cursor.execute(f"DROP TABLE IF EXISTS {table}")
        cursor.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        conn.commit()

    cursor.execute(CREATE_TABLE_SYNC_LOG)
    cursor.execute(CREATE_TABLE_SYNC_KEYS)
    cursor.execute(CREATE_TABLE_SYNCED_FILES)
