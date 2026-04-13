# Kaydet Sync Protocol

> **Status:** Implemented (`feat/sync` branch, April 2026).

## Overview

Kaydet Sync enables multiple devices to keep their diary entries in sync
through a server. The server holds a full copy of all entries — plain
text, just like every client. Every device keeps its own complete copy.
If the server disappears, nothing is lost.

The sync model is **eventual consistency**: each device writes locally
first, syncs when a connection is available, and conflicts are resolved
automatically.

## Design Principles

- **[ZEN-PLAIN-TEXT]:** Entries remain `.txt` files on every device and on the server
- **[ZEN-OFFLINE]:** No internet needed to write; sync happens when available
- **[ZEN-STANDALONE]:** `kaydet sync` is a built-in subcommand
- **[ZEN-SELF-HEAL]:** Conflicts are resolved automatically

## Architecture

### Single Package, Two Roles

No repo split. `kaydet` is both client and server:

- `kaydet sync` — client commands
- `kaydet server` — server commands

Same binary, same codebase. The protocol layer is shared.

### Server is a Full Kaydet Instance

The server runs its own `KaydetService` with its own STORAGE_DIR,
txt files, attachments directory, and SQLite index. Plus additional
tables for sync:

- `sync_log` — append-only changes feed
- `sync_keys` — API key storage
- `secrets` — encrypted secret payloads

## Concepts

### Entry Identity

Entries are identified across devices by `source_file + timestamp +
text`. Same file, same time, same text = same entry. Different text at
the same timestamp = different entry (e.g., two entries at 14:00).

Entry IDs are local to each device and renormalized on sync.

### Sync Token

An integer representing a position in the server's `sync_log`. Clients
store their last sync token and present it to get only changes since.

### Changes Feed

The server maintains `sync_log` — an ordered log of all entry mutations
(created, updated, deleted). Clients request changes since their token.

## Secrets

Entries can carry an optional encrypted secret:

```
kaydet "evimdeki modemin sifresi" --secret "SarinmsakliKofte1999"
```

**Properties:**

- The `text` is plain text, stored normally in `.txt` files
- The `secret` is encrypted with AES-256-GCM (scrypt KDF) and stored
  only in SQLite — never in `.txt` files
- The server stores secrets as opaque blobs — it cannot read them
- Each device must know the encryption password to decrypt secrets
- Password is stored locally in each client's config, never synced

## Authentication

- **Local (stdin transport):** No authentication required
- **Remote (HTTP transport):** API key in `Authorization: Bearer <key>` header, mandatory

Keys are named and managed on the server:

```
kaydet server generate-key --name "macbook-air"
kaydet server list-keys
kaydet server revoke-key "macbook-air"
```

## Transports

The protocol is transport-agnostic. The same JSON messages work over:

- **stdin/stdout** — for local use (no network, no auth)
- **HTTP(S)** — for remote use, `POST /sync` endpoint

Both transports use the same envelope format:

```json
{"method": "changes", "body": {"since": 42}}
```

## Protocol Messages

All communication uses a `ProtocolMessage` envelope with a `method`
and `body`. Request and response share the same envelope.

### `changes` — Get Changes Feed

**Request body:**
```json
{"since": 42}
```

**Response body:**
```json
{
  "changes": [
    {"id": 43, "entry_id": 50, "action": "created", "device_id": "laptop", "created_at": "2026-04-13T14:00:00"},
    {"id": 44, "entry_id": 33, "action": "updated", "device_id": null, "created_at": "2026-04-13T14:05:00"},
    {"id": 45, "entry_id": 28, "action": "deleted", "device_id": "phone", "created_at": "2026-04-13T15:00:00"}
  ],
  "new_token": 45,
  "has_more": false
}
```

### `entries` — Fetch Full Entry Data

**Request body:**
```json
{"entry_ids": [50, 33]}
```

**Response body:**
```json
{
  "entries": [
    {
      "entry_id": 50,
      "source_file": "2026-04-13.txt",
      "timestamp": "14:30",
      "text": "Meeting notes #work",
      "tags": ["work"],
      "metadata": {"status": "done"},
      "attachments": [],
      "encrypted_secret": null,
      "updated_at": "2026-04-13T14:30:00"
    }
  ]
}
```

### `push` — Push Entries to Server

**Request body:**
```json
{
  "entries": [
    {
      "entry_id": 0,
      "source_file": "2026-04-13.txt",
      "timestamp": "16:00",
      "text": "New entry from mobile #daily",
      "tags": ["daily"],
      "metadata": {},
      "attachments": [],
      "encrypted_secret": null,
      "updated_at": "2026-04-13T16:00:00"
    }
  ],
  "device_id": "phone"
}
```

**Response body:**
```json
{
  "accepted": 1,
  "conflicts": 0,
  "errors": []
}
```

### `attachment_get` — Download Attachment

**Request body:**
```json
{"filename": "51_photo.jpg"}
```

**Response body:**
```json
{"filename": "51_photo.jpg", "data": "<base64>", "found": true}
```

### `attachment_put` — Upload Attachment

**Request body:**
```json
{"filename": "51_photo.jpg", "data": "<base64>"}
```

**Response body:**
```json
{"filename": "51_photo.jpg", "stored": true}
```

## Sync Flow

```
Client                              Server
  |                                   |
  |  push (local changes)            |
  |---------------------------------->|
  |  { accepted: 2 }                 |
  |<----------------------------------|
  |                                   |
  |  changes (since last token)      |
  |---------------------------------->|
  |  { changes: [...], new_token }   |
  |<----------------------------------|
  |                                   |
  |  entries (fetch changed IDs)     |
  |---------------------------------->|
  |  { entries: [...] }              |
  |<----------------------------------|
  |                                   |
  |  attachment_get (if needed)      |
  |---------------------------------->|
  |  { data: "<base64>" }            |
  |<----------------------------------|
  |                                   |
  |  (write to local files)          |
  |  (mark pull log as non-local)    |
  |                                   |
  Done. Client stores new token.
```

**Push-first order** prevents pulled entries from being immediately
pushed back in the next sync cycle.

### Sync Loop Prevention

- Pushed log entries are marked with the device's `device_id`
- Pulled log entries are marked with `__pull__`
- Only `device_id IS NULL` log entries are pushed

## Conflict Resolution

### Last-Writer-Wins (with timestamp)

When the same entry exists on both sides:

1. Compare `updated_at` timestamps
2. The newer one wins — the stale push is silently skipped
3. If no `updated_at` available, the push is accepted

### Entry Identity

Two entries at the same `source_file + timestamp` are considered the
same entry **only if their text matches**. Different text at the same
timestamp = different entries (both are kept).

### Deletions

Deletions are logged in `sync_log` with `action: "deleted"`. The
client removes the entry from its local index on pull.

## CLI Commands

### Client

```
kaydet "text" --secret "sensitive"   Add entry with encrypted secret
kaydet --get <id>                    Show entry + decrypted secret
kaydet sync                          Run sync (push then pull)
kaydet sync setup                    Configure server connection
kaydet sync status                   Show sync token, transport, server
```

### Server

```
kaydet server start                       Start stdin server
kaydet server start --transport http      Start HTTP server
kaydet server start --host 0.0.0.0        Bind to all interfaces
kaydet server generate-key --name "x"     Create API key
kaydet server list-keys                   List all keys
kaydet server revoke-key "x"              Revoke a key
```

## Error Handling

- **Network failure during sync:** Client retries from last token.
- **Server unavailable:** Client continues offline.
- **Invalid API key:** Server returns 401.
- **HTTP errors:** Client wraps urllib errors in `ConnectionError`.
- **Unknown path:** Server returns 404 for non-`/sync` paths.
