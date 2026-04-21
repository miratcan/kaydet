"""Secret encryption and storage for kaydet entries."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional


def _derive_key(password: str, salt: bytes) -> bytes:
    """Derive a 256-bit key from a password using scrypt.

    Parameters match OWASP recommendations for interactive use:
    n=2**16, r=8, p=1 (doubles memory cost vs the previous n=2**14).
    """
    from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

    kdf = Scrypt(salt=salt, length=32, n=2**16, r=8, p=1)
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


# -- File-based storage (secrets/ directory is SoT) --


def _secrets_dir(storage_dir: Path) -> Path:
    """Return the secrets directory, creating it if needed."""
    d = storage_dir / "secrets"
    d.mkdir(exist_ok=True)
    return d


def store_secret(
    entry_id: str,
    encrypted_data: bytes,
    storage_dir: Path,
) -> None:
    """Save or replace an encrypted secret for an entry."""
    path = _secrets_dir(storage_dir) / f"{entry_id}.enc"
    path.write_bytes(encrypted_data)


def get_secret(
    entry_id: str,
    storage_dir: Path,
) -> Optional[bytes]:
    """Retrieve encrypted secret data for an entry, or None."""
    path = storage_dir / "secrets" / f"{entry_id}.enc"
    if path.exists():
        return path.read_bytes()
    return None


def delete_secret(
    entry_id: str,
    storage_dir: Path,
) -> bool:
    """Delete the secret file for an entry. Returns True if deleted."""
    path = storage_dir / "secrets" / f"{entry_id}.enc"
    if path.exists():
        path.unlink()
        return True
    return False
