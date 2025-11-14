# Sync at Home Protocol

## Overview

Sync at Home enables mobile devices to synchronize diary files with a desktop computer over LAN, without cloud services or encryption. Privacy is protected by physical boundaries: sync happens only when the device connects to the home Wi-Fi network.

## Design Principles

- **[ZEN-PLAIN-TEXT]:** All diary files remain human-readable `.txt` files
- **[ZEN-OFFLINE]:** No internet required; sync works over local network only
- **[ZEN-READABLE]:** MD5 fingerprints enable efficient delta sync
- **[ZEN-STANDALONE]:** Server uses Python's built-in `http.server`; no external dependencies
- **[ZEN-SELF-HEAL]:** ID conflicts are automatically normalized after merge

## Security Model

### Pairing

- Mobile app generates random `device_secret` and derives 6-digit pairing code
- **Pairing code expires after 10 minutes** (prevents brute force)
- User enters code on desktop: `kaydet sync approve <code>`
- Desktop adds device to `sync_whitelist.csv`
- Code is deleted after use or expiry

### Authentication

All sync requests include three headers:

```
X-Kaydet-Device: dev_01
X-Kaydet-Timestamp: 2025-11-14T10:30:00Z
X-Kaydet-Signature: <hmac>
```

**Signature calculation:**
```
HMAC_SHA256(timestamp + body, device_secret)
```

**Replay protection:**
- Server rejects requests older than 5 minutes
- No database needed; timestamp validation is sufficient

### Session Management

- Session ID: UUID v4 (cryptographically random)
- Timeout: 30 minutes idle, 2 hours maximum
- One active session per device (new session cancels old)
- Deleted on `/complete` or timeout

## Architecture

### Roles

**Client (mobile):**
- Works offline; detects home Wi-Fi
- Sends file hashes; uploads dirty files
- Receives merged content

**Server (desktop):**
- Runs `kaydet sync-server`
- Compares hashes; merges files
- Returns final versions

### High-Level Flow

```
1. Mobile detects home SSID
2. Mobile opens session → Server returns session_id
3. Mobile sends fingerprints → Server compares with local files
4. Server identifies dirty files → Mobile uploads them
5. Server merges content → Mobile downloads results
6. Mobile closes session
```

## Protocol Specification

### Health Check

```
GET /health
Response: { "version": "0.33.0", "status": "ready" }
```

### Pairing Endpoints

**`POST /pair/request`**
- Device requests pairing
- Returns `pair_id`

**`GET /pair/status?pair_id=<id>`**
- Device polls for approval
- Returns approval status

**Example:**

```bash
# Mobile requests pairing
POST /pair/request
Body: { "code": "472813", "device_name": "iPhone", "device_secret": "..." }
Response: { "pair_id": "abc123" }

# Mobile polls for approval
GET /pair/status?pair_id=abc123
Response: { "status": "approved", "device_id": "dev_01" }

# Desktop approves
$ kaydet sync approve 472813
# Writes to sync_whitelist.csv: dev_01,"iPhone","<secret>"
```

### Sync Endpoints

All sync endpoints require `X-Kaydet-Device`, `X-Kaydet-Timestamp`, and `X-Kaydet-Signature` headers.

**`POST /sync/start`**
- Opens session with file fingerprints
- Returns `session_id` and dirty/clean lists

**`POST /sync/{session}/clear`**
- Upload dirty files
- Returns merged content

**`POST /sync/{session}/complete`**
- Send final fingerprints to verify consistency
- Returns sync status (complete or dirty)
- Closes session if complete

**Signature notes:**
- Timestamp format: ISO 8601 UTC (e.g., `2025-11-14T10:30:00Z`)
- Server rejects requests with timestamp > 5 minutes old
- Body must be exact JSON string used in signature calculation

## Sync Algorithm

### 1. Start Session + Fingerprint Exchange

**Client sends:**
```json
POST /sync/start
{
  "app_version": "1.0.0",
  "fingerprints": {
    "2025-01-01.txt": "d8e8fca2dc0f896fd7cb4cb0031ba249",
    "2025-01-02.txt": "5d41402abc4b2a76b9719d911017c592"
  }
}
```

**Server responds:**
```json
{
  "session_id": "sess_9",
  "dirty": [
    { "name": "2025-01-01.txt", "state": "both" },
    { "name": "2025-01-03.txt", "state": "download" }
  ],
  "clean": ["2025-01-02.txt"]
}
```

**State values:**
- `upload`: Client has newer content
- `download`: Server has newer content
- `both`: Both sides modified (merge needed)

### 2. Clear (Upload & Merge)

**Client sends dirty files:**
```json
{
  "entries": [
    {
      "name": "2025-01-01.txt",
      "hash": "d8e8fca2dc0f896fd7cb4cb0031ba249",
      "content": "14:25 [42]: Meeting notes | #work\n"
    },
    {
      "name": "2025-01-03.txt",
      "hash": null,
      "content": ""
    }
  ]
}
```

**Server merges and responds:**
```json
{
  "results": [
    {
      "name": "2025-01-01.txt",
      "hash": "a1b2c3d4e5f6...",
      "content": "09:00 [41]: Desktop entry | #work\n14:25 [42]: Meeting notes | #work\n"
    },
    {
      "name": "2025-01-03.txt",
      "hash": "f7e6d5c4b3a2...",
      "content": "10:00 [43]: Server-only entry | #personal\n"
    }
  ]
}
```

**Notes:**
- `hash: null` means "send me the file"
- `content: ""` means "I don't have this file"
- Server always returns new hash + merged content

### 3. Complete (Verify & Close)

**Client sends final fingerprints:**
```json
POST /sync/{session}/complete
{
  "fingerprints": {
    "2025-01-01.txt": "a1b2c3d4e5f6...",
    "2025-01-02.txt": "5d41402abc4b2a76b9719d911017c592",
    "2025-01-03.txt": "f7e6d5c4b3a2..."
  }
}
```

**Server responds (if in sync):**
```json
{ "status": "complete" }
```

**Server responds (if new changes detected):**
```json
{
  "status": "dirty",
  "dirty": [
    { "name": "2025-01-01.txt", "state": "upload" }
  ]
}
```

**Client retry logic:**
- Max 3 retries
- If dirty: go back to step 2 (clear)
- If max retries exceeded: partial sync, close session
- Remaining dirty files sync in next session

**Why max retries?**
- Prevents infinite loop if user continuously writes
- Real-time sync will catch remaining changes
- Typical sync: 2-5 seconds, 3 loops = max 15 seconds

## Conflict Resolution

### Append-Both Strategy

When both client and server modified the same file:

1. Server appends client entries to its own entries
2. Server sorts by timestamp
3. Server normalizes entry IDs (via `sync_modified_diary_files`)
4. Client receives merged content and overwrites local file

**Example:**

```
Server: 09:00 [41]: Desktop work
Client: 14:25 [41]: Mobile note  ← ID conflict!

Merged: 09:00 [41]: Desktop work
        14:25 [42]: Mobile note  ← ID renormalized
```

**Why append-only works:**
- Users rarely modify old entries
- New entries always append to end of file
- ID conflicts are automatically fixed by normalization
- Three-way merge is overkill for MVP

## Pairing Flow

### Desktop Setup

```bash
# Start server
$ kaydet sync-server
Server listening on http://192.168.1.100:8080
```

### Mobile Setup

1. App prompts for home Wi-Fi SSID: `HomeWiFi`
2. App prompts for server address: `192.168.1.100:8080` (or auto-discover via mDNS)
3. App generates `device_secret` and 6-digit code: `472813`
4. App shows code to user

### Pairing

```
Mobile                          Desktop
  |                               |
  | POST /pair/request            |
  | { code: "472813", ... }       |
  |------------------------------>|
  | { pair_id: "abc123" }         |
  |<------------------------------|
  |                               |
  | GET /pair/status?pair_id=...  |
  |------------------------------>|
  | { status: "pending" }         |
  |<------------------------------|
  |                               |
  |                    User runs: kaydet sync approve 472813
  |                               |
  | GET /pair/status?pair_id=...  |
  |------------------------------>|
  | { status: "approved",         |
  |   device_id: "dev_01" }       |
  |<------------------------------|
  |                               |
  ✓ Paired!
```

## Sync Flow

### Preconditions

- Device is paired
- Device connected to home Wi-Fi
- Desktop sync server is running

### Flow

```
Mobile                          Desktop
  |                               |
  | POST /sync/start              |
  | Headers: device_id, timestamp, signature
  | Body: { fingerprints: {...} } |
  |------------------------------>|
  | { session_id: "sess_9",       |
  |   dirty: [...], clean: [...] }|
  |<------------------------------|
  |                               |
  | POST /sync/sess_9/clear       |
  | { entries: [{ name, hash, content }] }
  |------------------------------>|
  | { results: [{ name, hash, content }] }
  |<------------------------------|
  |                               |
  | (writes merged files locally) |
  |                               |
  | POST /sync/sess_9/complete    |
  | Body: { fingerprints: {...} } |
  |------------------------------>|
  | { status: "complete" }        |
  | (or { status: "dirty", ... }) |
  |<------------------------------|
  |                               |
  | If dirty: loop to /clear      |
  | If complete: done!            |
  |                               |
  ✓ Synced!
```

### Error Handling

- Network failure during upload → Client retries with same session_id
- Session timeout → Client starts new session
- HMAC validation failure → Client re-pairs
- Timestamp too old → Client syncs clock and retries

## Real-time Sync

When mobile app detects sync server on home network:

**Entry add/edit triggers sync:**
- User saves entry → Writes to local file immediately
- If sync not already running → Starts sync flow
- If sync already running → Skipped (changes included in next sync)

**Benefits:**
- No blocking: User can continue writing while sync happens
- Batching: Multiple rapid entries sync together efficiently
- No special endpoint: Uses standard sync flow
- Falls back to periodic sync if real-time fails

**Example flow:**
```
T0: User opens app → Background sync starts
    - /start sends fingerprints

T1: User writes entry 1 → Saved locally
    - Sync already running → Skip trigger

T2: User writes entry 2 → Saved locally
    - Sync already running → Skip trigger

T3: Sync /clear completes → Downloads merged files

T4: Sync /complete sends new fingerprints
    - Server detects entry 1 & 2 → Returns dirty
    - Client loops: /clear again → /complete again
    - Server sees in sync → Returns complete

T5: User writes entry 3 → Triggers new sync cycle
```

**Race condition handled:**
- Complete always re-validates with fresh fingerprints
- Max 3 retry loops prevent infinite sync
- Worst case: partial sync, next cycle catches remainder

## Implementation Notes

### Whitelist File

**Location:** `~/.local/share/kaydet/sync_whitelist.csv`

**Format:** CSV without header
```
dev_01,"Mirat iPhone","<device_secret>"
dev_02,"Mirat iPad","<device_secret>"
```

**Management:**
- `kaydet sync approve <code>` → Adds entry
- `kaydet sync revoke <device_id>` → Removes entry (planned)
- Server reloads file periodically

### Network Discovery

**mDNS/Bonjour (future):**
- Server advertises: `_kaydet._tcp.local`
- Mobile auto-discovers without manual IP entry

**Manual entry (current):**
- User enters hostname or IP: `kaydet.local` or `192.168.1.100`
- Port defaults to 8080

### Configuration

App stores in `sync_state.json`:
```json
{
  "sync_home_ssid": "HomeWiFi",
  "sync_host": "192.168.1.100:8080",
  "device_id": "dev_01",
  "device_secret": "<secret>",
  "last_success_at": "2025-11-14T10:30:00Z",
  "fingerprints": {
    "2025-01-01.txt": "md5..."
  }
}
```

### Roadmap

**Phase 1 - MVP:**
1. Server skeleton: `src/kaydet/sync_server.py` using `http.server`
2. Pairing endpoints + whitelist management
3. Sync endpoints + HMAC validation
4. Append-both merge strategy
5. Mobile app (iOS/Android)

**Phase 2 - Polish:**
1. mDNS auto-discovery
2. Resume interrupted sessions
3. Desktop CLI: `kaydet sync pull` (force sync)
4. Background sync on iOS (App Refresh) and Android (WorkManager)

**Phase 3 - Advanced:**
1. Three-way merge for edited entries
2. Conflict UI (let user choose)
3. Multi-device broadcast sync

---

This protocol balances simplicity with security, enabling offline-first sync without sacrificing kaydet's plain-text philosophy.
