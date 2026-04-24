"""Secret encryption and storage for kaydet entries."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import kaydet_core_rs as _rust

_SAFE_ENTRY_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9\-]{0,63}$")


def _safe_entry_id(entry_id: str) -> str:
    """Raise ValueError if entry_id would be unsafe as a file name component."""
    if not _SAFE_ENTRY_ID_RE.match(entry_id):
        raise ValueError(f"Invalid entry_id: {entry_id!r}")
    return entry_id


def encrypt_secret(plaintext: str, password: str) -> bytes:
    """Encrypt plaintext with AES-256-GCM, key derived via scrypt.

    Returns: salt (16) + nonce (12) + ciphertext + tag
    """
    return bytes(_rust.encrypt_secret(plaintext, password))


def decrypt_secret(encrypted: bytes, password: str) -> str:
    """Decrypt data produced by encrypt_secret."""
    return _rust.decrypt_secret(bytes(encrypted), password)


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
    path = _secrets_dir(storage_dir) / f"{_safe_entry_id(entry_id)}.enc"
    path.write_bytes(encrypted_data)


def get_secret(
    entry_id: str,
    storage_dir: Path,
) -> Optional[bytes]:
    """Retrieve encrypted secret data for an entry, or None."""
    path = storage_dir / "secrets" / f"{_safe_entry_id(entry_id)}.enc"
    if path.exists():
        return path.read_bytes()
    return None


def delete_secret(
    entry_id: str,
    storage_dir: Path,
) -> bool:
    """Delete the secret file for an entry. Returns True if deleted."""
    path = storage_dir / "secrets" / f"{_safe_entry_id(entry_id)}.enc"
    if path.exists():
        path.unlink()
        return True
    return False
