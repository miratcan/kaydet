# Kaydet Sync Protocol Specification

|             |                    |
|-------------|--------------------|
| Version     | 1.0                |
| Status      | Frozen             |
| Date        | 2026-04-15         |

## Overview

The sync protocol enables multiple kaydet nodes to synchronize entries.
Every node is a full kaydet instance with its own storage, index, and
secrets. Sync is peer-to-peer and opportunistic — nodes sync when
connectivity allows.

The protocol follows a **fat-server, dumb-client** model. The primary
sync method is a single round-trip: the client sends its local changes
and receives remote changes in one call. All conflict resolution happens
server-side.

## Design Principles

- **ZEN-OFFLINE:** Nodes work independently; sync is optional
- **ZEN-PLAIN-TEXT:** Sync moves entries between nodes; each node
  writes its own plain text day files
- **ZEN-SELF-HEAL:** Conflicts are resolved automatically
- **ZEN-AGNOSTIC:** Any language can implement a client — the protocol
  is simple JSON over any transport

## Transport

The protocol is transport-agnostic. All messages are JSON objects
exchanged via a `ProtocolMessage` envelope:

```json
{"method": "sync", "body": { ... }}
```

Supported transports:

| Transport | Use case | Authentication |
|-----------|----------|----------------|
| stdin/stdout | Local (same machine) | None |
| HTTP(S) | Remote | `Authorization: Bearer <key>` |

Both transports use the same envelope format. The HTTP transport
sends the envelope as a POST body to a single endpoint (e.g.
`POST /sync`).

## Message Envelope

Every message (request and response) uses this envelope:

```json
{
  "method": "<method_name>",
  "body": { ... }
}
```

The `method` field determines the body schema. Unknown methods
MUST receive an error response.

## Entry Data

Entries are transported as `EntryData` objects:

```json
{
  "entry_id": "d1",
  "source_file": "2026-04-15.txt",
  "timestamp": "14:30",
  "text": "Meeting notes #work",
  "tags": ["work"],
  "metadata": {"status": "done"},
  "attachments": ["d1_photo.jpg"],
  "encrypted_secret": "<base64>",
  "updated_at": "2026-04-15T14:30:00"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| entry_id | string | MUST | Unique entry identifier (e.g. `d1`, `c42`) |
| source_file | string | MUST | Day file name (e.g. `2026-04-15.txt`) |
| timestamp | string | MUST | Entry time `HH:MM` |
| text | string | MUST | Full entry text including inline tags |
| tags | string[] | MAY | Extracted tags |
| metadata | object | MAY | Key-value metadata pairs |
| attachments | string[] | MAY | Attachment filenames |
| encrypted_secret | string\|null | MAY | Base64-encoded encrypted secret (see encryption spec) |
| updated_at | string\|null | MAY | ISO 8601 timestamp of last modification |

## Primary Method: `sync`

The recommended sync method. Single round-trip, dumb client.

### Request

```json
{
  "method": "sync",
  "body": {
    "since": 42,
    "entries": [ ... ],
    "device_id": "d"
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| since | integer | Client's last sync token (0 for first sync) |
| entries | EntryData[] | Local entries to push to server |
| device_id | string | Identifier for the sending device |

### Response

```json
{
  "method": "sync",
  "body": {
    "entries": [ ... ],
    "new_token": 57
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| entries | EntryData[] | Remote entries the client doesn't have yet |
| new_token | integer | Client MUST store this for the next sync |

### Server Behavior

1. Record the current max sync_log ID as `pre_apply_max`
2. Apply each client entry via upsert (see Conflict Resolution)
3. Query sync_log for changes where `id > since AND id <= pre_apply_max`
   (this excludes entries the client just pushed)
4. For each change:
   - `created` or `updated`: load full entry data and include in response
   - `deleted`: include a tombstone entry with `metadata._deleted = "true"`
     and empty text/source_file/timestamp
5. Set `new_token` to the current max sync_log ID (after all applies)
6. Return response

### Client Behavior

1. Collect local entries from sync_log since `last_pushed_log_id`
2. Send `sync` request with `since` = stored token, `entries` = local changes
3. For each entry in response:
   - If `metadata._deleted == "true"`: delete from local index
   - Otherwise: upsert into local store
4. Store `new_token` as the new sync token
5. Update `last_pushed_log_id`

### Sync Token

The sync token is an opaque integer representing a position in the
server's change log. Clients MUST NOT interpret it — just store and
send it back.

A token of `0` means "give me everything."

## Conflict Resolution

### Last-Writer-Wins

When the server receives an entry that already exists (same `entry_id`):

1. Compare `updated_at` timestamps
2. If server's copy is **newer** → skip the client's entry (silent)
3. If client's copy is **newer** or timestamps are missing → accept

This is intentionally simple. No merge, no conflict markers.

### Entry Identity

Entries are identified by `entry_id`. Two entries with the same ID
are the same entry, regardless of content.

### Deletions

Deleted entries are represented as tombstones in the sync response:

```json
{
  "entry_id": "d5",
  "source_file": "",
  "timestamp": "",
  "text": "",
  "metadata": {"_deleted": "true"}
}
```

Clients receiving a tombstone MUST remove the entry from their local
index. The `_deleted` key is reserved and MUST NOT be used as regular
metadata.

## Legacy Methods

The following methods exist for backward compatibility. New
implementations SHOULD use `sync` instead.

### `changes`

Request changes feed since a token.

**Request:** `{"since": 42}`

**Response:**
```json
{
  "changes": [
    {"id": 43, "entry_id": "d5", "action": "created",
     "device_id": "laptop", "created_at": "2026-04-15T14:00:00"}
  ],
  "new_token": 43,
  "has_more": false
}
```

### `entries`

Fetch full entry data by ID list.

**Request:** `{"entry_ids": ["d5", "d6"]}`

**Response:** `{"entries": [ ...EntryData... ]}`

### `push`

Push entries to server.

**Request:** `{"entries": [ ...EntryData... ], "device_id": "laptop"}`

**Response:** `{"accepted": 1, "conflicts": 0, "errors": []}`

## Auxiliary Methods

These methods are independent of the sync flow.

### `search`

Server-side full-text search.

**Request:** `{"query": "#work status:done", "limit": 50}`

**Response:** `{"entries": [ ...EntryData... ], "total": 3}`

### `delete`

Delete an entry by ID.

**Request:** `{"entry_id": "d5", "device_id": "laptop"}`

**Response:** `{"entry_id": "d5", "deleted": true, "error": ""}`

### `update`

Update an entry by ID.

**Request:**
```json
{
  "entry_id": "d5",
  "text": "updated text",
  "tags": ["work"],
  "metadata": {"status": "done"},
  "device_id": "laptop"
}
```

**Response:** `{"entry_id": "d5", "updated": true, "error": ""}`

### `attachment_get`

Download an attachment by filename.

**Request:** `{"filename": "d1_photo.jpg"}`

**Response:** `{"filename": "d1_photo.jpg", "data": "<base64>", "found": true}`

### `attachment_put`

Upload an attachment.

**Request:** `{"filename": "d1_photo.jpg", "data": "<base64>"}`

**Response:** `{"filename": "d1_photo.jpg", "stored": true}`

## Authentication

| Transport | Mechanism |
|-----------|-----------|
| stdin | None required |
| HTTP | API key via `Authorization: Bearer <key>` header, MUST be required |

API keys are managed on the server:

```
kaydet server generate-key --name "macbook"
kaydet server list-keys
kaydet server revoke-key "macbook"
```

## Error Handling

- **Unknown method:** `{"error": "Unknown method: <name>"}`
- **Network failure:** Client retries from last stored token
- **Server unavailable:** Client continues offline
- **Invalid API key:** HTTP 401

## Fixture

See `fixtures/sync-protocol.json` for a machine-readable test scenario.
