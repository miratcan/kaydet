"""Sync server: handles sync protocol requests against a local store."""

from __future__ import annotations

import base64
import hashlib
import logging
import secrets as secrets_mod
import sqlite3
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

from kaydet_core.parsers import partition_entry_tokens
from kaydet_core.service import KaydetService
from kaydet_core.sync_protocol import (
    AttachmentGetRequest,
    AttachmentGetResponse,
    AttachmentPutRequest,
    AttachmentPutResponse,
    DeleteEntryRequest,
    DeleteEntryResponse,
    EntryData,
    GetEntryRequest,
    GetEntryResponse,
    GetStatsRequest,
    GetStatsResponse,
    ListTagsRequest,
    ListTagsResponse,
    ProtocolMessage,
    PushEntriesRequest,
    PushEntriesResponse,
    SearchRequest,
    SearchResponse,
    SyncChange,
    SyncChangesRequest,
    SyncChangesResponse,
    SyncEntriesRequest,
    SyncEntriesResponse,
    SyncRequest,
    SyncResponse,
    UpdateEntryRequest,
    UpdateEntryResponse,
    UploadFinishResponse,
    UploadStartResponse,
    deserialize_message,
    make_response_message,
    parse_request,
    serialize_message,
    validate_attachment_filename,
)


@dataclass
class UploadState:
    """Tracks an in-progress chunked upload."""

    upload_id: str
    filename: str
    size: int
    expected_sha256: str
    received_bytes: int = 0
    created_at: float = field(default_factory=time.time)


class FileTransferManager:
    """Manages chunked file uploads and file downloads."""

    def __init__(
        self,
        storage_dir: Path,
        cleanup_timeout: int = 86400,
        chunk_size: int = 1048576,
    ) -> None:
        self.storage_dir = storage_dir
        self.attachments_dir = storage_dir / "attachments"
        self.uploads_dir = storage_dir / "uploads"
        self.cleanup_timeout = cleanup_timeout
        self.chunk_size = chunk_size
        self._uploads: Dict[str, UploadState] = {}

    def start_upload(
        self, filename: str, size: int, sha256: str
    ) -> UploadStartResponse:
        """Initiate or resume a chunked upload."""
        self.cleanup_stale()
        if not validate_attachment_filename(filename):
            return UploadStartResponse(
                upload_id=None, chunk_size=0, existing_offset=0
            )

        # Fast-path: file already exists with matching hash
        target = self.attachments_dir / filename
        if target.exists():
            existing_hash = self.compute_sha256(target)
            if existing_hash == sha256:
                return UploadStartResponse(
                    already_exists=True
                )

        # Check for existing partial upload for this filename
        for uid, state in self._uploads.items():
            if state.filename == filename:
                part_file = self.uploads_dir / f"{uid}.part"
                if part_file.exists():
                    existing_offset = part_file.stat().st_size
                    state.received_bytes = existing_offset
                    return UploadStartResponse(
                        upload_id=uid,
                        chunk_size=self.chunk_size,
                        existing_offset=existing_offset,
                    )
                # Stale state entry, clean it up
                del self._uploads[uid]
                break

        # New upload
        upload_id = secrets_mod.token_hex(8)
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        self._uploads[upload_id] = UploadState(
            upload_id=upload_id,
            filename=filename,
            size=size,
            expected_sha256=sha256,
        )
        return UploadStartResponse(
            upload_id=upload_id,
            chunk_size=self.chunk_size,
            existing_offset=0,
        )

    def write_chunk(
        self, upload_id: str, offset: int, data: bytes
    ) -> Optional[tuple]:
        """Write a chunk. Returns (received_bytes, total_received) or None."""
        state = self._uploads.get(upload_id)
        if state is None:
            return None

        part_file = self.uploads_dir / f"{upload_id}.part"
        current_size = (
            part_file.stat().st_size if part_file.exists() else 0
        )

        if offset != current_size:
            return None  # offset mismatch

        with open(part_file, "ab") as f:
            f.write(data)

        received = len(data)
        state.received_bytes = current_size + received
        return (received, state.received_bytes)

    def get_expected_offset(self, upload_id: str) -> int:
        """Return the expected next offset for an upload."""
        part_file = self.uploads_dir / f"{upload_id}.part"
        if part_file.exists():
            return part_file.stat().st_size
        return 0

    def finish_upload(
        self, upload_id: str
    ) -> UploadFinishResponse:
        """Finalize an upload: verify SHA-256, move to attachments."""
        state = self._uploads.get(upload_id)
        if state is None:
            return UploadFinishResponse(
                ok=False, error="Unknown upload_id"
            )

        part_file = self.uploads_dir / f"{upload_id}.part"
        if not part_file.exists():
            del self._uploads[upload_id]
            return UploadFinishResponse(
                filename=state.filename,
                ok=False,
                error="No data received",
            )

        actual_hash = self.compute_sha256(part_file)
        actual_size = part_file.stat().st_size

        # Skip hash check if client didn't provide one
        if state.expected_sha256 and actual_hash != state.expected_sha256:
            part_file.unlink()
            del self._uploads[upload_id]
            return UploadFinishResponse(
                filename=state.filename,
                ok=False,
                sha256_match=False,
                size=actual_size,
                error=(
                    f"SHA-256 mismatch: expected "
                    f"{state.expected_sha256} "
                    f"got {actual_hash}"
                ),
            )

        # Move to attachments
        self.attachments_dir.mkdir(parents=True, exist_ok=True)
        target = self.attachments_dir / state.filename
        part_file.rename(target)
        del self._uploads[upload_id]

        return UploadFinishResponse(
            filename=state.filename,
            ok=True,
            sha256_match=True,
            size=actual_size,
        )

    def get_file_path(
        self, filename: str
    ) -> Optional[Path]:
        """Return path to an attachment if it exists."""
        if not validate_attachment_filename(filename):
            return None
        filepath = self.attachments_dir / filename
        if filepath.exists() and filepath.is_file():
            return filepath
        return None

    @staticmethod
    def compute_sha256(filepath: Path) -> str:
        """Compute hex-encoded SHA-256 of a file."""
        h = hashlib.sha256()
        with open(filepath, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        return h.hexdigest()

    def cleanup_stale(self) -> int:
        """Remove uploads older than cleanup_timeout. Returns count removed."""
        now = time.time()
        stale = [
            uid
            for uid, state in self._uploads.items()
            if now - state.created_at > self.cleanup_timeout
        ]
        for uid in stale:
            part_file = self.uploads_dir / f"{uid}.part"
            if part_file.exists():
                part_file.unlink()
            del self._uploads[uid]
        return len(stale)


class SyncServer:
    """Server-side sync logic backed by a KaydetService instance."""

    def __init__(self, service: KaydetService) -> None:
        self.service = service

    # Convenience accessors for sync-specific DB operations
    @property
    def conn(self) -> sqlite3.Connection:
        return self.service.conn

    @property
    def storage_dir(self):
        return self.service.storage_dir

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
        elif msg.method == "sync":
            req = parse_request(msg)
            resp = self._handle_sync(req)
        elif msg.method == "search":
            req = parse_request(msg)
            resp = self._handle_search(req)
        elif msg.method == "delete":
            req = parse_request(msg)
            resp = self._handle_delete(req)
        elif msg.method == "update":
            req = parse_request(msg)
            resp = self._handle_update(req)
        elif msg.method == "get_entry":
            req = parse_request(msg)
            resp = self._handle_get_entry(req)
        elif msg.method == "list_tags":
            req = parse_request(msg)
            resp = self._handle_list_tags(req)
        elif msg.method == "get_stats":
            req = parse_request(msg)
            resp = self._handle_get_stats(req)
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

    def _handle_sync(
        self, req: SyncRequest
    ) -> SyncResponse:
        """Single round-trip sync: accept client entries, return changes."""
        now = datetime.now()

        # 1. Record the current max sync_log id before applying
        #    client entries, so we don't send them back.
        cursor = self.conn.cursor()
        cursor.execute("SELECT MAX(id) FROM sync_log")
        pre_apply_max = cursor.fetchone()[0] or 0

        # 2. Apply client's entries (same as push)
        for entry_data in req.entries:
            try:
                self._upsert_entry(entry_data, req.device_id, now)
            except Exception as exc:
                logger.warning(
                    "Failed to apply entry %s during sync: %s",
                    entry_data.entry_id, exc
                )

        # 3. Find changes since client's token, excluding
        #    entries we just applied from the client.
        cursor.execute(
            "SELECT id, entry_id, action FROM sync_log "
            "WHERE id > ? AND id <= ? ORDER BY id",
            (req.since, pre_apply_max),
        )
        rows = cursor.fetchall()

        # 4. Collect unique entry IDs to send back
        to_send: dict[str, str] = {}  # entry_id -> action
        for _log_id, entry_id, action in rows:
            to_send[entry_id] = action

        # 5. Load full entry data for created/updated
        entries: List[EntryData] = []
        for entry_id, action in to_send.items():
            if action in ("created", "updated"):
                loaded = self._load_entry(entry_id)
                if loaded:
                    entries.append(loaded)
            # For "deleted" entries, send a tombstone
            elif action == "deleted":
                entries.append(EntryData(
                    entry_id=entry_id,
                    source_file="",
                    timestamp="",
                    text="",
                    metadata={"_deleted": "true"},
                ))

        # 6. New token = max sync_log id now (after our applies)
        cursor.execute("SELECT MAX(id) FROM sync_log")
        new_token = cursor.fetchone()[0] or req.since

        return SyncResponse(
            entries=entries,
            new_token=new_token,
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

    def _load_entry(self, entry_id: str) -> Optional[EntryData]:
        """Load a single entry via KaydetService."""
        from kaydet_core.secrets import get_secret

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

        # Get encrypted secret (check disk fallback)
        encrypted = get_secret(entry_id, self.storage_dir)
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
        resolved_entries: List[EntryData] = []

        for entry_data in req.entries:
            try:
                entry_id = self._upsert_entry(
                    entry_data, req.device_id, now
                )
                if entry_id:
                    accepted += 1
                    loaded = self._load_entry(entry_id)
                    if loaded:
                        resolved_entries.append(loaded)
            except Exception as e:
                errors.append(
                    f"Entry {entry_data.entry_id}: {e}"
                )

        return PushEntriesResponse(
            accepted=accepted,
            conflicts=conflicts,
            errors=errors,
            entries=resolved_entries,
        )

    def _handle_attachment_get(
        self, req: AttachmentGetRequest
    ) -> AttachmentGetResponse:
        """Serve an attachment file."""
        attachments_dir = self.storage_dir / "attachments"
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
        attachments_dir = self.storage_dir / "attachments"
        attachments_dir.mkdir(exist_ok=True)
        filepath = attachments_dir / req.filename
        filepath.write_bytes(base64.b64decode(req.data))
        return AttachmentPutResponse(
            filename=req.filename, stored=True
        )

    def _handle_search(
        self, req: SearchRequest
    ) -> SearchResponse:
        """Search entries using KaydetService (server-side FTS)."""
        result = self.service.search_entries(req.query)
        if not result.get("success"):
            return SearchResponse(entries=[], total=0)

        entries: list[EntryData] = []
        for match in result.get("matches", [])[:req.limit]:
            entry_id = str(match.get("id", ""))
            if entry_id:
                loaded = self._load_entry(entry_id)
                if loaded:
                    entries.append(loaded)

        return SearchResponse(
            entries=entries, total=len(entries)
        )

    def _handle_get_entry(
        self, req: GetEntryRequest
    ) -> GetEntryResponse:
        """Return a single entry by ID."""
        loaded = self._load_entry(req.entry_id)
        if loaded:
            return GetEntryResponse(entry=loaded, found=True)
        return GetEntryResponse(
            found=False, error=f"Entry {req.entry_id} not found"
        )

    def _handle_list_tags(
        self, req: ListTagsRequest
    ) -> ListTagsResponse:
        """Return all tags with counts."""
        result = self.service.list_tags()
        return ListTagsResponse(tags=result.get("tags", []))

    def _handle_get_stats(
        self, req: GetStatsRequest
    ) -> GetStatsResponse:
        """Return calendar stats."""
        result = self.service.get_stats(
            year=req.year, month=req.month
        )
        if not result.get("success"):
            return GetStatsResponse()
        return GetStatsResponse(
            year=result["year"],
            month=result["month"],
            days=result["days"],
            total_entries=result["total_entries"],
        )

    def _handle_delete(
        self, req: DeleteEntryRequest
    ) -> DeleteEntryResponse:
        """Delete an entry by ID."""
        try:
            result = self.service.delete_entry(req.entry_id)
            if result.get("success"):
                return DeleteEntryResponse(
                    entry_id=req.entry_id, deleted=True
                )
            return DeleteEntryResponse(
                entry_id=req.entry_id,
                deleted=False,
                error=result.get("error", "Delete failed"),
            )
        except Exception as e:
            return DeleteEntryResponse(
                entry_id=req.entry_id,
                deleted=False,
                error=str(e),
            )

    def _handle_update(
        self, req: UpdateEntryRequest
    ) -> UpdateEntryResponse:
        """Update an existing entry."""
        try:
            result = self.service.update_entry(
                req.entry_id,
                text=req.text,
                metadata=req.metadata,
                tags=req.tags,
            )
            if result.get("success"):
                return UpdateEntryResponse(
                    entry_id=req.entry_id, updated=True
                )
            return UpdateEntryResponse(
                entry_id=req.entry_id,
                updated=False,
                error=result.get("error", "Update failed"),
            )
        except Exception as e:
            return UpdateEntryResponse(
                entry_id=req.entry_id,
                updated=False,
                error=str(e),
            )

    def _upsert_entry(
        self,
        entry_data: EntryData,
        device_id: str,
        now: datetime,
    ) -> Optional[str]:
        """Insert or update an entry on the server. Returns the entry_id or None if skipped."""
        # Check if entry already exists by ID
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT id, updated_at FROM entries WHERE id = ?",
            (entry_data.entry_id,),
        )
        existing = cursor.fetchone()

        if existing:
            existing_id, server_updated_at = existing
            # Reject if server copy is newer.
            # Truncate to 19 chars ("YYYY-MM-DDTHH:MM:SS") before comparing
            # so trailing "Z" or "+HH:MM" suffixes don't skew ordering.
            if server_updated_at and entry_data.updated_at:
                if server_updated_at[:19] > entry_data.updated_at[:19]:
                    return None  # server has newer data, skip
            self._update_existing_entry(
                existing_id, entry_data, device_id
            )
            return existing_id
        else:
            return self._create_new_entry(entry_data, device_id, now)

    def _update_existing_entry(
        self,
        existing_id: str,
        entry_data: EntryData,
        device_id: str,
    ) -> None:
        """Update an existing server entry with pushed data."""
        text = entry_data.text
        if entry_data.attachments:
            att_refs = " ".join(
                f"attachment:{a}" for a in entry_data.attachments
            )
            text = f"{text} {att_refs}"

        self.service.update_entry(
            existing_id,
            text=text,
            metadata=entry_data.metadata or None,
            tags=entry_data.tags or None,
        )

        if entry_data.encrypted_secret:
            from kaydet_core.secrets import store_secret

            encrypted = base64.b64decode(
                entry_data.encrypted_secret
            )
            store_secret(existing_id, encrypted, self.storage_dir)

    def _create_new_entry(
        self,
        entry_data: EntryData,
        device_id: str,
        now: datetime,
    ) -> Optional[str]:
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

        # Append attachment references to text so they
        # get written into the day file header
        text = entry_data.text
        if entry_data.attachments:
            att_refs = " ".join(
                f"attachment:{a}" for a in entry_data.attachments
            )
            text = f"{text} {att_refs}"

        # If client sent no metadata/tags, parse them from text
        metadata = entry_data.metadata or None
        tags = entry_data.tags or None
        if not metadata and not tags:
            _, parsed_meta, parsed_tags = partition_entry_tokens(text.split())
            metadata = parsed_meta or None
            tags = list(parsed_tags) or None

        result = self.service.add_entry(
            text=text,
            metadata=metadata,
            tags=tags,
            at=entry_at,
            entry_id=entry_data.entry_id,
        )

        if not result.get("success"):
            return None

        new_id = result["entry_id"]

        if entry_data.encrypted_secret:
            from kaydet_core.secrets import store_secret

            encrypted = base64.b64decode(
                entry_data.encrypted_secret
            )
            store_secret(new_id, encrypted, self.storage_dir)

        return new_id


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
