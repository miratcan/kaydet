# Kaydet Sync Protocol

> **Status:** Draft. Not implemented yet.

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

## Concepts

### Entry

The atomic unit of sync. An entry has:

- `id` — numeric, unique per device (renormalized on sync)
- `date` — the day file it belongs to (e.g. `2026-04-13`)
- `timestamp` — `HH:MM` format
- `text` — the entry content, including inline tags
- `metadata` — key:value pairs
- `attachments` — list of filenames
- `secret` — optional encrypted payload (see Secrets below)

### Sync Token

An opaque value representing a point in the server's change history.
Clients store their last sync token and present it to get only the
changes that happened since.

### Changes Feed

The server maintains an ordered log of all changes (created, updated,
deleted). Clients request changes since their last token.

## Secrets

Entries can carry an optional encrypted secret:

```
kaydet "evimdeki modemin sifresi" --secret "SarinmsakliKofte1999"
```

**Properties:**

- The `text` is plain text, stored normally in `.txt` files
- The `secret` is encrypted with AES-256-GCM (scrypt KDF from a
  user-chosen password) and stored only in SQLite — never in `.txt` files
- Secrets do not appear in `--list`, `search`, or sync log content
- Secrets are only accessible via `kaydet get <id>`
- The server stores secrets as encrypted blobs — it cannot read them
- Each device must know the encryption password to decrypt secrets

**What this is not:** a password manager. It is a simple way to attach
sensitive information to a diary entry without it being grep-able in
plain text files.

**Setup:**
```
kaydet sync setup
Enter secret encryption password: ********
```

The password is stored locally in the client config. The server does
not receive or store the password.

## Authentication

- **Local (stdin transport):** No authentication required
- **Remote (HTTP transport):** API key in `Authorization: Bearer <key>` header

Keys are named and managed on the server:

```
kaydet server generate-key --name "macbook-air-cli"
kaydet server generate-key --name "pwa-android"
kaydet server revoke-key "pwa-android"
```

## Transports

The protocol is transport-agnostic. The same JSON messages work over:

- **stdin/stdout** — for local use (no network, no auth)
- **HTTP(S)** — for remote use

All request/response bodies are JSON.

## Endpoints

### `GET /changes`

Get entries that changed since a sync token.

**Request:**
```
GET /changes?since=42
```

`since` is the client's last sync token. Omit for first sync (gets
everything).

**Response:**
```json
{
  "token": 67,
  "changes": [
    { "entry_id": 50, "action": "created" },
    { "entry_id": 51, "action": "created" },
    { "entry_id": 33, "action": "updated" },
    { "entry_id": 28, "action": "deleted" }
  ]
}
```

### `GET /entries`

Fetch full entry data by IDs.

**Request:**
```
GET /entries?ids=50,51,33
```

**Response:**
```json
{
  "entries": [
    {
      "id": 50,
      "date": "2026-04-13",
      "timestamp": "14:30",
      "text": "Meeting notes #work",
      "metadata": { "status": "done" },
      "attachments": [],
      "secret": null
    },
    {
      "id": 51,
      "date": "2026-04-13",
      "timestamp": "15:00",
      "text": "Photo from park #personal",
      "metadata": {},
      "attachments": ["51_photo.jpg"],
      "secret": null
    },
    {
      "id": 33,
      "date": "2026-04-12",
      "timestamp": "09:00",
      "text": "Modem password",
      "metadata": {},
      "attachments": [],
      "secret": "base64-encrypted-blob..."
    }
  ]
}
```

The `secret` field is either `null` (no secret) or a base64-encoded
AES-256-GCM ciphertext. The server stores and relays it as-is — it
cannot decrypt it.

### `POST /entries`

Push new or updated entries to the server.

**Request:**
```json
{
  "entries": [
    {
      "date": "2026-04-13",
      "timestamp": "16:00",
      "text": "New entry from mobile #daily",
      "metadata": {},
      "attachments": [],
      "secret": null
    }
  ]
}
```

**Response:**
```json
{
  "token": 69,
  "entries": [
    { "id": 60, "status": "created" }
  ]
}
```

### `POST /attachments`

Upload an attachment file.

**Request:**
```
POST /attachments
Content-Type: multipart/form-data

file: <binary>
entry_id: 51
```

**Response:**
```json
{
  "attachment": "51_photo.jpg"
}
```

### `GET /attachments/{filename}`

Download an attachment file.

**Response:** Binary file content.

## Sync Flow

```
Client                              Server
  |                                   |
  |  GET /changes?since=42            |
  |---------------------------------->|
  |  { token:67, changes:[...] }      |
  |<----------------------------------|
  |                                   |
  |  GET /entries?ids=50,51,33        |
  |---------------------------------->|
  |  [ entries... ]                   |
  |<----------------------------------|
  |                                   |
  |  GET /attachments/51_photo.jpg    |
  |---------------------------------->|
  |  <binary>                         |
  |<----------------------------------|
  |                                   |
  |  (write to local files)           |
  |                                   |
  |  POST /entries (local changes)    |
  |---------------------------------->|
  |  { token:69 }                     |
  |<----------------------------------|
  |                                   |
  |  POST /attachments (if any)       |
  |---------------------------------->|
  |  { attachment: "60_doc.pdf" }     |
  |<----------------------------------|
  |                                   |
  ✓ Done. Client stores token 69.
```

### First Sync

On first sync the client has no token. It sends `GET /changes` without
`since` — the server returns all entries. The client writes them locally
and stores the returned token.

### Subsequent Syncs

Client sends its stored token. Server returns only what changed since
then. Client pulls new entries, pushes its own, stores the new token.

## Conflict Resolution

### Last-Writer-Wins

When the same entry was modified on both sides:

1. Compare modification timestamps
2. The newer one wins
3. The losing version is discarded

### Deletions

A deletion is a change with a timestamp. If a deletion is newer than
the other side's modification, the entry stays deleted. If the
modification is newer, the entry survives.

### Same Timestamp

When timestamps are identical, the device ID is used as a tiebreaker
(lexicographic ordering). This ensures deterministic resolution.

### ID Renormalization

Entry IDs are local to each device. When entries arrive from another
device, they are assigned new local IDs. The server maintains its own
ID space. Each device renormalizes on write.

## Error Handling

- **Network failure during sync:** Client retries from last successful
  token. Already-pushed entries are idempotent.
- **Server unavailable:** Client continues working offline. Sync resumes
  when server is reachable.
- **Invalid API key:** Server returns 401. Client should re-register.
