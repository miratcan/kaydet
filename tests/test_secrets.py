"""Tests for the secrets module."""

import sqlite3

import pytest

from kaydet.secrets import (
    decrypt_secret,
    delete_secret,
    encrypt_secret,
    get_secret,
    store_secret,
)


@pytest.fixture
def conn():
    """In-memory SQLite connection with secrets table."""
    c = sqlite3.Connection(":memory:")
    c.execute("PRAGMA foreign_keys = ON")
    c.execute(
        "CREATE TABLE entries ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "source_file TEXT NOT NULL,"
        "timestamp TEXT NOT NULL)"
    )
    c.execute(
        "CREATE TABLE IF NOT EXISTS secrets ("
        "entry_id INTEGER PRIMARY KEY,"
        "encrypted_data BLOB NOT NULL,"
        "FOREIGN KEY (entry_id) "
        "REFERENCES entries(id) ON DELETE CASCADE)"
    )
    c.execute(
        "INSERT INTO entries (source_file, timestamp) "
        "VALUES ('2025-01-01.txt', '10:00')"
    )
    return c


class TestEncryption:
    def test_round_trip(self):
        plaintext = "super secret data"
        password = "mypassword"
        encrypted = encrypt_secret(plaintext, password)
        assert isinstance(encrypted, bytes)
        assert len(encrypted) > 28  # salt + nonce + ciphertext
        result = decrypt_secret(encrypted, password)
        assert result == plaintext

    def test_different_passwords_produce_different_output(self):
        plaintext = "same text"
        enc1 = encrypt_secret(plaintext, "password1")
        enc2 = encrypt_secret(plaintext, "password2")
        assert enc1 != enc2

    def test_wrong_password_fails(self):
        from cryptography.exceptions import InvalidTag

        encrypted = encrypt_secret("secret", "correct")
        with pytest.raises(InvalidTag):
            decrypt_secret(encrypted, "wrong")

    def test_empty_plaintext(self):
        encrypted = encrypt_secret("", "password")
        assert decrypt_secret(encrypted, "password") == ""

    def test_unicode_plaintext(self):
        text = "Merhaba \u00e7al\u0131\u015fma #t\u00fcrk\u00e7e"
        encrypted = encrypt_secret(text, "pw")
        assert decrypt_secret(encrypted, "pw") == text


class TestSecretStorage:
    def test_store_and_get(self, conn):
        data = b"encrypted_blob_data"
        store_secret(conn, 1, data)
        result = get_secret(conn, 1)
        assert result == data

    def test_get_nonexistent(self, conn):
        assert get_secret(conn, 999) is None

    def test_store_replaces(self, conn):
        store_secret(conn, 1, b"first")
        store_secret(conn, 1, b"second")
        assert get_secret(conn, 1) == b"second"

    def test_delete(self, conn):
        store_secret(conn, 1, b"data")
        assert delete_secret(conn, 1) is True
        assert get_secret(conn, 1) is None

    def test_delete_nonexistent(self, conn):
        assert delete_secret(conn, 999) is False

    def test_cascade_delete(self, conn):
        store_secret(conn, 1, b"data")
        conn.execute("DELETE FROM entries WHERE id = 1")
        assert get_secret(conn, 1) is None
