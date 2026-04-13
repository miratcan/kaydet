"""Secret encryption and storage for kaydet entries."""

from __future__ import annotations

import os
import sqlite3
from typing import Optional


def _derive_key(password: str, salt: bytes) -> bytes:
    """Derive a 256-bit key from a password using scrypt."""
    from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

    kdf = Scrypt(salt=salt, length=32, n=2**14, r=8, p=1)
    return kdf.derive(password.encode("utf-8"))


def encrypt_secret(plaintext: str, password: str) -> bytes:
    """Encrypt plaintext with AES-256-GCM, key derived via scrypt.

    Returns: salt (16) + nonce (12) + ciphertext + tag
    """
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    salt = os.urandom(16)
    key = _derive_key(password, salt)
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    return salt + nonce + ciphertext


def decrypt_secret(encrypted: bytes, password: str) -> str:
    """Decrypt data produced by encrypt_secret."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    salt = encrypted[:16]
    nonce = encrypted[16:28]
    ciphertext = encrypted[28:]
    key = _derive_key(password, salt)
    aesgcm = AESGCM(key)
    plaintext = aesgcm.decrypt(nonce, ciphertext, None)
    return plaintext.decode("utf-8")


# -- SQLite storage --


def store_secret(
    conn: sqlite3.Connection, entry_id: int, encrypted_data: bytes
) -> None:
    """Save or replace an encrypted secret for an entry."""
    conn.execute(
        "INSERT OR REPLACE INTO secrets (entry_id, encrypted_data) "
        "VALUES (?, ?)",
        (entry_id, encrypted_data),
    )


def get_secret(
    conn: sqlite3.Connection, entry_id: int
) -> Optional[bytes]:
    """Retrieve encrypted secret data for an entry, or None."""
    cursor = conn.execute(
        "SELECT encrypted_data FROM secrets WHERE entry_id = ?",
        (entry_id,),
    )
    row = cursor.fetchone()
    return row[0] if row else None


def delete_secret(
    conn: sqlite3.Connection, entry_id: int
) -> bool:
    """Delete the secret for an entry. Returns True if a row was deleted."""
    cursor = conn.execute(
        "DELETE FROM secrets WHERE entry_id = ?",
        (entry_id,),
    )
    return cursor.rowcount > 0
