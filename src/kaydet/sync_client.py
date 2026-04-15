"""Sync client: pulls changes from a remote and applies them locally."""

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
)
from .sync_transport import SyncTransport


class SyncClient:
    """Client-side sync logic backed by a KaydetService and transport."""

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
        """Perform a full pull-then-push synchronization."""
        pull_result = self.pull()
        push_result = self.push()
        return {"pull": pull_result, "push": push_result}

    def pull(self) -> Dict[str, Any]:
        """Pull remote changes and apply them locally."""
        since = int(self.config.get("sync_token", "0"))
        changes_resp = self._get_changes(since)

        if not changes_resp.changes:
            return {"pulled": 0, "token": since}

        # Identify which entries need full data
        to_fetch = [
            c.entry_id
            for c in changes_resp.changes
            if c.action in ("created", "updated")
        ]
        to_delete = [
            c.entry_id for c in changes_resp.changes if c.action == "deleted"
        ]

        # Fetch full entry data
        entries_data: List[EntryData] = []
        if to_fetch:
            entries_data = self._get_entries(to_fetch)

        # Apply deletions
        for eid in to_delete:
            self._delete_local_entry(eid)

        # Apply upserts
        for entry_data in entries_data:
            self._apply_entry(entry_data)

        # Update sync token
        new_token = str(changes_resp.new_token)
        self._update_config("sync_token", new_token)

        return {"pulled": len(entries_data) + len(to_delete), "token": new_token}

    def push(self) -> Dict[str, Any]:
        """Push local changes to the remote."""
        # Find local changes not yet pushed?
        # Actually, for this simple protocol, we just push everything
        # that was modified after the last sync.
        # A better way is tracking sync state per-entry, but for now
        # let's just push everything from sync_log.
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT id, entry_id, action, device_id FROM sync_log "
            "WHERE id > ? ORDER BY id",
            (int(self.config.get("last_pushed_log_id", "0")),),
        )
        rows = cursor.fetchall()
        if not rows:
            return {"pushed": 0}

        to_push_ids = [r[1] for r in rows if r[2] in ("created", "updated")]
        entries = []
        for eid in to_push_ids:
            entry_data = self._load_local_entry(eid)
            if entry_data:
                entries.append(entry_data)

        if not entries:
            # Maybe only deletions?
            new_pushed_id = rows[-1][0]
            self._update_config("last_pushed_log_id", str(new_pushed_id))
            return {"pushed": 0}

        # Push to remote
        req = ProtocolMessage(
            method="push",
            body={
                "entries": [e.to_dict() for e in entries],
                "device_id": self.config.get("DEVICE_ID", "unknown"),
            },
        )
        resp_msg = self.transport.send(req)
        if "error" in resp_msg.body:
            raise Exception(f"Push failed: {resp_msg.body['error']}")

        # Update last pushed ID
        new_pushed_id = rows[-1][0]
        self._update_config("last_pushed_log_id", str(new_pushed_id))

        return {"pushed": len(entries)}

    def _get_changes(self, since: int):
        req = ProtocolMessage(method="changes", body={"since": since})
        resp = self.transport.send(req)
        from .sync_protocol import parse_response

        return parse_response("changes", resp.body)

    def _get_entries(self, entry_ids: List[str]) -> List[EntryData]:
        req = ProtocolMessage(
            method="entries", body={"entry_ids": entry_ids}
        )
        resp = self.transport.send(req)
        from .sync_protocol import parse_response

        return parse_response("entries", resp.body).entries

    def _apply_entry(self, entry_data: EntryData) -> None:
        """Apply a pulled entry to the local store."""
        # Check if entry exists locally by ID
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT e.id, f.body FROM entries e "
            "LEFT JOIN entries_fts f ON f.entry_id = e.id "
            "WHERE e.id = ?",
            (entry_data.entry_id,),
        )
        existing = cursor.fetchone()

        is_same_id = existing is not None
        
        # If ID doesn't exist, check by source_file + timestamp (legacy match)
        if not is_same_id:
            cursor.execute(
                "SELECT e.id, f.body FROM entries e "
                "LEFT JOIN entries_fts f ON f.entry_id = e.id "
                "WHERE e.source_file = ? AND e.timestamp = ?",
                (entry_data.source_file, entry_data.timestamp),
            )
            existing = cursor.fetchone()

        # Only treat as same entry if text matches too (for legacy match)
        # or if ID is identical.
        is_same = existing and (
            is_same_id or 
            (existing[1] and existing[1].strip() == entry_data.text.strip())
        )

        if is_same:
            self.service.update_entry(
                existing[0],
                text=entry_data.text,
                metadata=entry_data.metadata or None,
                tags=entry_data.tags or None,
            )
            local_id = existing[0]
        else:
            # Derive datetime from source_file
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

            # Preserve remote ID if creating new
            result = self.service.add_entry(
                text=entry_data.text,
                metadata=entry_data.metadata or None,
                tags=entry_data.tags or None,
                at=entry_at,
                entry_id=entry_data.entry_id,
            )
            local_id = result.get("entry_id")
            if not local_id:
                return

        # Store encrypted secret if provided
        if entry_data.encrypted_secret:
            from .secrets import store_secret

            encrypted = base64.b64decode(
                entry_data.encrypted_secret
            )
            store_secret(local_id, encrypted, self.storage_dir)

    def _update_config(self, key: str, value: str) -> None:
        """Update a key in the local config file."""
        from .utils import save_config_setting

        self.config[key] = value
        save_config_setting(self.service.config_dir, key, value)

    def _get_attachment(self, filename: str) -> bytes:
        req = ProtocolMessage(
            method="attachment_get", body={"filename": filename}
        )
        resp_msg = self.transport.send(req)
        from .sync_protocol import parse_response

        resp = parse_response("attachment_get", resp_msg.body)
        if not resp.found:
            raise FileNotFoundError(filename)
        return base64.b64decode(resp.data)

    def _put_attachment(self, filename: str, data_bytes: bytes) -> None:
        data = base64.b64encode(data_bytes).decode("ascii")
        req = ProtocolMessage(
            method="attachment_put",
            body={"filename": filename, "data": data},
        )
        self.transport.send(req)

    def _delete_local_entry(self, entry_id: str) -> None:
        """Delete an entry locally (soft: just from index)."""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT id FROM entries WHERE id = ?",
            (entry_id,),
        )
        if cursor.fetchone():
            cursor.execute(
                "DELETE FROM entries WHERE id = ?",
                (entry_id,),
            )

    def _load_local_entry(
        self, entry_id: str
    ) -> Optional[EntryData]:
        """Load an entry from local storage for pushing."""
        from .secrets import get_secret

        result = self.service.get_entry(entry_id)
        if not result.get("success"):
            return None

        entry = result["entry"]

        # Get source_file and updated_at from DB
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT source_file, updated_at FROM entries WHERE id = ?",
            (entry_id,),
        )
        row = cursor.fetchone()
        source_file = row[0] if row else ""
        updated_at = row[1] if row else None

        # Get encrypted secret
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
