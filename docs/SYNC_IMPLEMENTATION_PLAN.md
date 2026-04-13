# Sync Implementation Plan

> Internal planning document. See SYNC_PROTOCOL.md for the protocol spec.
> **Status:** Phases 1-5 implemented on `feat/sync` branch (April 2026).

## Architecture

### Single Package, Two Roles

No repo split. `kaydet` is both client and server:

- `kaydet sync` — client commands
- `kaydet server` — server commands

Same binary, same codebase. The protocol layer is shared.

### Key Design Decisions

- **No full encryption.** Server stores entries as plain text, just like
  clients. Only `--secret` payloads are encrypted.
- **No RemoteKaydetService.** Every device runs LocalKaydetService —
  writes to disk, syncs separately.
- **No KEEP_LOCAL_COPY flag.** Every device keeps local files.
- **Server is a full kaydet instance** with its own STORAGE_DIR, txt
  files, attachments, and SQLite index.

### Transport Layer

Server supports two transports, same JSON protocol:

- **stdin/stdout** — local use, no network, no auth
- **HTTP(S)** — remote use, API key auth

Client config determines which transport to use:

```ini
[sync]
# Local: stdin transport (server binary path)
transport = stdin
server_path = /usr/local/bin/kaydet

# Remote: HTTP transport
transport = http
server = https://my-server.example.com
api_key = kyd_a1b2c3d4e5f6...
```

### Server Storage

The server is a full kaydet instance — it has its own STORAGE_DIR with
txt files, its own attachments directory, and its own SQLite index. Plus
additional tables for sync:

```sql
-- Changes feed: log of all entry mutations
CREATE TABLE sync_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id INTEGER NOT NULL,
    action TEXT NOT NULL,  -- 'created', 'updated', 'deleted'
    device_id TEXT,
    created_at TEXT NOT NULL
);

-- API keys for remote auth
CREATE TABLE sync_keys (
    key TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    last_used_at TEXT
);

-- Encrypted secrets (synced as opaque blobs)
CREATE TABLE secrets (
    entry_id INTEGER PRIMARY KEY,
    encrypted_data BLOB NOT NULL,
    FOREIGN KEY (entry_id) REFERENCES entries(id) ON DELETE CASCADE
);
```

### Client Storage

Client adds to its config:

```ini
[sync]
transport = http
server = https://my-server.example.com
api_key = kyd_a1b2c3d4e5f6...
sync_token = 67
secret_password = <stored locally, never sent to server, never synced>
```

The `secrets` table is also added to the client's SQLite for local
secret storage.

## New Modules

### `src/kaydet/sync_protocol.py`

Shared between client and server. Transport-agnostic.

- `SyncChangesRequest` / `SyncChangesResponse` dataclasses
- `SyncEntriesRequest` / `SyncEntriesResponse` dataclasses
- `PushEntriesRequest` / `PushEntriesResponse` dataclasses
- JSON serialization/deserialization

### `src/kaydet/sync_server.py`

Server-side logic.

- Reads from its own STORAGE_DIR + SQLite
- Writes sync_log on every entry mutation
- Handles: `/changes`, `/entries`, `/attachments`
- Transport adapters: stdin reader, HTTP handler

### `src/kaydet/sync_client.py`

Client-side logic.

- Stores sync_token in config
- Pull: fetch changes → fetch entries → write to local files
- Push: detect local changes since last sync → post entries
- Transport adapters: stdin writer, HTTP client

### `src/kaydet/sync_transport.py`

Transport abstraction.

- `StdinTransport` — spawn server process, write/read JSON via pipes
- `HttpTransport` — HTTP requests with API key header
- Both implement same interface: `request(method, path, body) → response`

### `src/kaydet/secrets.py`

Secret encryption for `--secret` flag.

- `encrypt_secret(plaintext, password)` → encrypted bytes
- `decrypt_secret(encrypted, password)` → plaintext
- AES-256-GCM, key derived from password via scrypt
- `store_secret(conn, entry_id, encrypted_data)` — save to SQLite
- `get_secret(conn, entry_id)` → encrypted bytes
- Uses `cryptography` lib (required dependency)

## CLI Commands

### Client

```
kaydet "text" --secret "sensitive"  — add entry with encrypted secret
kaydet get <id>                     — show entry + decrypted secret
kaydet sync                         — run sync now
kaydet sync setup                   — configure server + secret password
kaydet sync status                  — show last sync time, token, server
kaydet sync devices                 — list registered devices (from server)
```

### Server

```
kaydet server start                      — start server (stdin mode)
kaydet server start --transport http     — start HTTP server
kaydet server generate-key --name "x"    — create API key
kaydet server list-keys                  — list all keys
kaydet server revoke-key "x"             — revoke a key
```

## Sync Log Hook

Every entry mutation must write to sync_log. This hooks into existing
code:

- `database.add_entry()` → log 'created'
- `commands/edit.py` → log 'updated'
- `commands/delete.py` → log 'deleted'

The sync_log is append-only. It's the source of the changes feed.

### Detecting Local Changes (Client)

Client also writes sync_log locally. On sync, read local log entries
since last push, resolve each entry_id to its `date + timestamp`
identity, and send those to server. Same mechanism on both sides.

## Conflict Resolution Implementation

When pushing entries to server:

1. Server checks if entry already exists (by `date + timestamp`)
2. If conflict: compare modification timestamps, last-writer-wins
3. Server writes winning version, logs the change

Entry identity across devices uses `date + timestamp` as a natural key.
Same-day same-minute collision is near-zero for a single user. No UUID
needed — identity is derived from the entry itself, survives doctor
rebuilds, and doesn't pollute txt files.

## Attachment Sync

Attachments sync separately from entries:

1. Entry arrives with `attachments: ["51_photo.jpg"]`
2. Client checks if file exists locally
3. If not: `GET /attachments/51_photo.jpg`
4. If pushing: `POST /attachments` with file

Attachment filenames include entry_id prefix, so they're globally
unique within a kaydet instance.

## Implementation Order

### Phase 1: Secrets — Done

1. [x] `secrets.py` — encrypt/decrypt + SQLite storage
2. [x] `--secret` flag in CLI
3. [x] `kaydet get <id>` shows decrypted secret
4. [x] `secrets` table in database schema
5. [x] Tests: secret CRUD, encryption round-trip

### Phase 2: Protocol + Local Sync — Done

6. [x] `sync_protocol.py` — message dataclasses, JSON serialization
7. [x] Add `sync_log` table to database schema
8. [x] Hook sync_log writes into existing add/edit/delete
9. [x] `sync_server.py` — stdin transport only
10. [x] `sync_client.py` — stdin transport only
11. [x] `kaydet sync setup` — configure server
12. [x] `kaydet sync` command (local stdin mode)
13. [x] Tests: full round-trip sync between two local instances (6 e2e tests)

### Phase 3: Remote — Done

14. [x] `sync_transport.py` — HTTP transport
15. [x] `kaydet server start --transport http`
16. [x] API key auth: generate, validate, revoke
17. [x] `kaydet sync` with HTTP config
18. [x] HTTP error handling (401, 5xx, unreachable)

### Phase 4: Attachments — Done

19. [x] Attachment upload/download via `attachment_get`/`attachment_put`
20. [x] Client attachment pull/push logic
21. [x] Tests: attachment sync

### Phase 5: Polish — Done

22. [x] `kaydet sync status`
23. [ ] `kaydet sync devices` (stub only)
24. [x] `kaydet server list-keys`
25. [x] Error handling hardening
26. [x] Conflict resolution with `updated_at` (last-writer-wins)
27. [x] Sync loop prevention (`__pull__` marker)
28. [x] SoC refactoring (server/client use KaydetService)

## What Doesn't Change

- `KaydetService` API (sync_log hook + secret support added)
- Entry file format (txt files untouched — secrets never in txt)
- Existing CLI commands (new flags added, existing behavior preserved)
- SQLite index schema (new tables added, existing untouched)
- MCP server (secret + sync tools may be added later)

## Resolved Questions

- [x] **Entry identity across devices:** `date + timestamp` (D option).
  Same-day same-minute collision is near-zero for single user. If
  insufficient, revisit with UUID later.
- [x] **Terminology:** storage > days (day file) > entry > (attachment,
  secret). No "diary", "log", or "record". (TODO #1390)
- [x] **Attachment file structure:** Documented in FILE_FORMAT.md.
  `{entry_id}_{filename}` in `attachments/` dir. (TODO #1389 done)
- [x] **`cryptography` lib:** Required dependency. 3.3MB, pre-built
  wheels on all platforms. ZEN-STANDALONE: batteries included.
- [x] **MCP server secret tools:** Yes. ZEN-AI-PARITY + ZEN-USER-CHOICE.
  No extra permission layer — MCP client decides approval UX.
- [x] **Secret password:** Shared across devices, stored in each
  client's config. Never synced — user enters same password on each
  new device. First `--secret` usage prompts for password creation
  (ZEN-INTUITIVE).
