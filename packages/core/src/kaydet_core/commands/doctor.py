"""Doctor command - rebuild search index."""

import re
import shutil
import sqlite3
from configparser import SectionProxy
from datetime import datetime
from pathlib import Path

from ..parsers import TAG_PATTERN
from ..sync import sync_modified_day_files
from ..utils import save_config_setting

DELETE_INDEX_TABLES = ("tags", "entries_fts", "metadata")
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
    conn: sqlite3.Connection,
    storage_dir: Path,
    config: SectionProxy,
    now: datetime,
    config_dir: Path | None = None,
) -> dict:
    """Rebuild the SQLite index while normalizing entry IDs."""
    results = []

    conn.execute("BEGIN")
    try:
        for table in DELETE_INDEX_TABLES:
            conn.execute(DELETE_TABLE_TEMPLATE.format(table=table))
        conn.execute(DELETE_ENTRIES_SQL)
        conn.execute(DELETE_SYNCED_FILES_SQL)
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise

    normalized = sync_modified_day_files(
        conn,
        storage_dir,
        config,
        now,
        config_dir=config_dir,
        force=True,
    )
    for changed in normalized:
        results.append(f"Normalized IDs in {changed}")

    cursor = conn.cursor()

    # Recover LAST_ID from existing entry IDs
    if config_dir:
        prefix = config.get("DEVICE_PREFIX", "d")
        cursor.execute("SELECT id FROM entries")
        max_num = 0
        pattern = re.compile(rf"^{re.escape(prefix)}(\d+)$")
        for (eid,) in cursor.fetchall():
            m = pattern.match(eid)
            if m:
                max_num = max(max_num, int(m.group(1)))
        current = int(config.get("LAST_ID", "0"))
        if max_num > current:
            config["LAST_ID"] = str(max_num)
            save_config_setting(config_dir, "LAST_ID", str(max_num))
            results.append(
                f"Recovered LAST_ID: {current} → {max_num}"
            )

    cursor.execute(SELECT_ENTRY_COUNT_SQL)
    total_entries = cursor.fetchone()[0]

    if storage_dir.exists():
        for child in storage_dir.iterdir():
            # Only delete directories that look like tag directories
            # AND are not day-file directories (extra safety check).
            if (
                child.is_dir()
                and TAG_PATTERN.fullmatch(child.name)
                and not child.name[0].isdigit()  # day dirs start with year digits
            ):
                shutil.rmtree(child)

    cursor.execute(SELECT_TAG_STATS_SQL)
    tag_stats = cursor.fetchall()
    tags = [{"tag": tag, "count": count} for tag, count in tag_stats]

    return {
        "success": True,
        "total_entries": total_entries,
        "normalized_files": normalized,
        "tag_stats": tags,
        "messages": results,
    }
