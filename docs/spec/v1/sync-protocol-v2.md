# kaydet Sync Protocol — v2 (Binary + Merkle)

|             |                    |
|-------------|--------------------|
| Version     | 2.0                |
| Status      | Draft              |
| Date        | 2026-04-20         |

> **Supersedes:** sync-protocol.md (v1, JSON + sync_log based)  
> **ZEN-DOOM:** No JSON parsers. No magic libraries. Just bytes, integers, and CRC32.

---

## Overview

The sync protocol enables kaydet nodes to exchange entries over any transport. It is built on two primitives:

1. **Merkle Tree** — answers "what is different?" without any shared state
2. **Entry Packet** — answers "how do we transfer it?" (see `entry-packet.md`)

---

## Why Merkle Tree?

Previous v1 protocol used a `sync_log` table and a `since_token` integer. The client asked "give me changes since token 42." This had two problems:

- **Fragile state:** if `sync_log` was corrupted or missing, sync broke. The token was a dependency that could go out of sync.
- **Coupling:** server had to maintain a change log forever, ordered by time.

Merkle tree eliminates both problems. There is no log, no token, no shared state. Each node independently computes a hash of its current storage. Sync is just: compare hashes, find differences, transfer them.

```
sync_log + token  →  "what changed since when?"   (stateful, fragile)
Merkle tree       →  "what is different right now?" (stateless, robust)
```

If the index is corrupted, run `kaydet doctor` — it rebuilds everything from `.txt` files. The Merkle tree is the same: always recomputable from the source of truth (the files).

---

## Design Principles

- **ZEN-OFFLINE:** Nodes work independently. Sync is optional.
- **ZEN-PLAIN-TEXT:** Each node writes its own plain text day files.
- **ZEN-SELF-HEAL:** Conflicts resolved automatically. Tree always recomputable from files.
- **ZEN-DOOM:** If Doom runs on it, kaydet runs on it. No JSON. Just bytes and CRC32.

---

## Merkle Tree Structure

```
ROOT
└── hash(all day hashes)
    ├── 2026-04-18  hash(all entry hashes for that day)
    │   ├── d1  crc32(entry bytes)
    │   └── d2  crc32(entry bytes)
    └── 2026-04-19  hash(all entry hashes for that day)
        ├── d3  crc32(entry bytes)
        └── d4  crc32(entry bytes)
```

### Hash Computation

```
entry_hash  = crc32(NFC(entry_text))
day_hash    = crc32(entry_hash_1 || entry_hash_2 || ...)  sorted by entry_id
root_hash   = crc32(day_hash_1 || day_hash_2 || ...)      sorted by date
```

`||` = concatenation of raw bytes.  
Sorting is mandatory — same entries in different order must produce the same hash.  
All strings NFC-normalized before hashing (see `entry-packet.md`).

### Properties

- Root hash changes if and only if any entry changes.
- "Are we in sync?" = one CRC32 comparison.
- "What changed?" = walk the tree level by level until leaves diverge.
- Tree is always recomputable from `.txt` files. No cache required.

---

## Transport

Transport-agnostic. Same frame format over:

| Transport    | Use case             | Authentication                |
|--------------|----------------------|-------------------------------|
| HTTP(S)      | Remote / managed     | `Authorization: Bearer <key>` |
| stdin/stdout | Local (same machine) | None                          |

---

## Frame Format

Every message is a frame:

```
┌──────────────────────────────────────────┐
│  MAGIC (2)  │  TYPE (1)  │  FLAGS (1)    │
├──────────────────────────────────────────┤
│  PAYLOAD LENGTH (4)                      │
├──────────────────────────────────────────┤
│  PAYLOAD (n bytes)                       │
├──────────────────────────────────────────┤
│  CRC32 (4)                               │
└──────────────────────────────────────────┘
```

All integers **big-endian**.  
All strings **UTF-8, NFC-normalized**, length-prefixed.

### Header (8 bytes)

| Offset | Size | Field          | Value              |
|--------|------|----------------|--------------------|
| 0      | 2    | magic          | `0x4B 0x53` ("KS") |
| 2      | 1    | type           | see Message Types  |
| 3      | 1    | flags          | see Flags          |
| 4      | 4    | payload_length | byte length        |

### Flags

| Bit | Name          | Description                 |
|-----|---------------|-----------------------------|
| 0   | IS_COMPRESSED | payload is gzip-compressed  |
| 1   | IS_ERROR      | this is an error response   |
| 2–7 | reserved      | MUST be 0                   |

### CRC32

CRC32 of all bytes from offset 0 up to (not including) the checksum.  
On failure: discard frame, send ERROR frame.

---

## Message Types

| Type          | Hex  | Direction        | Description                  |
|---------------|------|------------------|------------------------------|
| HELLO         | 0x01 | client → server  | Open session                 |
| TREE_ROOT     | 0x02 | client → server  | Send root hash               |
| TREE_DAY      | 0x03 | both             | Send day-level hashes        |
| TREE_ENTRIES  | 0x04 | both             | Send entry-level hashes      |
| SEND_ENTRIES  | 0x05 | both             | Transfer Entry Packets       |
| DELETE        | 0x06 | client → server  | Delete an entry              |
| ACK           | 0x07 | both             | Acknowledge                  |
| ERROR         | 0xFF | both             | Error                        |

---

## Messages

### HELLO (0x01)

**Payload:**

| Size | Field         | Notes                            |
|------|---------------|----------------------------------|
| 1    | version       | MUST be `0x02`                   |
| 2    | device_id_len |                                  |
| n    | device_id     | UTF-8 NFC                        |

Server responds with ACK or ERROR.

---

### TREE_ROOT (0x02)

Client sends its root hash. Server compares with its own.

**Payload:**

| Size | Field      | Notes                          |
|------|------------|--------------------------------|
| 4    | root_hash  | CRC32 of entire storage        |

**Server response:**

- If hashes match → ACK. Sync complete. No further messages needed.
- If hashes differ → TREE_DAY (server sends its day-level hashes).

This is the fast path: if nothing changed, the entire sync is one round trip.

---

### TREE_DAY (0x03)

Exchange day-level hashes to find which days differ.

**Payload:**

| Size | Field      | Notes                          |
|------|------------|--------------------------------|
| 2    | day_count  | number of days                 |

For each day:

| Size | Field      | Notes                          |
|------|------------|--------------------------------|
| 2    | date_len   | byte length of date string     |
| n    | date       | UTF-8, `"2026-04-19"`          |
| 4    | day_hash   | CRC32 of this day's entries    |

Receiver compares each day hash with its own. Days that differ proceed to TREE_ENTRIES.

---

### TREE_ENTRIES (0x04)

Exchange entry-level hashes for a specific day.

**Payload:**

| Size | Field      | Notes                          |
|------|------------|--------------------------------|
| 2    | date_len   |                                |
| n    | date       | UTF-8, `"2026-04-19"`          |
| 2    | entry_count|                                |

For each entry:

| Size | Field      | Notes                          |
|------|------------|--------------------------------|
| 4    | id_len     |                                |
| n    | entry_id   | UTF-8 NFC                      |
| 4    | entry_hash | CRC32 of entry content         |

Receiver compares each entry hash. Entries that differ → request via SEND_ENTRIES.

---

### SEND_ENTRIES (0x05)

Transfer actual entry content as Entry Packets.

**Payload:**

| Size | Field        | Notes                          |
|------|--------------|--------------------------------|
| 4    | packet_count |                                |

Immediately after this frame: `packet_count` Entry Packets (see `entry-packet.md`), sent sequentially.

---

### DELETE (0x06)

**Payload:**

| Size | Field      | Notes                          |
|------|------------|--------------------------------|
| 4    | id_len     |                                |
| n    | entry_id   | UTF-8 NFC                      |
| 8    | deleted_at | u64, Unix timestamp (seconds)  |

Server keeps tombstone (entry_id + deleted_at), discards content.  
Server responds with ACK.

---

### ACK (0x07)

No payload. payload_length = 0.

---

### ERROR (0xFF)

| Size | Field   | Notes                    |
|------|---------|--------------------------|
| 1    | code    | see error codes          |
| 2    | msg_len |                          |
| n    | message | UTF-8 NFC, human-readable|

**Error codes:**

| Code | Name             | Description                      |
|------|------------------|----------------------------------|
| 0x01 | VERSION_MISMATCH | Unsupported protocol version     |
| 0x02 | AUTH_FAILED      | Invalid or missing API key       |
| 0x03 | BAD_FRAME        | CRC32 mismatch or malformed frame|
| 0x04 | BAD_PACKET       | Entry Packet CRC32 failed        |
| 0x05 | UNKNOWN_TYPE     | Unknown message type             |
| 0x06 | ENTRY_NOT_FOUND  | DELETE on unknown entry_id       |
| 0xFF | INTERNAL         | Server-side error                |

---

## Full Sync Flow

```
Client                              Server
  │                                    │
  │  HELLO                             │
  │──────────────────────────────────▶ │
  │                               ACK  │
  │ ◀────────────────────────────────  │
  │                                    │
  │  TREE_ROOT (hash=abc123)           │   "are we in sync?"
  │──────────────────────────────────▶ │
  │                                    │
  │         [hashes differ]            │
  │                                    │
  │                  TREE_DAY          │   "which days differ?"
  │ ◀────────────────────────────────  │
  │                                    │
  │  TREE_ENTRIES (date=2026-04-19)    │   "which entries differ?"
  │──────────────────────────────────▶ │
  │                                    │
  │                TREE_ENTRIES        │   server sends its entries for that day
  │ ◀────────────────────────────────  │
  │                                    │
  │  SEND_ENTRIES (d5, d7)             │   client sends what server is missing
  │──────────────────────────────────▶ │
  │                                    │
  │                SEND_ENTRIES (d3)   │   server sends what client is missing
  │ ◀────────────────────────────────  │
  │                                    │
  │                               ACK  │
  │ ◀────────────────────────────────  │
  │                                    │
  ✓ synced
```

### First Sync (empty client)

Client root hash = `0x00000000`. Server sees this, skips tree negotiation, sends everything directly via SEND_ENTRIES.

---

## Conflict Resolution

### Last-Writer-Wins

When a node receives an entry that already exists:

1. Compare `updated_at` from incoming Entry Packet vs. local copy
2. Server copy newer → discard incoming
3. Incoming newer or `updated_at` missing → accept, overwrite

Tie-breaker (same `updated_at`): lexicographically larger `device_id` wins. Deterministic, no coin flip.

---

## Search

Search is **not part of the sync protocol**. Separate HTTP endpoint:

```
GET /v2/search?q=<query>&limit=<n>
Authorization: Bearer <key>
```

Response: JSON list of matching entries. Full-text search is a server feature, not a sync concern.

---

## Minimal Parser (pseudocode)

```
fn parse_frame(bytes):
    assert bytes[0..2] == [0x4B, 0x53]   # KS
    msg_type    = bytes[2]
    flags       = bytes[3]
    payload_len = u32_be(bytes, 4)

    payload = bytes[8 .. 8 + payload_len]
    if flags & 0x01:
        payload = gzip_decompress(payload)

    expected = crc32(bytes[0 .. 8 + payload_len])
    actual   = u32_be(bytes, 8 + payload_len)
    assert expected == actual

    return (msg_type, flags, payload)
```

15 lines. Runs on anything that can read bytes.

---

## What Was Removed (vs v1)

| v1 concept      | Status  | Reason                                        |
|-----------------|---------|-----------------------------------------------|
| `sync_log`      | Removed | Merkle tree needs no change log               |
| `since_token`   | Removed | Stateless hash comparison replaces it         |
| `changes`       | Removed | Superseded by tree negotiation                |
| `entries`       | Removed | Superseded by SEND_ENTRIES                    |
| `push`          | Removed | Superseded by SEND_ENTRIES                    |
| `attachment_get`| Removed | Attachments travel inside Entry Packets       |
| `attachment_put`| Removed | Attachments travel inside Entry Packets       |
| JSON envelope   | Removed | ZEN-DOOM — bytes only                         |
| search in sync  | Removed | Search is a separate HTTP concern             |
