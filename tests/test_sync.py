"""Tests for sync_log hooks and sync server/client."""

import base64

import pytest

from kaydet import database
from kaydet.service import KaydetService
from kaydet.sync_protocol import (
    EntryData,
    ProtocolMessage,
    parse_response,
)
from kaydet.sync_server import (
    SyncServer,
    generate_api_key,
    list_api_keys,
    revoke_api_key,
    validate_api_key,
)


@pytest.fixture
def sync_env(tmp_path):
    """Set up a full kaydet environment for sync tests."""
    from configparser import ConfigParser

    storage_dir = tmp_path / "storage"
    storage_dir.mkdir()
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    db_path = tmp_path / "index.db"
    conn = database.get_db_connection(db_path)
    database.initialize_database(conn)

    cp = ConfigParser(interpolation=None)
    cp["SETTINGS"] = {
        "DAY_FILE_PATTERN": "%Y-%m-%d.txt",
        "DAY_TITLE_PATTERN": "%Y/%m/%d/ - %A",
        "STORAGE_DIR": str(storage_dir),
        "EDITOR": "cat",
        "DEVICE_PREFIX": "d",
        "LAST_ID": "0",
    }
    config = cp["SETTINGS"]

    service = KaydetService(
        config=config,
        config_dir=config_dir,
        storage_dir=storage_dir,
        conn=conn,
    )

    return conn, storage_dir, config, config_dir, service


class TestSyncLogHooks:
    def test_log_sync_action_created(self, sync_env):
        conn, storage_dir, config, config_dir, service = sync_env
        database.add_entry(
            conn,
            "2025-01-01.txt",
            "10:00",
            ["test"],
            "hello",
            {},
            entry_id="d1"
        )
        database.log_sync_action(conn, "d1", "created")
        cursor = conn.cursor()
        cursor.execute(
            "SELECT entry_id, action FROM sync_log"
        )
        rows = cursor.fetchall()
        assert len(rows) == 1
        assert rows[0][1] == "created"
        assert rows[0][0] == "d1"

    def test_multiple_logs(self, sync_env):
        conn, *_ = sync_env
        database.add_entry(
            conn, "2025-01-01.txt", "10:00", [], "a", {}, entry_id="d1"
        )
        database.add_entry(
            conn, "2025-01-01.txt", "11:00", [], "b", {}, entry_id="d2"
        )
        database.log_sync_action(conn, "d1", "created")
        database.log_sync_action(conn, "d2", "created")
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM sync_log")
        assert cursor.fetchone()[0] == 2


class TestSyncServer:
    def test_handle_changes_empty(self, sync_env):
        conn, storage_dir, config, config_dir, service = sync_env
        server = SyncServer(service)
        msg = ProtocolMessage(
            method="changes", body={"since": 0}
        )
        resp = server.handle_message(msg)
        assert resp.method == "changes"
        changes = parse_response("changes", resp.body)
        assert len(changes.changes) == 0

    def test_handle_changes_returns_entries(self, sync_env):
        conn, storage_dir, config, config_dir, service = sync_env
        database.add_entry(
            conn,
            "2025-01-01.txt",
            "10:00",
            ["work"],
            "hello",
            {},
            entry_id="d1"
        )
        database.log_sync_action(conn, "d1", "created")

        server = SyncServer(service)
        msg = ProtocolMessage(
            method="changes", body={"since": 0}
        )
        resp = server.handle_message(msg)
        changes = parse_response("changes", resp.body)
        assert len(changes.changes) == 1
        assert changes.changes[0].action == "created"
        assert changes.changes[0].entry_id == "d1"
        assert changes.new_token > 0

    def test_handle_entries(self, sync_env):
        conn, storage_dir, config, config_dir, service = sync_env
        # Create entry and the day file it points to
        eid = database.add_entry(
            conn,
            "2025-01-01.txt",
            "10:00",
            ["work"],
            "hello world",
            {},
            entry_id="d1"
        )
        day_file = storage_dir / "2025-01-01.txt"
        day_file.write_text(
            "2025/01/01/ - Wednesday\n"
            "---\n"
            f"10:00 [{eid}]: hello world #work\n",
            encoding="utf-8",
        )

        server = SyncServer(service)
        msg = ProtocolMessage(
            method="entries", body={"entry_ids": [eid]}
        )
        resp = server.handle_message(msg)
        entries = parse_response("entries", resp.body)
        assert len(entries.entries) == 1
        assert "hello world" in entries.entries[0].text
        assert entries.entries[0].entry_id == "d1"

    def test_handle_push(self, sync_env):
        conn, storage_dir, config, config_dir, service = sync_env
        server = SyncServer(service)

        entry = EntryData(
            entry_id="client1",
            source_file="2025-06-01.txt",
            timestamp="14:00",
            text="pushed entry",
            tags=["sync"],
        )
        from dataclasses import asdict

        msg = ProtocolMessage(
            method="push",
            body={
                "entries": [asdict(entry)],
                "device_id": "test-device",
            },
        )
        resp = server.handle_message(msg)
        push_resp = parse_response("push", resp.body)
        assert push_resp.accepted == 1

    def test_push_rejects_stale_entry(self, sync_env):
        """Server should skip update when server copy is newer."""
        conn, storage_dir, config, config_dir, service = sync_env
        server = SyncServer(service)

        # Create an entry directly on server
        result = service.add_entry(text="original text")
        assert result["success"]
        eid = result["entry_id"]

        # Manually set a recent updated_at on the server
        conn.execute(
            "UPDATE entries SET updated_at = ? WHERE id = ?",
            ("2025-06-01T14:00:00", eid),
        )

        # Get the source_file and timestamp from DB
        cursor = conn.cursor()
        cursor.execute(
            "SELECT source_file, timestamp FROM entries "
            "WHERE id = ?",
            (eid,),
        )
        source_file, ts = cursor.fetchone()

        from dataclasses import asdict

        # Push a stale version of the same entry (same ID)
        stale = EntryData(
            entry_id=eid,
            source_file=source_file,
            timestamp=ts,
            text="original text",
            tags=[],
            metadata={"status": "stale"},
            updated_at="2025-05-01T10:00:00",
        )
        msg = ProtocolMessage(
            method="push",
            body={
                "entries": [asdict(stale)],
                "device_id": "device-b",
            },
        )
        server.handle_message(msg)

        # Verify the stale metadata was NOT applied
        cursor.execute(
            "SELECT meta_value FROM metadata "
            "WHERE entry_id = ? AND meta_key = 'status'",
            (eid,),
        )
        row = cursor.fetchone()
        # Either no status metadata, or it's not "stale"
        assert row is None or row[0] != "stale"

    def test_handle_sync_single_roundtrip(self, sync_env):
        """The sync method accepts entries and returns changes."""
        conn, storage_dir, config, config_dir, service = sync_env

        # Create an entry on server (DB + day file)
        database.add_entry(
            conn, "2025-01-01.txt", "10:00", ["work"], "server entry",
            {}, entry_id="d1"
        )
        database.log_sync_action(conn, "d1", "created")
        day_file = storage_dir / "2025-01-01.txt"
        day_file.write_text(
            "2025/01/01/ - Wednesday\n"
            "---\n"
            "10:00 [d1]: server entry #work\n",
            encoding="utf-8",
        )

        server = SyncServer(service)

        # Client sends its entry + token 0
        from dataclasses import asdict
        client_entry = EntryData(
            entry_id="c1",
            source_file="2025-01-02.txt",
            timestamp="14:00",
            text="client entry",
            tags=["sync"],
        )
        msg = ProtocolMessage(
            method="sync",
            body={
                "since": 0,
                "entries": [asdict(client_entry)],
                "device_id": "test-client",
            },
        )
        resp = server.handle_message(msg)
        sync_resp = parse_response("sync", resp.body)

        # Server should return its entry to the client
        assert len(sync_resp.entries) == 1
        assert sync_resp.entries[0].entry_id == "d1"
        assert sync_resp.new_token > 0

        # Verify client's entry was stored on server
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id FROM entries WHERE id = 'c1'"
        )
        assert cursor.fetchone() is not None

    def test_handle_sync_empty(self, sync_env):
        """Sync with no changes returns empty."""
        conn, storage_dir, config, config_dir, service = sync_env
        server = SyncServer(service)

        msg = ProtocolMessage(
            method="sync",
            body={"since": 0, "entries": [], "device_id": "x"},
        )
        resp = server.handle_message(msg)
        sync_resp = parse_response("sync", resp.body)
        assert len(sync_resp.entries) == 0

    def test_unknown_method(self, sync_env):
        conn, storage_dir, config, config_dir, service = sync_env
        server = SyncServer(service)
        msg = ProtocolMessage(method="bogus", body={})
        resp = server.handle_message(msg)
        assert "error" in resp.body

    def test_attachment_get_not_found(self, sync_env):
        conn, storage_dir, config, config_dir, service = sync_env
        server = SyncServer(service)
        msg = ProtocolMessage(
            method="attachment_get",
            body={"filename": "nonexistent.jpg"},
        )
        resp = server.handle_message(msg)
        att_resp = parse_response(
            "attachment_get", resp.body
        )
        assert att_resp.found is False

    def test_attachment_put_and_get(self, sync_env):
        conn, storage_dir, config, config_dir, service = sync_env
        server = SyncServer(service)

        data = base64.b64encode(b"file content").decode()
        put_msg = ProtocolMessage(
            method="attachment_put",
            body={
                "filename": "d1_test.txt",
                "data": data,
            },
        )
        put_resp = server.handle_message(put_msg)
        assert parse_response(
            "attachment_put", put_resp.body
        ).stored is True

        get_msg = ProtocolMessage(
            method="attachment_get",
            body={"filename": "d1_test.txt"},
        )
        get_resp = server.handle_message(get_msg)
        att = parse_response(
            "attachment_get", get_resp.body
        )
        assert att.found is True
        assert base64.b64decode(att.data) == b"file content"


class TestApiKeys:
    def test_generate_and_validate(self, sync_env):
        conn, *_ = sync_env
        key = generate_api_key(conn, "test-key")
        assert key.startswith("kyd_")
        assert validate_api_key(conn, key) is True

    def test_invalid_key(self, sync_env):
        conn, *_ = sync_env
        assert validate_api_key(conn, "bogus") is False

    def test_list_keys(self, sync_env):
        conn, *_ = sync_env
        generate_api_key(conn, "key1")
        generate_api_key(conn, "key2")
        keys = list_api_keys(conn)
        assert len(keys) == 2
        names = {k["name"] for k in keys}
        assert names == {"key1", "key2"}

    def test_revoke_key(self, sync_env):
        conn, *_ = sync_env
        key = generate_api_key(conn, "to-revoke")
        assert revoke_api_key(conn, "to-revoke") is True
        assert validate_api_key(conn, key) is False

    def test_revoke_nonexistent(self, sync_env):
        conn, *_ = sync_env
        assert revoke_api_key(conn, "nope") is False
