# Kaydet Encryption Specification

|             |                    |
|-------------|--------------------|
| Version     | 1.0                |
| Status      | Frozen             |
| Date        | 2026-04-15         |

## Overview

Kaydet entries MAY carry an encrypted secret payload. The secret is
encrypted client-side with a user-chosen password. Servers transport
secrets as opaque blobs and MUST NOT attempt to decrypt them.

## Key Derivation

Implementations MUST derive the encryption key using scrypt with the
following parameters:

| Parameter | Value          |
|-----------|----------------|
| salt      | 16 random bytes |
| n         | 2^14 (16384)   |
| r         | 8              |
| p         | 1              |
| key_len   | 32 bytes       |

The password MUST be encoded as UTF-8 before passing to scrypt.

The output is a 256-bit (32-byte) key.

## Encryption

Implementations MUST use AES-256-GCM with the following parameters:

| Parameter | Value          |
|-----------|----------------|
| key       | 32 bytes (from key derivation) |
| nonce     | 12 random bytes |
| aad       | None (no additional authenticated data) |

The plaintext MUST be encoded as UTF-8 before encryption.

AES-GCM produces ciphertext + a 16-byte authentication tag. Most
libraries append the tag to the ciphertext automatically.

## Wire Format

The encrypted payload is a single byte sequence:

```
+--------+-------+-------------------+
| salt   | nonce | ciphertext + tag  |
| 16 B   | 12 B  | variable length   |
+--------+-------+-------------------+
```

| Offset  | Length   | Field            |
|---------|---------|------------------|
| 0       | 16      | scrypt salt      |
| 16      | 12      | AES-GCM nonce    |
| 28      | N + 16  | ciphertext + tag |

Where N is the byte length of the UTF-8 encoded plaintext.

Total payload length = 28 + N + 16 = N + 44 bytes.

## File Storage

Encrypted payloads are stored as raw bytes in files named
`{entry_id}.enc` inside the `secrets/` directory under STORAGE_DIR:

```
storage/
  secrets/
    d1.enc
    d5.enc
```

An implementation MUST NOT store secrets in plain text files or in
the SQLite index. The `secrets/` directory is the sole source of truth.

## Transport

When transmitting secrets over the sync protocol, implementations MUST
encode the raw bytes as base64 (standard alphabet, with padding). The
field name in `EntryData` is `encrypted_secret`.

A null or absent `encrypted_secret` field means the entry has no secret.

## Decryption

To decrypt:

1. Read bytes 0..16 as `salt`
2. Read bytes 16..28 as `nonce`
3. Read bytes 28.. as `ciphertext_with_tag`
4. Derive key from password + salt (same scrypt parameters)
5. Decrypt with AES-256-GCM using key + nonce
6. Decode the resulting bytes as UTF-8

If decryption fails (wrong password, corrupted data), AES-GCM MUST
raise an authentication error. Implementations MUST NOT silently
return garbage.

## Test Vector

The following test vector can be used to validate an implementation.

| Field       | Value |
|-------------|-------|
| password    | `test-password-123` |
| salt        | `00112233445566778899aabbccddeeff` (hex) |
| nonce       | `aabbccddeeff00112233aabb` (hex) |
| plaintext   | `Hello, world! This is a secret.` (ASCII, 31 bytes) |
| derived key | `a455522e74d20e05ad8be58c6fd8c37e8532067f62e00ea17f35a0633236ce69` (hex) |
| wire format | `00112233445566778899aabbccddeeff` `aabbccddeeff00112233aabb` `c1c6939bd8a9a3694531874967e10ae42cf98cab7f3dade911c50c6b52682d26e269310fa70009ce3b12106fc7ae15` (hex, split for readability: salt \| nonce \| ciphertext+tag) |
| wire length | 75 bytes |

An implementation MUST be able to:
1. Given the password and wire format bytes, decrypt to the plaintext
2. Given the password, salt, and nonce, produce the same wire format
3. Given a tampered wire format (e.g. last byte flipped), fail with an
   authentication error
4. Given a wrong password, fail with an authentication error

See `fixtures/encryption.json` for the machine-readable test vector.
