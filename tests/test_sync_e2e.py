"""End-to-end sync test between two local kaydet instances."""

from __future__ import annotations

from configparser import ConfigParser

from kaydet import database
from kaydet.service import KaydetService
from kaydet.sync_client import SyncClient
from kaydet.sync_protocol import ProtocolMessage
from kaydet.sync_server import SyncServer
from kaydet.sync_transport import SyncTransport


def _add_and_log(service, **kwargs):
    """Add an entry and log it to sync_log (simulating CLI/MCP behavior)."""
    result = service.add_entry(**kwargs)
    assert result["success"]
    database.log_sync_action(service.conn, result["entry_id"], "created")
    return result


class DirectTransport(SyncTransport):
    """In-process transport that calls SyncServer directly."""

    def __init__(self, server: SyncServer) -> None:
        self.server = server

    def send(self, msg: ProtocolMessage) -> ProtocolMessage:
        return self.server.handle_message(msg)


def _make_instance(tmp_path, name, prefix="d"):
    """Create a kaydet instance (service + DB) in a subdirectory."""
    base = tmp_path / name
    storage = base / "storage"
    storage.mkdir(parents=True)
    config_dir = base / "config"
    config_dir.mkdir(parents=True)

    db_path = base / "index.db"
    conn = database.get_db_connection(db_path)
    database.initialize_database(conn)

    cp = ConfigParser(interpolation=None)
    cp["SETTINGS"] = {
        "DAY_FILE_PATTERN": "%Y-%m-%d.txt",
        "DAY_TITLE_PATTERN": "%Y/%m/%d/ - %A",
        "STORAGE_DIR": str(storage),
        "EDITOR": "cat",
        "sync_token": "0",
        "DEVICE_PREFIX": prefix,
        "LAST_ID": "0",
    }

    service = KaydetService(
        config=cp["SETTINGS"],
        config_dir=config_dir,
        storage_dir=storage,
        conn=conn,
    )
    return service


class TestE2ESync:
    def test_push_to_server(self, tmp_path):
        """Add entry on client, sync to server."""
        client_svc = _make_instance(tmp_path, "client")
        server_svc = _make_instance(tmp_path, "server")

        server = SyncServer(server_svc)
        client = SyncClient(client_svc, DirectTransport(server))

        _add_and_log(client_svc, text="Hello from client")

        result = client.sync()
        assert result["pushed"] == 1

        server_entries = server_svc.list_recent_entries(limit=10)
        texts = [e["text"] for e in server_entries["entries"]]
        assert any("Hello from client" in t for t in texts)

    def test_pull_from_server(self, tmp_path):
        """Add entry on server, sync to client."""
        client_svc = _make_instance(tmp_path, "client")
        server_svc = _make_instance(tmp_path, "server")

        server = SyncServer(server_svc)
        client = SyncClient(client_svc, DirectTransport(server))

        _add_and_log(server_svc, text="Hello from server")

        result = client.sync()
        assert result["pulled"] == 1

        client_entries = client_svc.list_recent_entries(limit=10)
        texts = [e["text"] for e in client_entries["entries"]]
        assert any("Hello from server" in t for t in texts)

    def test_bidirectional_sync(self, tmp_path):
        """Both sides add entries, single sync merges them."""
        client_svc = _make_instance(tmp_path, "client", prefix="c")
        server_svc = _make_instance(tmp_path, "server", prefix="s")

        server = SyncServer(server_svc)
        client = SyncClient(client_svc, DirectTransport(server))

        _add_and_log(client_svc, text="Client note")
        _add_and_log(server_svc, text="Server note")

        result = client.sync()
        assert result["pushed"] == 1
        assert result["pulled"] >= 1

        # Client has both
        client_texts = [
            e["text"]
            for e in client_svc.list_recent_entries(limit=10)["entries"]
        ]
        assert any("Client note" in t for t in client_texts)
        assert any("Server note" in t for t in client_texts)

        # Server has both
        server_texts = [
            e["text"]
            for e in server_svc.list_recent_entries(limit=10)["entries"]
        ]
        assert any("Client note" in t for t in server_texts)
        assert any("Server note" in t for t in server_texts)

    def test_no_sync_loop(self, tmp_path):
        """Synced entries must NOT bounce back on next sync."""
        client_svc = _make_instance(tmp_path, "client")
        server_svc = _make_instance(tmp_path, "server")

        server = SyncServer(server_svc)
        client = SyncClient(client_svc, DirectTransport(server))

        _add_and_log(server_svc, text="Server entry")

        # First sync: pull server entry
        first = client.sync()
        assert first["pulled"] == 1

        # Second sync: nothing should happen
        second = client.sync()
        assert second["pushed"] == 0
        assert second["pulled"] == 0

    def test_multiple_syncs_no_duplication(self, tmp_path):
        """Repeated syncs must not create duplicate entries."""
        client_svc = _make_instance(tmp_path, "client")
        server_svc = _make_instance(tmp_path, "server")

        server = SyncServer(server_svc)
        client = SyncClient(client_svc, DirectTransport(server))

        _add_and_log(client_svc, text="Only once")
        client.sync()

        result = client.sync()
        assert result["pushed"] == 0
        assert result["pulled"] == 0

        matching = [
            e
            for e in server_svc.list_recent_entries(limit=10)["entries"]
            if "Only once" in e["text"]
        ]
        assert len(matching) == 1

    def test_secret_syncs(self, tmp_path):
        """Encrypted secrets should sync as opaque blobs."""
        from kaydet.secrets import (
            decrypt_secret,
            encrypt_secret,
            get_secret,
            store_secret,
        )

        client_svc = _make_instance(tmp_path, "client")
        server_svc = _make_instance(tmp_path, "server")

        server = SyncServer(server_svc)
        client = SyncClient(client_svc, DirectTransport(server))

        result = _add_and_log(client_svc, text="Secret entry")
        eid = result["entry_id"]
        password = "test-password"
        encrypted = encrypt_secret("my secret", password)
        store_secret(eid, encrypted, client_svc.storage_dir)

        client.sync()

        # Find the synced entry's secret on server
        server_ids = [
            r[0]
            for r in server_svc.conn.execute(
                "SELECT id FROM entries"
            ).fetchall()
        ]
        found_secret = False
        for sid in server_ids:
            enc = get_secret(sid, server_svc.storage_dir)
            if enc:
                decrypted = decrypt_secret(enc, password)
                if decrypted == "my secret":
                    found_secret = True
                    break
        assert found_secret
