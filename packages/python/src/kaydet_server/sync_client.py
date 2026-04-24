"""Sync client: single round-trip sync with a remote server."""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

from kaydet_core.service import KaydetService
from kaydet_core.sync_protocol import (
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
        """Multi-page sync: send local changes, pull all remote changes."""
        device_id = self.config.get("device_id")
        if not device_id:
            import secrets
            device_id = secrets.token_hex(4)
            self._update_config("device_id", device_id)

        local_entries, new_pushed_log_id = self._collect_local_changes()

        pulled_total = 0
        att_stats_total = {"downloaded": 0, "uploaded": 0}

        entries_to_push = [e.to_dict() for e in local_entries]
        since = int(self.config.get("sync_token", "0"))

        while True:
            req = ProtocolMessage(
                method="sync",
                body={
                    "since": since,
                    "entries": entries_to_push,
                    "device_id": device_id,
                },
            )
            resp_msg = self.transport.send(req)
            resp = parse_response("sync", resp_msg.body)

            entries_to_push = []

            for entry_data in resp.entries:
                if entry_data.metadata.get("_deleted") == "true" or getattr(entry_data, "deleted", False):
                    self._delete_local_entry(entry_data.entry_id)
                else:
                    self._apply_entry(entry_data)
                pulled_total += 1

            page_att_stats = self._sync_packets(
                resp.entries, local_entries if not pulled_total else []
            )
            att_stats_total["downloaded"] += page_att_stats["downloaded"]
            att_stats_total["uploaded"] += page_att_stats["uploaded"]

            since = resp.server_time

            if not resp.has_more:
                break

        if pulled_total > 0:
            self.service.reload_rust()

        if new_pushed_log_id:
            self._update_config("last_pushed_log_id", str(new_pushed_log_id))

        self._update_config("sync_token", str(since))

        return {
            "pushed": len(local_entries),
            "pulled": pulled_total,
            "token": since,
            "attachments_downloaded": att_stats_total["downloaded"],
            "attachments_uploaded": att_stats_total["uploaded"],
        }

    def _collect_local_changes(self) -> tuple[List[EntryData], int]:
        """Gather entries from sync_log that haven't been pushed yet."""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT id, entry_id, action FROM sync_log "
            "WHERE id > ? ORDER BY id",
            (int(self.config.get("last_pushed_log_id", "0")),),
        )
        rows = cursor.fetchall()
        if not rows:
            return [], 0

        entries = []
        for _log_id, entry_id, action in rows:
            entry_id = str(entry_id)
            if action in ("created", "updated"):
                entry_data = self._load_local_entry(entry_id)
                if entry_data:
                    entries.append(entry_data)

        new_max = rows[-1][0]
        return entries, new_max

    def _apply_entry(self, entry_data: EntryData) -> None:
        """Apply a remote entry to the local store."""
        if not entry_data.entry_id or len(entry_data.entry_id) > 64:
            logger.warning("Skipping entry with invalid ID: %r", entry_data.entry_id)
            return
        existing = self.service.get_entry(entry_data.entry_id)

        if existing.get("success"):
            self.service.update_entry(
                entry_data.entry_id,
                text=entry_data.text,
                metadata=entry_data.metadata or None,
                tags=entry_data.tags or None,
                _log_sync=False,
            )
        else:
            day_pattern = self.config.get("DAY_FILE_PATTERN", "%Y-%m-%d.txt")
            entry_at = None
            try:
                entry_date = datetime.strptime(entry_data.source_file, day_pattern)
                h, m = entry_data.timestamp.split(":")
                entry_at = entry_date.replace(hour=int(h), minute=int(m))
            except (ValueError, AttributeError):
                pass

            result = self.service.add_entry(
                text=entry_data.text,
                metadata=entry_data.metadata or None,
                tags=entry_data.tags or None,
                at=entry_at,
                entry_id=entry_data.entry_id,
                _log_sync=False,
            )
            if not result.get("success"):
                return

        if entry_data.encrypted_secret:
            import base64
            from kaydet_core.secrets import store_secret
            encrypted = base64.b64decode(entry_data.encrypted_secret)
            store_secret(entry_data.entry_id, encrypted, self.storage_dir)

    def _delete_local_entry(self, entry_id: str) -> None:
        self.service.delete_entry(entry_id, _log_sync=False)

    def _load_local_entry(self, entry_id: str) -> Optional[EntryData]:
        """Load an entry for pushing to the server."""
        import base64
        from kaydet_core.secrets import get_secret

        result = self.service.get_entry(entry_id)
        if not result.get("success"):
            return None

        entry = result["entry"]

        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT CAST(strftime('%s', MAX(created_at)) AS INTEGER) FROM sync_log WHERE entry_id = ?",
            (entry_id,),
        )
        row = cursor.fetchone()
        updated_at = row[0] if row and row[0] else None  # int unix timestamp

        encrypted = get_secret(entry_id, self.storage_dir)
        enc_b64 = None
        if encrypted:
            enc_b64 = base64.b64encode(encrypted).decode("ascii")

        return EntryData(
            entry_id=entry_id,
            source_file=f"{entry['date']}.txt" if entry.get("date") else "",
            timestamp=entry["timestamp"],
            text=entry["text"],
            tags=entry.get("tags", []),
            metadata=entry.get("metadata", {}),
            attachments=entry.get("attachments", []),
            encrypted_secret=enc_b64,
            updated_at=updated_at,
        )

    def _sync_packets(
        self,
        remote_entries: List[EntryData],
        local_entries: List[EntryData],
    ) -> Dict[str, int]:
        """Transfer entry packets (entry + attachments) via KYDT format."""
        from .sync_transport import HttpTransport
        import kaydet_core_rs as _rust

        if not isinstance(self.transport, HttpTransport):
            return {"downloaded": 0, "uploaded": 0}

        transport: HttpTransport = self.transport
        att_dir = self.storage_dir / "attachments"
        downloaded = 0
        uploaded = 0

        # Download: remote entries with attachments we're missing
        for entry in remote_entries:
            if not entry.attachments:
                continue
            missing = [a for a in entry.attachments if not (att_dir / a).exists()]
            if not missing:
                continue
            try:
                packet_bytes = transport.download_packet(entry.entry_id)
                packet = _rust.deserialize_packet(packet_bytes)
                att_dir.mkdir(parents=True, exist_ok=True)
                for name, data in packet["attachments"].items():
                    dest = att_dir / name
                    tmp = att_dir / f".{name}.tmp"
                    tmp.write_bytes(bytes(data))
                    tmp.rename(dest)
                    downloaded += 1
            except Exception as exc:
                logger.warning(
                    "Failed to download packet for %s: %s",
                    entry.entry_id, exc,
                )

        # Upload: local entries with attachments
        for entry in local_entries:
            if not entry.attachments:
                continue
            local_atts = {
                name: (att_dir / name).read_bytes()
                for name in entry.attachments
                if (att_dir / name).exists()
            }
            if not local_atts:
                continue
            try:
                result = self.service.get_entry(entry.entry_id)
                if not result.get("success"):
                    continue
                e = result["entry"]
                packet_bytes = _rust.serialize_packet(
                    entry_id=e["entry_id"],
                    timestamp=e["timestamp"],
                    text=e["text"],
                    attachments=local_atts,
                )
                transport.upload_packet(entry.entry_id, bytes(packet_bytes))
                uploaded += len(local_atts)
            except Exception as exc:
                logger.warning(
                    "Failed to upload packet for %s: %s",
                    entry.entry_id, exc,
                )

        return {"downloaded": downloaded, "uploaded": uploaded}

    def _update_config(self, key: str, value: str) -> None:
        from kaydet_core.utils import save_config_setting
        self.config[key] = value
        save_config_setting(self.service.config_dir, key, value)
