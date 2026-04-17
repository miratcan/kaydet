# Kaydet File Transfer Specification

|             |                    |
|-------------|--------------------|
| Version     | 1.0                |
| Status      | Draft              |
| Date        | 2026-04-15         |

## Overview

Kaydet entries MAY have file attachments (photos, videos, documents)
and encrypted secrets. This spec defines how files are transferred
between nodes reliably, supporting large files and resumable transfers.

## Scope

This spec covers:
- Attachment upload (chunked, resumable)
- Attachment download (ranged, resumable)
- Integrity verification (SHA-256)

Secret files (`secrets/*.enc`) are small (< 1KB typically) and
continue to use the existing base64 transport in `EntryData`.

## Storage Layout

```
storage/
  attachments/
    d1_photo.jpg
    d1_video.mp4
    d5_receipt.pdf
  secrets/
    d1.enc
```

Attachment filenames follow the `{entry_id}_{original_name}` convention
defined in the file format spec.

## Transport Modes

| Transport | Small files (< 1MB) | Large files (>= 1MB) |
|-----------|--------------------|-----------------------|
| HTTP      | Single request     | Chunked upload/download |
| stdin     | Base64 in JSON     | Base64 in JSON (no chunking) |
| Embed     | Direct function call | Direct function call |

Stdin transport has no chunking — files are transferred as base64
in the existing `attachment_get`/`attachment_put` protocol messages.
This is acceptable because stdin is local-only (no network, no
interruption risk).

**Mobile clients (React Native) MUST use the HTTP binary endpoints.**
Files are stored locally using the platform filesystem (e.g.
`expo-file-system`) and downloaded via `GET /files/{filename}`.
Base64 transport (`attachment_get`/`attachment_put`) is NOT used by
mobile clients — it is inefficient and unreliable for large files on
native platforms.

## SHA-256 Verification

The `sha256` field in `upload-start` is OPTIONAL. If omitted or empty,
the server skips hash verification and accepts the upload as-is.
Clients SHOULD provide the hash when they can compute it for integrity
guarantees. The server always returns the actual hash in `upload-finish`
via the `sha256_match` field.

## Upload Protocol (HTTP)

### Step 1: Initiate Upload

```
POST /files/upload-start

{
  "filename": "d1_video.mp4",
  "size": 250000000,
  "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
}
```

| Field    | Type    | Required | Description |
|----------|---------|----------|-------------|
| filename | string  | MUST     | Target filename in `{entry_id}_{name}` format |
| size     | integer | MUST     | Total file size in bytes |
| sha256   | string  | MUST     | Hex-encoded SHA-256 of the complete file |

**Response:**
```json
{
  "upload_id": "a1b2c3d4",
  "chunk_size": 1048576,
  "existing_offset": 0
}
```

| Field           | Type    | Description |
|-----------------|---------|-------------|
| upload_id       | string  | Opaque identifier for this upload session |
| chunk_size      | integer | Recommended chunk size in bytes (server decides) |
| existing_offset | integer | Bytes already received (for resume). 0 = fresh start |

If the file already exists and the SHA-256 matches, the server MAY
return immediately with `{"upload_id": null, "already_exists": true}`.

If a partial upload exists for the same filename, the server MUST
return the `existing_offset` so the client can resume.

### Step 2: Upload Chunks

```
POST /files/upload-chunk

Content-Type: application/octet-stream
X-Upload-Id: a1b2c3d4
X-Chunk-Offset: 0

[raw binary chunk data]
```

| Header         | Type    | Required | Description |
|----------------|---------|----------|-------------|
| X-Upload-Id    | string  | MUST     | From upload-start response |
| X-Chunk-Offset | integer | MUST     | Byte offset of this chunk |

The body is raw bytes (NOT base64, NOT JSON).

**Response:**
```json
{
  "received_bytes": 1048576,
  "total_received": 1048576
}
```

Client MUST send chunks sequentially (offset 0, then chunk_size,
then 2*chunk_size, etc.). Server MUST reject out-of-order chunks.

If a chunk fails (network error), client retries the same offset.

### Step 3: Finalize Upload

```
POST /files/upload-finish

{
  "upload_id": "a1b2c3d4"
}
```

**Server behavior:**
1. Concatenate all chunks into final file
2. Compute SHA-256 of the result
3. Compare with the hash from upload-start
4. If match: move to `attachments/`, return success
5. If mismatch: delete chunks, return error

**Response (success):**
```json
{
  "filename": "d1_video.mp4",
  "ok": true,
  "sha256_match": true,
  "size": 250000000
}
```

**Response (integrity failure):**
```json
{
  "filename": "d1_video.mp4",
  "ok": false,
  "sha256_match": false,
  "error": "SHA-256 mismatch: expected e3b0c4... got 5d41402..."
}
```

### Upload Cleanup

Incomplete uploads (started but not finished) SHOULD be cleaned up
by the server after a configurable timeout (default: 24 hours).

## Download Protocol (HTTP)

### Small Files

```
GET /files/d1_photo.jpg
```

**Response:** Raw binary with appropriate `Content-Type` and
`Content-Length` headers.

### Large Files (Range Requests)

Standard HTTP range requests:

```
GET /files/d1_video.mp4
Range: bytes=0-1048575
```

**Response:**
```
HTTP/1.1 206 Partial Content
Content-Range: bytes 0-1048575/250000000
Content-Length: 1048576

[raw binary data]
```

Server MUST support `Range` header for all files. Client MAY request
the full file without a Range header.

### Integrity Verification

The download response MUST include a `X-SHA256` header:

```
X-SHA256: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
```

Client SHOULD verify the hash after download completes. If mismatch,
client SHOULD discard the file and retry.

## Sync Integration

When syncing entries with attachments:

1. `sync` method returns `EntryData` with `attachments: ["d1_video.mp4"]`
2. Client checks if each attachment exists locally
3. For missing attachments, client downloads via the file transfer protocol
4. For local attachments not on server, client uploads

The `sync` method does NOT transfer file content — only references.
File transfer is a separate step using this protocol.

## Stdin Transport

Stdin transport continues to use the existing JSON-based protocol:

- `attachment_get`: response contains base64-encoded `data` field
- `attachment_put`: request contains base64-encoded `data` field

This is acceptable because stdin is local-only. Implementations
SHOULD warn or reject files larger than 10MB over stdin transport.

## Security

- All HTTP file transfers MUST go through the same authentication
  as the sync protocol (`Authorization: Bearer <key>`)
- Filenames MUST be validated: no path traversal (`../`), no absolute
  paths, must match `{entry_id}_{name}` pattern
- Server MUST reject uploads that would exceed a configurable
  storage quota (default: no limit)

## Error Handling

| Scenario | Behavior |
|----------|----------|
| Unknown upload_id | 404 |
| Chunk offset mismatch | 409 Conflict, return expected offset |
| SHA-256 mismatch | Delete file, return error |
| File not found (download) | 404 |
| Storage full | 507 Insufficient Storage |
| Auth failure | 401 |
