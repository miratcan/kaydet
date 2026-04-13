"""Sync server: handles sync protocol requests against a local store."""

from __future__ import annotations

import base64
import sqlite3
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional

from .service import KaydetService
from .sync_protocol import (
    AttachmentGetRequest,
    AttachmentGetResponse,
    AttachmentPutRequest,
    AttachmentPutResponse,
    EntryData,
    ProtocolMessage,
    PushEntriesRequest,
    PushEntriesResponse,
    SyncChange,
    SyncChangesRequest,
    SyncChangesResponse,
    SyncEntriesRequest,
    SyncEntriesResponse,
    deserialize_message,
    make_response_message,
    parse_request,
    serialize_message,
)


class SyncServer:
    """Server-side sync logic backed by a KaydetService instance."""

    def __init__(self, service: KaydetService) -> None:
        self.service = service

    # Convenience accessors for sync-specific DB operations
    @property
    def conn(self) -> sqlite3.Connection:
        return self.service.conn

    @property
    def log_dir(self):
        return self.service.log_dir

    @classmethod
    def initialize(cls) -> SyncServer:
        """Create a server from the local config."""
        service = KaydetService.initialize()
        return cls(service)

    def handle_message(
        self, msg: ProtocolMessage
    ) -> ProtocolMessage:
        """Dispatch a protocol message to the correct handler."""
        if msg.method == "changes":
            req = parse_request(msg)
            resp = self._handle_changes(req)
        elif msg.method == "entries":
            req = parse_request(msg)
            resp = self._handle_entries(req)
        elif msg.method == "push":
            req = parse_request(msg)
            resp = self._handle_push(req)
        elif msg.method == "attachment_get":
            req = parse_request(msg)
            resp = self._handle_attachment_get(req)
        elif msg.method == "attachment_put":
            req = parse_request(msg)
            resp = self._handle_attachment_put(req)
        else:
            resp = {"error": f"Unknown method: {msg.method}"}
            return ProtocolMessage(method=msg.method, body=resp)
        return make_response_message(msg.method, resp)

    def _handle_changes(
        self, req: SyncChangesRequest
    ) -> SyncChangesResponse:
        """Return sync_log entries since the given token."""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT id, entry_id, action, device_id, created_at "
            "FROM sync_log WHERE id > ? ORDER BY id LIMIT 1000",
            (req.since,),
        )
        rows = cursor.fetchall()
        changes = [
            SyncChange(
                id=r[0],
                entry_id=r[1],
                action=r[2],
                device_id=r[3],
                created_at=r[4],
            )
            for r in rows
        ]
        new_token = changes[-1].id if changes else req.since
        return SyncChangesResponse(
            changes=changes,
            new_token=new_token,
            has_more=len(rows) == 1000,
        )

    def _handle_entries(
        self, req: SyncEntriesRequest
    ) -> SyncEntriesResponse:
        """Return full entry data for requested IDs."""
        entries: List[EntryData] = []
        for eid in req.entry_ids:
            entry_data = self._load_entry(eid)
            if entry_data:
                entries.append(entry_data)
        return SyncEntriesResponse(entries=entries)

    def _load_entry(self, entry_id: int) -> Optional[EntryData]:
        """Load a single entry via KaydetService."""
        from .secrets import get_secret

        result = self.service.get_entry(entry_id)
        if not result.get("success"):
            return None

        entry = result["entry"]

        # Get updated_at from DB
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT source_file, updated_at "
            "FROM entries WHERE id = ?",
            (entry_id,),
        )
        row = cursor.fetchone()
        source_file = row[0] if row else ""
        updated_at = row[1] if row else None

        # Get encrypted secret
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

    def _handle_push(
        self, req: PushEntriesRequest
    ) -> PushEntriesResponse:
        """Accept pushed entries from a client."""
        now = datetime.now()
        accepted = 0
        conflicts = 0
        errors: List[str] = []

        for entry_data in req.entries:
            try:
                self._upsert_entry(
                    entry_data, req.device_id, now
                )
                accepted += 1
            except Exception as e:
                errors.append(
                    f"Entry {entry_data.entry_id}: {e}"
                )

        return PushEntriesResponse(
            accepted=accepted,
            conflicts=conflicts,
            errors=errors,
        )

    def _handle_attachment_get(
        self, req: AttachmentGetRequest
    ) -> AttachmentGetResponse:
        """Serve an attachment file."""
        attachments_dir = self.log_dir / "attachments"
        filepath = attachments_dir / req.filename
        if not filepath.exists() or not filepath.is_file():
            return AttachmentGetResponse(
                filename=req.filename, found=False
            )
        data = base64.b64encode(
            filepath.read_bytes()
        ).decode("ascii")
        return AttachmentGetResponse(
            filename=req.filename, data=data, found=True
        )

    def _handle_attachment_put(
        self, req: AttachmentPutRequest
    ) -> AttachmentPutResponse:
        """Store an uploaded attachment file."""
        attachments_dir = self.log_dir / "attachments"
        attachments_dir.mkdir(exist_ok=True)
        filepath = attachments_dir / req.filename
        filepath.write_bytes(base64.b64decode(req.data))
        return AttachmentPutResponse(
            filename=req.filename, stored=True
        )

    def _upsert_entry(
        self,
        entry_data: EntryData,
        device_id: str,
        now: datetime,
    ) -> None:
        """Insert or update an entry on the server."""
        # Check if entry already exists by source_file + timestamp
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT e.id, e.updated_at, f.body "
            "FROM entries e "
            "LEFT JOIN entries_fts f ON f.rowid = e.id "
            "WHERE e.source_file = ? AND e.timestamp = ?",
            (entry_data.source_file, entry_data.timestamp),
        )
        existing = cursor.fetchone()

        if existing:
            existing_id, server_updated_at, existing_body = (
                existing
            )
            # Different text at same timestamp = different entry
            if (
                existing_body
                and existing_body.strip()
                != entry_data.text.strip()
            ):
                existing = None

        if existing:
            existing_id, server_updated_at, _ = existing
            # Reject if server copy is newer
            if (
                server_updated_at
                and entry_data.updated_at
                and server_updated_at > entry_data.updated_at
            ):
                return  # server has newer data, skip
            self._update_existing_entry(
                existing_id, entry_data, device_id
            )
        else:
            self._create_new_entry(entry_data, device_id, now)

    def _update_existing_entry(
        self,
        existing_id: int,
        entry_data: EntryData,
        device_id: str,
    ) -> None:
        """Update an existing server entry with pushed data."""
        self.service.update_entry(
            existing_id,
            text=entry_data.text,
            metadata=entry_data.metadata or None,
            tags=entry_data.tags or None,
        )

        if entry_data.encrypted_secret:
            from .secrets import store_secret

            encrypted = base64.b64decode(
                entry_data.encrypted_secret
            )
            store_secret(self.conn, existing_id, encrypted)

    def _create_new_entry(
        self,
        entry_data: EntryData,
        device_id: str,
        now: datetime,
    ) -> None:
        """Create a new entry on the server via KaydetService."""
        # Derive entry datetime from source_file + timestamp
        # so the entry lands in the correct day file.
        config = self.service.config
        day_pattern = config.get(
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

        if not result.get("success"):
            return

        new_id = result["entry_id"]

        if entry_data.encrypted_secret:
            from .secrets import store_secret

            encrypted = base64.b64decode(
                entry_data.encrypted_secret
            )
            store_secret(self.conn, new_id, encrypted)


def validate_api_key(
    conn: sqlite3.Connection, key: str
) -> bool:
    """Check if an API key is valid and update last_used_at."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT key FROM sync_keys WHERE key = ?", (key,)
    )
    if cursor.fetchone() is None:
        return False
    conn.execute(
        "UPDATE sync_keys SET last_used_at = datetime('now') "
        "WHERE key = ?",
        (key,),
    )
    return True


def generate_api_key(
    conn: sqlite3.Connection, name: str
) -> str:
    """Generate and store a new API key."""
    import secrets

    key = f"kyd_{secrets.token_hex(24)}"
    conn.execute(
        "INSERT INTO sync_keys (key, name, created_at) "
        "VALUES (?, ?, datetime('now'))",
        (key, name),
    )
    return key


def revoke_api_key(
    conn: sqlite3.Connection, name: str
) -> bool:
    """Revoke an API key by name. Returns True if found."""
    cursor = conn.execute(
        "DELETE FROM sync_keys WHERE name = ?", (name,)
    )
    return cursor.rowcount > 0


def list_api_keys(
    conn: sqlite3.Connection,
) -> List[Dict[str, Any]]:
    """List all API keys (without exposing full key)."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT key, name, created_at, last_used_at "
        "FROM sync_keys ORDER BY created_at"
    )
    return [
        {
            "key_prefix": row[0][:12] + "...",
            "name": row[1],
            "created_at": row[2],
            "last_used_at": row[3],
        }
        for row in cursor.fetchall()
    ]


# -- stdin transport --


def run_stdin_server() -> None:
    """Run the sync server reading/writing JSON on stdin/stdout."""
    server = SyncServer.initialize()

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            msg = deserialize_message(line)
            response = server.handle_message(msg)
            sys.stdout.write(serialize_message(response) + "\n")
            sys.stdout.flush()
        except Exception as e:
            error_resp = ProtocolMessage(
                method="error",
                body={"error": str(e)},
            )
            sys.stdout.write(
                serialize_message(error_resp) + "\n"
            )
            sys.stdout.flush()


if __name__ == "__main__":
    run_stdin_server()
