"""End-to-end sync test between two local kaydet instances."""

from __future__ import annotations

from configparser import ConfigParser

from kaydet import database
from kaydet.service import KaydetService
from kaydet.sync_client import SyncClient
from kaydet.sync_protocol import (
    ProtocolMessage,
)
from kaydet.sync_server import SyncServer
from kaydet.sync_transport import SyncTransport


class DirectTransport(SyncTransport):
    """In-process transport that calls SyncServer directly.

    No subprocess needed — ideal for testing.
    """

    def __init__(self, server: SyncServer) -> None:
        self.server = server

    def send(self, msg: ProtocolMessage) -> ProtocolMessage:
        return self.server.handle_message(msg)


def _make_instance(tmp_path, name):
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
    }

    service = KaydetService(
        config=cp["SETTINGS"],
        config_dir=config_dir,
        storage_dir=storage,
        conn=conn,
    )
    return service


class TestE2ESync:
    def test_basic_sync_flow(self, tmp_path):
        """Add entry on client, push to server, verify on server."""
        client_svc = _make_instance(tmp_path, "client")
        server_svc = _make_instance(tmp_path, "server")

        server = SyncServer(server_svc)
        transport = DirectTransport(server)
        client = SyncClient(client_svc, transport)

        # Add entry on client
        result = client_svc.add_entry(text="Hello from client")
        assert result["success"]

        # Push to server
        push_result = client.push()
        assert push_result["pushed"] == 1

        # Verify entry exists on server
        server_entries = server_svc.list_recent_entries(limit=10)
        texts = [
            e["text"] for e in server_entries["entries"]
        ]
        assert any("Hello from client" in t for t in texts)

    def test_pull_from_server(self, tmp_path):
        """Add entry on server, pull to client."""
        client_svc = _make_instance(tmp_path, "client")
        server_svc = _make_instance(tmp_path, "server")

        server = SyncServer(server_svc)
        transport = DirectTransport(server)
        client = SyncClient(client_svc, transport)

        # Add entry on server
        result = server_svc.add_entry(
            text="Hello from server"
        )
        assert result["success"]

        # Pull to client
        pull_result = client.pull()
        assert pull_result["pulled"] == 1

        # Verify entry exists on client
        client_entries = client_svc.list_recent_entries(
            limit=10
        )
        texts = [
            e["text"] for e in client_entries["entries"]
        ]
        assert any("Hello from server" in t for t in texts)

    def test_no_sync_loop(self, tmp_path):
        """Pulled entries must NOT be pushed back."""
        client_svc = _make_instance(tmp_path, "client")
        server_svc = _make_instance(tmp_path, "server")

        server = SyncServer(server_svc)
        transport = DirectTransport(server)
        client = SyncClient(client_svc, transport)

        # Add entry on server
        server_svc.add_entry(text="Server entry")

        # Pull to client
        client.pull()

        # Now push — should push 0 (the pulled entry
        # must not be pushed back)
        push_result = client.push()
        assert push_result["pushed"] == 0

    def test_bidirectional_sync(self, tmp_path):
        """Both sides add entries, full sync merges them."""
        client_svc = _make_instance(tmp_path, "client")
        server_svc = _make_instance(tmp_path, "server")

        server = SyncServer(server_svc)
        transport = DirectTransport(server)
        client = SyncClient(client_svc, transport)

        # Add entries on both sides
        client_svc.add_entry(text="Client note")
        server_svc.add_entry(text="Server note")

        # Full sync
        result = client.sync()

        # Client pushed its entry
        assert result["push"]["pushed"] == 1
        # Client pulled server's entry (may also pull back
        # its own pushed entry since the server logged it)
        assert result["pull"]["pulled"] >= 1

        # Verify client has both
        client_entries = client_svc.list_recent_entries(
            limit=10
        )
        client_texts = [
            e["text"] for e in client_entries["entries"]
        ]
        assert any("Client note" in t for t in client_texts)
        assert any("Server note" in t for t in client_texts)

        # Verify server has both
        server_entries = server_svc.list_recent_entries(
            limit=10
        )
        server_texts = [
            e["text"] for e in server_entries["entries"]
        ]
        assert any("Client note" in t for t in server_texts)
        assert any("Server note" in t for t in server_texts)

    def test_multiple_syncs_no_duplication(self, tmp_path):
        """Running sync multiple times must not create duplicates."""
        client_svc = _make_instance(tmp_path, "client")
        server_svc = _make_instance(tmp_path, "server")

        server = SyncServer(server_svc)
        transport = DirectTransport(server)
        client = SyncClient(client_svc, transport)

        # Add one entry and sync
        client_svc.add_entry(text="Only once")
        client.sync()

        # Sync again — nothing new should happen
        result = client.sync()
        assert result["push"]["pushed"] == 0
        assert result["pull"]["pulled"] == 0

        # Verify only one entry on server
        server_entries = server_svc.list_recent_entries(
            limit=10
        )
        matching = [
            e
            for e in server_entries["entries"]
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
        transport = DirectTransport(server)
        client = SyncClient(client_svc, transport)

        # Add entry with secret on client
        result = client_svc.add_entry(text="Secret entry")
        eid = result["entry_id"]
        password = "test-password"
        encrypted = encrypt_secret("my secret", password)
        store_secret(client_svc.conn, eid, encrypted)

        # Sync
        client.sync()

        # Verify secret is on server (as opaque blob)
        server_cursor = server_svc.conn.cursor()
        server_cursor.execute(
            "SELECT id FROM entries"
        )
        server_ids = [r[0] for r in server_cursor.fetchall()]
        # Find the synced entry
        found_secret = False
        for sid in server_ids:
            enc = get_secret(server_svc.conn, sid)
            if enc:
                decrypted = decrypt_secret(enc, password)
                if decrypted == "my secret":
                    found_secret = True
                    break
        assert found_secret
