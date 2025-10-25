"""Helpers for maintaining the SQLite search index."""

from __future__ import annotations

import sqlite3
from configparser import SectionProxy
from datetime import datetime
from pathlib import Path

from .commands.doctor import doctor_command

SELECT_ENTRY_COUNT_SQL = "SELECT COUNT(*) FROM entries"


def rebuild_index_if_empty(
    db: sqlite3.Connection,
    log_dir: Path,
    config: SectionProxy,
    current_time: datetime | None = None,
) -> None:
    """Trigger a doctor rebuild when the index tables are empty."""

    cursor = db.cursor()
    cursor.execute(SELECT_ENTRY_COUNT_SQL)
    entry_count = cursor.fetchone()[0]
    if entry_count != 0 or not log_dir.exists():
        return
    if not any(log_dir.glob("*.txt")):
        return

    print("Search index is empty. Rebuilding from existing files...")
    timestamp = current_time or datetime.now()
    doctor_command(db, log_dir, config, timestamp)
    print()
