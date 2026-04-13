"""Sync client: pulls from and pushes to a sync server."""

from __future__ import annotations

import base64
import sqlite3
from dataclasses import asdict
from datetime import datetime
from typing import Any, Dict, List, Optional

from .secrets import store_secret
from .service import KaydetService
from .sync_protocol import (
    EntryData,
    ProtocolMessage,
    PushEntriesRequest,
    SyncChangesRequest,
    parse_response,
)
from .sync_transport import SyncTransport


class SyncClient:
    """Client-side sync logic backed by a KaydetService."""

    def __init__(
        self,
        service: KaydetService,
        transport: SyncTransport,
    ) -> None:
        self.service = service
        self.transport = transport

    # Convenience accessors
    @property
    def conn(self) -> sqlite3.Connection:
        return self.service.conn

    @property
    def config(self):
        return self.service.config

    @property
    def storage_dir(self):
        return self.service.storage_dir

    @classmethod
    def initialize(cls) -> SyncClient:
        """Create a client from the local config."""
        from .sync_transport import create_transport

        service = KaydetService.initialize()
        transport = create_transport(service.config)
        return cls(service, transport)

    def sync(self) -> Dict[str, Any]:
        """Run a full sync cycle: push first, then pull.

        Push-first prevents pulled entries from being
        immediately pushed back (sync loop).
        """
        push_result = self.push()
        pull_result = self.pull()
        return {
            "pull": pull_result,
            "push": push_result,
        }

    def pull(self) -> Dict[str, Any]:
        """Pull changes from the server."""
        sync_token = int(self.config.get("sync_token", "0"))

        # Record max sync_log id before pull so we can mark
        # any log entries created by pull as non-local
        cursor = self.conn.cursor()
        cursor.execute("SELECT MAX(id) FROM sync_log")
        pre_pull_max = cursor.fetchone()[0] or 0

        # Step 1: Get changes since our token
        changes_req = ProtocolMessage(
            method="changes",
            body=asdict(SyncChangesRequest(since=sync_token)),
        )
        changes_resp_msg = self.transport.send(changes_req)
        changes_resp = parse_response(
            "changes", changes_resp_msg.body
        )

        if not changes_resp.changes:
            return {"pulled": 0, "new_token": sync_token}

        # Step 2: Collect entry IDs we need to fetch
        entry_ids = list(
            {c.entry_id for c in changes_resp.changes}
        )
        deleted_ids = [
            c.entry_id
            for c in changes_resp.changes
            if c.action == "deleted"
        ]
        fetch_ids = [
            eid for eid in entry_ids if eid not in deleted_ids
        ]

        # Step 3: Fetch full entries
        pulled = 0
        if fetch_ids:
            entries_req = ProtocolMessage(
                method="entries",
                body={"entry_ids": fetch_ids},
            )
            entries_resp_msg = self.transport.send(entries_req)
            entries_resp = parse_response(
                "entries", entries_resp_msg.body
            )

            for entry_data in entries_resp.entries:
                self._apply_entry(entry_data)
                pulled += 1
                # Download missing attachments
                for att in entry_data.attachments:
                    self._pull_attachment(att)

        # Step 4: Handle deletes
        for eid in deleted_ids:
            self._delete_local_entry(eid)

        # Step 5: Mark sync_log entries created during pull
        # so they won't be pushed back to the server
        self.conn.execute(
            "UPDATE sync_log SET device_id = '__pull__' "
            "WHERE id > ? AND device_id IS NULL",
            (pre_pull_max,),
        )

        # Step 6: Update sync token
        new_token = changes_resp.new_token
        self._save_sync_token(new_token)

        return {"pulled": pulled, "new_token": new_token}

    def _seed_sync_log(self) -> int:
        """Seed sync_log with all existing entries on first push.

        Returns the number of entries seeded.
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM sync_log")
        if cursor.fetchone()[0] > 0:
            return 0  # already has log entries

        cursor.execute("SELECT id FROM entries ORDER BY id")
        entry_ids = [r[0] for r in cursor.fetchall()]
        if not entry_ids:
            return 0

        from .database import LOG_SYNC_ACTION_SQL

        for eid in entry_ids:
            cursor.execute(
                LOG_SYNC_ACTION_SQL, (eid, "created", None)
            )
        return len(entry_ids)

    def push(self) -> Dict[str, Any]:
        """Push local changes to the server."""
        self.service._ensure_index(datetime.now())
        self._seed_sync_log()

        # Get local changes since last push
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT id, entry_id, action "
            "FROM sync_log "
            "WHERE device_id IS NULL "
            "ORDER BY id",
        )
        local_changes = cursor.fetchall()

        if not local_changes:
            return {"pushed": 0}

        # Collect entries to push (skip deleted)
        entries_to_push: List[EntryData] = []
        for _log_id, entry_id, action in local_changes:
            if action == "deleted":
                continue
            entry_data = self._load_local_entry(entry_id)
            if entry_data:
                entries_to_push.append(entry_data)

        if not entries_to_push:
            return {"pushed": 0}

        # Build device ID
        import platform

        device_id = platform.node() or "unknown"

        push_req = ProtocolMessage(
            method="push",
            body=asdict(
                PushEntriesRequest(
                    entries=entries_to_push,
                    device_id=device_id,
                )
            ),
        )
        push_resp_msg = self.transport.send(push_req)
        push_resp = parse_response("push", push_resp_msg.body)

        # Mark pushed log entries so they won't be pushed again
        pushed_log_ids = [r[0] for r in local_changes]
        if pushed_log_ids:
            placeholders = ",".join("?" * len(pushed_log_ids))
            self.conn.execute(
                f"UPDATE sync_log SET device_id = ? "
                f"WHERE id IN ({placeholders})",
                [device_id, *pushed_log_ids],
            )

        # Push attachments for pushed entries
        for entry_data in entries_to_push:
            for att in entry_data.attachments:
                self._push_attachment(att)

        return {
            "pushed": push_resp.accepted,
            "conflicts": push_resp.conflicts,
            "errors": push_resp.errors,
        }

    def _apply_entry(self, entry_data: EntryData) -> None:
        """Apply a pulled entry to the local store."""
        # Check if entry exists locally by source_file+timestamp
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT e.id, f.body FROM entries e "
            "LEFT JOIN entries_fts f ON f.rowid = e.id "
            "WHERE e.source_file = ? AND e.timestamp = ?",
            (entry_data.source_file, entry_data.timestamp),
        )
        existing = cursor.fetchone()

        # Only treat as same entry if text matches too,
        # otherwise it's a different entry at the same time
        is_same = (
            existing
            and existing[1]
            and existing[1].strip() == entry_data.text.strip()
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

            result = self.service.add_entry(
                text=entry_data.text,
                metadata=entry_data.metadata or None,
                tags=entry_data.tags or None,
                at=entry_at,
            )
            local_id = result.get("entry_id")
            if not local_id:
                return

        # Store encrypted secret if provided
        if entry_data.encrypted_secret:
            encrypted = base64.b64decode(
                entry_data.encrypted_secret
            )
            store_secret(self.conn, local_id, encrypted)

    def _pull_attachment(self, filename: str) -> None:
        """Download an attachment if not present locally."""
        attachments_dir = self.storage_dir / "attachments"
        local_path = attachments_dir / filename
        if local_path.exists():
            return
        attachments_dir.mkdir(exist_ok=True)

        req = ProtocolMessage(
            method="attachment_get",
            body={"filename": filename},
        )
        resp_msg = self.transport.send(req)
        resp = parse_response(
            "attachment_get", resp_msg.body
        )
        if resp.found and resp.data:
            local_path.write_bytes(
                base64.b64decode(resp.data)
            )

    def _push_attachment(self, filename: str) -> None:
        """Upload an attachment to the server."""
        attachments_dir = self.storage_dir / "attachments"
        local_path = attachments_dir / filename
        if not local_path.exists():
            return

        data = base64.b64encode(
            local_path.read_bytes()
        ).decode("ascii")
        req = ProtocolMessage(
            method="attachment_put",
            body={"filename": filename, "data": data},
        )
        self.transport.send(req)

    def _delete_local_entry(self, entry_id: int) -> None:
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
        self, entry_id: int
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
            "SELECT source_file, updated_at "
            "FROM entries WHERE id = ?",
            (entry_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        source_file, updated_at = row

        encrypted = get_secret(self.conn, entry_id)
        enc_b64 = None
        if encrypted:
            enc_b64 = base64.b64encode(
                encrypted
            ).decode("ascii")

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

    def _save_sync_token(self, token: int) -> None:
        """Persist the sync token to config."""
        # Update in-memory config
        self.config["sync_token"] = str(token)

        # Write to config file
        from configparser import ConfigParser

        config_path = self.service.config_dir / "config.ini"
        parser = ConfigParser(interpolation=None)
        if config_path.exists():
            parser.read(config_path, encoding="utf-8")
        section = "SETTINGS"
        if section not in parser:
            parser[section] = {}
        parser[section]["sync_token"] = str(token)
        with config_path.open("w", encoding="utf-8") as f:
            parser.write(f)

    def get_status(self) -> Dict[str, Any]:
        """Return current sync status info."""
        sync_token = int(self.config.get("sync_token", "0"))
        server = self.config.get("sync_server", "")
        transport = self.config.get("sync_transport", "stdin")
        return {
            "sync_token": sync_token,
            "server": server,
            "transport": transport,
        }
