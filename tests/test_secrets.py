"""Tests for the secrets module."""

import pytest

from kaydet.secrets import (
    decrypt_secret,
    delete_secret,
    encrypt_secret,
    get_secret,
    store_secret,
)


class TestSpecFixture:
    """Validate against docs/spec/fixtures/encryption-v1.json."""

    def test_decrypt_fixture(self):
        import json
        from pathlib import Path

        fixture_path = (
            Path(__file__).parent.parent
            / "docs" / "spec" / "v1" / "fixtures" / "encryption.json"
        )
        fixture = json.loads(fixture_path.read_text())
        vec = fixture["vectors"][0]

        wire = bytes.fromhex(vec["wire_hex"])
        result = decrypt_secret(wire, vec["password"])
        assert result == vec["plaintext"]

    def test_encrypt_fixture_deterministic(self):
        import json
        from pathlib import Path

        from kaydet.secrets import _derive_key
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        fixture_path = (
            Path(__file__).parent.parent
            / "docs" / "spec" / "v1" / "fixtures" / "encryption.json"
        )
        fixture = json.loads(fixture_path.read_text())
        vec = fixture["vectors"][0]

        salt = bytes.fromhex(vec["salt_hex"])
        nonce = bytes.fromhex(vec["nonce_hex"])
        key = _derive_key(vec["password"], salt)
        assert key.hex() == vec["derived_key_hex"]

        aesgcm = AESGCM(key)
        ciphertext = aesgcm.encrypt(
            nonce, vec["plaintext"].encode("utf-8"), None
        )
        wire = salt + nonce + ciphertext
        assert wire.hex() == vec["wire_hex"]

    def test_tampered_wire_fails(self):
        import json
        from pathlib import Path

        from cryptography.exceptions import InvalidTag

        fixture_path = (
            Path(__file__).parent.parent
            / "docs" / "spec" / "v1" / "fixtures" / "encryption.json"
        )
        fixture = json.loads(fixture_path.read_text())
        vec = fixture["vectors"][0]

        wire = bytearray.fromhex(vec["wire_hex"])
        wire[-1] ^= 0xFF  # flip last byte
        with pytest.raises(InvalidTag):
            decrypt_secret(bytes(wire), vec["password"])


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
    def test_store_and_get(self, tmp_path):
        data = b"encrypted_blob_data"
        store_secret("d1", data, tmp_path)
        result = get_secret("d1", tmp_path)
        assert result == data
        assert (tmp_path / "secrets" / "d1.enc").exists()

    def test_get_nonexistent(self, tmp_path):
        assert get_secret("d999", tmp_path) is None

    def test_store_replaces(self, tmp_path):
        store_secret("d1", b"first", tmp_path)
        store_secret("d1", b"second", tmp_path)
        assert get_secret("d1", tmp_path) == b"second"
        assert (tmp_path / "secrets" / "d1.enc").read_bytes() == b"second"

    def test_delete(self, tmp_path):
        store_secret("d1", b"data", tmp_path)
        assert delete_secret("d1", tmp_path) is True
        assert get_secret("d1", tmp_path) is None
        assert not (tmp_path / "secrets" / "d1.enc").exists()

    def test_delete_nonexistent(self, tmp_path):
        assert delete_secret("d999", tmp_path) is False
