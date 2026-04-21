"""Doctor command - rebuild file IDs, clean orphan dirs."""

import re
import shutil
import sqlite3
from configparser import SectionProxy
from datetime import datetime
from pathlib import Path

from ..parsers import TAG_PATTERN
from ..sync import sync_modified_day_files
from ..utils import save_config_setting


def doctor_command(
    conn: sqlite3.Connection,
    storage_dir: Path,
    config: SectionProxy,
    now: datetime,
    config_dir: Path | None = None,
) -> dict:
    """Normalize entry IDs in day files and clean orphan tag directories."""
    results = []

    # Rust core owns the index — reset synced_files so all files are re-scanned.
    try:
        conn.execute("DELETE FROM synced_files")
        conn.commit()
    except Exception:
        pass

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

    # Recover LAST_ID from Rust index if available, else scan files.
    if config_dir:
        prefix = config.get("DEVICE_PREFIX", "d")
        pattern = re.compile(rf"^{re.escape(prefix)}(\d+)$")
        max_num = 0

        try:
            import kaydet_core_rs as _rs
            core = _rs.KaydetCore(str(storage_dir))
            for entry in core.all_entries():
                m = pattern.match(entry.entry_id)
                if m:
                    max_num = max(max_num, int(m.group(1)))
        except Exception:
            pass

        current = int(config.get("LAST_ID", "0"))
        if max_num > current:
            config["LAST_ID"] = str(max_num)
            save_config_setting(config_dir, "LAST_ID", str(max_num))
            results.append(f"Recovered LAST_ID: {current} → {max_num}")

    # Remove orphan tag directories.
    if storage_dir.exists():
        for child in storage_dir.iterdir():
            if (
                child.is_dir()
                and TAG_PATTERN.fullmatch(child.name)
                and not child.name[0].isdigit()
            ):
                shutil.rmtree(child)

    return {
        "success": True,
        "normalized_files": normalized,
        "messages": results,
    }
