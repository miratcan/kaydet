# kaydet Entry Packet Format — v1

> **Status:** Draft  
> **Philosophy:** So minimal that a fridge can parse it. If Doom runs on it, kaydet runs on it.  
> No JSON parsers. No magic libraries. Just bytes.

---

## Overview

An **entry packet** is a self-contained binary blob carrying one entry and all its attachments. It is the atomic unit of transfer between kaydet peers. Either the whole packet arrives or nothing does.

```
┌─────────────────────────────────────────────┐
│  MAGIC (4)  │  VERSION (1)  │  FLAGS (1)    │
├─────────────────────────────────────────────┤
│  ENTRY BLOCK                                │
│    id_len (4) │ id (n)                      │
│    ts_len (2) │ timestamp (n)               │
│    text_len (4) │ text (n)                  │
├─────────────────────────────────────────────┤
│  ATTACHMENT COUNT (2)                       │
├─────────────────────────────────────────────┤
│  ATTACHMENT BLOCK × count                   │
│    name_len (2) │ name (n)                  │
│    data_len (8) │ data (n)                  │
├─────────────────────────────────────────────┤
│  CHECKSUM (4)                               │
└─────────────────────────────────────────────┘
```

All multi-byte integers are **big-endian**.  
All strings are **UTF-8**, no null terminator.  
All strings MUST be **NFC-normalized** (Unicode Normalization Form C) before encoding.
A receiver SHOULD normalize on read as well — treat denormalized input as an error only if CRC32 fails.

---

## Byte Layout

### Header (6 bytes)

| Offset | Size | Field   | Value                        |
|--------|------|---------|------------------------------|
| 0      | 4    | magic   | `0x4B 0x59 0x44 0x54` ("KYDT") |
| 4      | 1    | version | `0x01`                       |
| 5      | 1    | flags   | see Flags                    |

### Flags (1 byte)

| Bit | Name            | Description                              |
|-----|-----------------|------------------------------------------|
| 0   | HAS_ATTACHMENTS | 1 if attachment count > 0                |
| 1   | IS_ENCRYPTED    | 1 if text is an encrypted payload (--secret) |
| 2   | IS_COMPRESSED   | 1 if everything after header is gzipped  |
| 3–7 | reserved        | MUST be 0                                |

If `IS_COMPRESSED` is set, bytes from offset 6 onward are a gzip stream.  
Decompress first, then parse the rest. If your platform has no gzip — skip compression, set bit 2 to 0. The format works either way.

### Entry Block

| Size   | Field      | Notes                        |
|--------|------------|------------------------------|
| 4      | id_len     | byte length of entry id      |
| id_len | id         | UTF-8, e.g. `"01HV3K..."`   |
| 2      | ts_len     | byte length of timestamp     |
| ts_len | timestamp  | UTF-8, `"HH:MM"` or ISO 8601 |
| 4      | text_len   | byte length of entry text    |
| text_len | text     | UTF-8, full raw entry text   |

### Attachment Section

| Size  | Field            | Notes                     |
|-------|------------------|---------------------------|
| 2     | attachment_count | 0 if HAS_ATTACHMENTS=0    |

Then for each attachment:

| Size      | Field     | Notes                          |
|-----------|-----------|--------------------------------|
| 2         | name_len  | byte length of filename        |
| name_len  | name      | UTF-8, e.g. `"abc123_foto.jpg"` |
| 8         | data_len  | byte length of raw file data   |
| data_len  | data      | raw bytes, no encoding         |

### Checksum (4 bytes)

CRC32 of all bytes from offset 0 up to (not including) the checksum itself.  
A receiver MUST verify this before writing anything to disk.  
If checksum fails: discard the entire packet. Do not write partial data.

---

## Chunked Transfer

Packets are transferred in chunks over HTTP. This enables resume on large attachments (video etc.) without restarting from zero.

### Upload

```
POST /v1/packets/{entry_id}
Content-Type: application/octet-stream
X-Kaydet-Chunk-Offset: <byte offset>
X-Kaydet-Total-Size: <total packet size in bytes>
X-Kaydet-Chunk-Size: <this chunk size in bytes>

<chunk bytes>
```

Response while uploading:
```
202 Accepted
{ "received": <bytes received so far> }
```

Response when complete (final chunk received + checksum verified):
```
200 OK
{ "entry_id": "...", "status": "complete" }
```

Checksum is verified only after the final chunk. If it fails, the server discards all chunks and returns:
```
422 Unprocessable Entity
{ "error": "checksum_mismatch" }
```
Client MUST restart from offset 0.

### Resume

If transfer is interrupted:

```
GET /v1/packets/{entry_id}/status
```

Response:
```json
{ "entry_id": "...", "received": 1048576, "total": 5242880, "status": "incomplete" }
```

Client resumes by sending chunks starting at `received` offset.

### Chunk Size

Recommended: **256 KB**.  
Minimum: **4 KB**.  
Maximum: **4 MB**.  
Receiver MUST accept any size within this range.

---

## Minimal Parser (pseudocode)

This is all a receiver needs. No JSON. No gzip required. Just byte reads.

```
fn parse_packet(bytes):
    assert bytes[0..4] == [0x4B, 0x59, 0x44, 0x54]  # KYDT
    assert bytes[4] == 0x01                            # version
    flags = bytes[5]

    if flags & 0x04:                                   # IS_COMPRESSED
        bytes = gzip_decompress(bytes[6:])
        offset = 0
    else:
        offset = 6

    # entry block
    id_len   = u32_be(bytes, offset);  offset += 4
    id       = utf8(bytes, offset, id_len);  offset += id_len
    ts_len   = u16_be(bytes, offset);  offset += 2
    ts       = utf8(bytes, offset, ts_len);  offset += ts_len
    text_len = u32_be(bytes, offset);  offset += 4
    text     = utf8(bytes, offset, text_len);  offset += text_len

    # attachments
    count = u16_be(bytes, offset);  offset += 2
    attachments = []
    repeat count times:
        name_len = u16_be(bytes, offset);  offset += 2
        name     = utf8(bytes, offset, name_len);  offset += name_len
        data_len = u64_be(bytes, offset);  offset += 8
        data     = bytes[offset .. offset+data_len];  offset += data_len
        attachments.append((name, data))

    # checksum
    expected = crc32(bytes[0 .. offset])
    actual   = u32_be(bytes, offset)
    assert expected == actual

    return Entry(id, ts, text, attachments)
```

Total parser complexity: ~30 lines. Runs on anything that can read bytes.

---

## Wire Example (no attachments, no compression)

```
4B 59 44 54   # magic: KYDT
01            # version: 1
00            # flags: none

00 00 00 24   # id_len: 36
30 31 48 56 33 4B ...  # id: "01HV3K..." (36 bytes)

00 05         # ts_len: 5
31 34 3A 32 35  # timestamp: "14:25"

00 00 00 1A   # text_len: 26
79 6F 6C 64 61 20 6E 6F 74 20 61 6C 64 C4 B1 6D 20 23 6D 69 72 61 74  # "yolda not aldım #mirat"

00 00         # attachment_count: 0

XX XX XX XX   # CRC32
```

---

## Validation Rules

- All string fields MUST be NFC-normalized UTF-8. Senders MUST normalize before encoding. Receivers SHOULD normalize after decoding before storing.
- Magic MUST be `KYDT` (4 bytes). Reject anything else silently.
- Version MUST be `0x01`. Unknown versions: respond `400 Bad Request`, do not parse.
- Reserved flag bits MUST be 0. If nonzero: reject with `400`.
- CRC32 MUST match. If not: reject with `422`, discard all chunks.
- `data_len` for attachments is 8 bytes (u64) — supports files up to 16 EB. Yes, really.
- A receiver with no gzip support MUST still handle uncompressed packets (IS_COMPRESSED=0).

---

## Why not JSON? Why not msgpack? Why not protobuf?

JSON: requires a parser. A parser requires memory, a string heap, recursion. Not fridge-safe.  
msgpack: better, but still a library. Schema implicit.  
protobuf: generated code, reflection, a runtime. Absolutely not.  

This format requires: integer reads, byte copies, CRC32.  
CRC32 is 20 lines of C. The rest is memcpy.  
That's it. That's the whole parser.

**[ZEN-DOOM]:** If Doom runs on it, kaydet runs on it.
