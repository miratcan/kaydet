"""Sync client: single round-trip sync with a remote server."""

from __future__ import annotations

import base64
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .service import KaydetService
from .sync_protocol import (
    EntryData,
    ProtocolMessage,
    parse_response,
)
from .sync_transport import SyncTransport


class SyncClient:
    """Dumb sync client — sends local changes, receives remote changes."""

    def __init__(
        self, service: KaydetService, transport: SyncTransport
    ) -> None:
        self.service = service
        self.transport = transport

    @property
    def conn(self) -> sqlite3.Connection:
        return self.service.conn

    @property
    def config(self) -> Dict[str, str]:
        return self.service.config

    @property
    def storage_dir(self) -> Path:
        return self.service.storage_dir

    def sync(self) -> Dict[str, Any]:
        """Single round-trip sync: send local changes, get remote changes."""
        # 1. Gather local entries to push
        local_entries = self._collect_local_changes()

        # 2. Send to server in one call
        token = int(self.config.get("sync_token", "0"))
        req = ProtocolMessage(
            method="sync",
            body={
                "since": token,
                "entries": [e.to_dict() for e in local_entries],
                "device_id": self.config.get("DEVICE_PREFIX", "d"),
            },
        )
        resp_msg = self.transport.send(req)
        resp = parse_response("sync", resp_msg.body)

        # 3. Apply remote entries locally
        pulled = 0
        for entry_data in resp.entries:
            if entry_data.metadata.get("_deleted") == "true":
                self._delete_local_entry(entry_data.entry_id)
            else:
                self._apply_entry(entry_data)
            pulled += 1

        # 4. Update token
        self._update_config("sync_token", str(resp.new_token))

        return {
            "pushed": len(local_entries),
            "pulled": pulled,
            "token": resp.new_token,
        }

    def _collect_local_changes(self) -> List[EntryData]:
        """Gather entries from sync_log that haven't been pushed yet."""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT id, entry_id, action FROM sync_log "
            "WHERE id > ? ORDER BY id",
            (int(self.config.get("last_pushed_log_id", "0")),),
        )
        rows = cursor.fetchall()
        if not rows:
            return []

        entries = []
        for _log_id, entry_id, action in rows:
            if action in ("created", "updated"):
                entry_data = self._load_local_entry(entry_id)
                if entry_data:
                    entries.append(entry_data)

        # Mark as pushed regardless of success
        new_max = rows[-1][0]
        self._update_config("last_pushed_log_id", str(new_max))

        return entries

    def _apply_entry(self, entry_data: EntryData) -> None:
        """Apply a remote entry to the local store."""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT id FROM entries WHERE id = ?",
            (entry_data.entry_id,),
        )
        existing = cursor.fetchone()

        if existing:
            self.service.update_entry(
                existing[0],
                text=entry_data.text,
                metadata=entry_data.metadata or None,
                tags=entry_data.tags or None,
            )
        else:
            day_pattern = self.config.get(
                "DAY_FILE_PATTERN", "%Y-%m-%d.txt"
            )
            entry_at = None
            try:
                entry_date = datetime.strptime(
                    entry_data.source_file, day_pattern
                )
                h, m = entry_data.timestamp.split(":")
                entry_at = entry_date.replace(
                    hour=int(h), minute=int(m)
                )
            except (ValueError, AttributeError):
                pass

            result = self.service.add_entry(
                text=entry_data.text,
                metadata=entry_data.metadata or None,
                tags=entry_data.tags or None,
                at=entry_at,
                entry_id=entry_data.entry_id,
            )
            if not result.get("success"):
                return

        # Store encrypted secret if provided
        if entry_data.encrypted_secret:
            from .secrets import store_secret

            encrypted = base64.b64decode(
                entry_data.encrypted_secret
            )
            store_secret(
                entry_data.entry_id, encrypted, self.storage_dir
            )

    def _delete_local_entry(self, entry_id: str) -> None:
        """Delete an entry from the local index."""
        self.conn.execute(
            "DELETE FROM entries WHERE id = ?", (entry_id,)
        )

    def _load_local_entry(
        self, entry_id: str
    ) -> Optional[EntryData]:
        """Load an entry for pushing to the server."""
        from .secrets import get_secret

        result = self.service.get_entry(entry_id)
        if not result.get("success"):
            return None

        entry = result["entry"]

        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT source_file, updated_at FROM entries WHERE id = ?",
            (entry_id,),
        )
        row = cursor.fetchone()
        source_file = row[0] if row else ""
        updated_at = row[1] if row else None

        encrypted = get_secret(entry_id, self.storage_dir)
        enc_b64 = None
        if encrypted:
            enc_b64 = base64.b64encode(encrypted).decode("ascii")

        return EntryData(
            entry_id=entry_id,
            source_file=source_file,
            timestamp=entry["timestamp"],
            text=entry["text"],
            tags=entry.get("tags", []),
            metadata=entry.get("metadata", {}),
            attachments=entry.get("attachments", []),
            encrypted_secret=enc_b64,
            updated_at=updated_at,
        )

    def _update_config(self, key: str, value: str) -> None:
        """Persist a config key to disk."""
        from .utils import save_config_setting

        self.config[key] = value
        save_config_setting(self.service.config_dir, key, value)
