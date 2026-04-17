/**
 * Kaydet sync protocol client.
 * Mirrors the PWA implementation — all communication via POST /sync.
 */

export interface SyncConfig {
  serverUrl: string;
  apiKey: string;
  deviceId: string;
}

export interface EntryData {
  entry_id: string;
  source_file: string;
  timestamp: string;
  text: string;
  tags: string[];
  metadata: Record<string, string>;
  attachments: string[];
  encrypted_secret?: string | null;
  updated_at?: string | null;
}

interface SyncChange {
  id: number;
  entry_id: string;
  action: "created" | "updated" | "deleted";
  device_id?: string;
  created_at: string;
}

interface ProtocolMessage {
  method: string;
  body: Record<string, unknown>;
}

async function send(
  config: SyncConfig,
  msg: ProtocolMessage
): Promise<ProtocolMessage> {
  const resp = await fetch(`${config.serverUrl}/sync`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${config.apiKey}`,
    },
    body: JSON.stringify(msg),
  });
  if (resp.status === 401) {
    throw new Error("Invalid API key");
  }
  if (!resp.ok) {
    throw new Error(`Server error: ${resp.status}`);
  }
  return resp.json();
}

export async function fetchChanges(
  config: SyncConfig,
  since = 0,
  limit = 500
): Promise<{
  changes: SyncChange[];
  new_token: number;
  has_more: boolean;
}> {
  const resp = await send(config, {
    method: "changes",
    body: { since, limit },
  });
  return resp.body as any;
}

export async function fetchEntries(
  config: SyncConfig,
  entryIds: string[]
): Promise<EntryData[]> {
  const resp = await send(config, {
    method: "entries",
    body: { entry_ids: entryIds },
  });
  return (resp.body as any).entries ?? [];
}

interface PushEntry {
  entry_id: string;
  source_file: string;
  timestamp: string;
  text: string;
  attachments: string[];
  updated_at?: string | null;
}

export async function pushEntries(
  config: SyncConfig,
  entries: PushEntry[]
): Promise<{ accepted: number; conflicts: number; errors: string[]; entries: EntryData[] }> {
  const resp = await send(config, {
    method: "push",
    body: { entries, device_id: config.deviceId },
  });
  const body = resp.body as any;
  return {
    accepted: body.accepted ?? 0,
    conflicts: body.conflicts ?? 0,
    errors: body.errors ?? [],
    entries: body.entries ?? [],
  };
}

export async function deleteEntry(
  config: SyncConfig,
  entryId: string
): Promise<{ deleted: boolean; error?: string }> {
  const resp = await send(config, {
    method: "delete",
    body: { entry_id: entryId, device_id: config.deviceId },
  });
  return resp.body as any;
}

export async function updateEntry(
  config: SyncConfig,
  entryId: string,
  text: string,
  tags?: string[],
  metadata?: Record<string, string>
): Promise<{ updated: boolean; error?: string }> {
  const resp = await send(config, {
    method: "update",
    body: {
      entry_id: entryId,
      text,
      tags,
      metadata,
      device_id: config.deviceId,
    },
  });
  return resp.body as any;
}

/**
 * Download an attachment to a local file path using binary HTTP.
 * Returns the local file:// URI on success, null on failure.
 */
export async function downloadAttachment(
  config: SyncConfig,
  filename: string,
  localPath: string
): Promise<string | null> {
  const FileSystem = await import("expo-file-system");
  const url = `${config.serverUrl}/files/${encodeURIComponent(filename)}`;
  const result = await FileSystem.downloadAsync(url, localPath, {
    headers: { Authorization: `Bearer ${config.apiKey}` },
  });
  if (result.status === 200) return result.uri;
  return null;
}

/**
 * Upload an attachment using chunked binary HTTP.
 * sha256 and size must be computed by the caller.
 */
export async function uploadAttachmentChunked(
  config: SyncConfig,
  filename: string,
  fileUri: string,
  size: number,
  sha256: string,
  onProgress?: (received: number, total: number) => void
): Promise<void> {
  const FileSystem = await import("expo-file-system");

  // Step 1: start
  const startResp = await fetch(`${config.serverUrl}/files/upload-start`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${config.apiKey}`,
    },
    body: JSON.stringify({ filename, size, sha256 }),
  });
  if (!startResp.ok) throw new Error(`Upload start failed: ${startResp.status}`);
  const startBody = await startResp.json();
  if (startBody.already_exists) return; // server already has it
  const { upload_id, chunk_size, existing_offset } = startBody;

  // Step 2: upload chunks
  let offset: number = existing_offset ?? 0;
  while (offset < size) {
    const length = Math.min(chunk_size, size - offset);
    // Read chunk as base64, then send as binary
    const b64 = await FileSystem.readAsStringAsync(fileUri, {
      encoding: "base64",
      position: offset,
      length,
    } as any);
    // Decode base64 → binary string → Uint8Array
    const binary = atob(b64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);

    const chunkResp = await fetch(`${config.serverUrl}/files/upload-chunk`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${config.apiKey}`,
        "Content-Type": "application/octet-stream",
        "X-Upload-Id": upload_id,
        "X-Chunk-Offset": String(offset),
        "Content-Length": String(bytes.length),
      },
      body: bytes,
    });
    if (!chunkResp.ok) throw new Error(`Chunk upload failed at offset ${offset}`);
    const chunkBody = await chunkResp.json();
    offset += length;
    onProgress?.(offset, size);
  }

  // Step 3: finish
  const finishResp = await fetch(`${config.serverUrl}/files/upload-finish`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${config.apiKey}`,
    },
    body: JSON.stringify({ upload_id }),
  });
  if (!finishResp.ok) throw new Error(`Upload finish failed: ${finishResp.status}`);
  const finishBody = await finishResp.json();
  if (!finishBody.ok) throw new Error(finishBody.error ?? "Upload verification failed");
}

export async function fullFetch(
  config: SyncConfig,
  batchSize = 100
): Promise<{ entries: EntryData[]; token: number }> {
  // Paginate through all changes
  let since = 0;
  const seen = new Map<string, string>();

  while (true) {
    const result = await fetchChanges(config, since);
    for (const c of result.changes) {
      seen.set(c.entry_id, c.action);
    }
    if (!result.has_more) {
      // Final token
      const toFetch = [...seen.entries()]
        .filter(([, action]) => action !== "deleted")
        .map(([id]) => id);

      // Fetch in batches to avoid huge payloads
      const entries: EntryData[] = [];
      for (let i = 0; i < toFetch.length; i += batchSize) {
        const batch = toFetch.slice(i, i + batchSize);
        const fetched = await fetchEntries(config, batch);
        entries.push(...fetched);
      }

      return { entries, token: result.new_token };
    }
    since = result.new_token;
  }
}

export async function incrementalSync(
  config: SyncConfig,
  since: number
): Promise<{ entries: EntryData[]; deleted: string[]; token: number }> {
  const result = await fetchChanges(config, since);

  const seen = new Map<string, string>();
  for (const c of result.changes) {
    seen.set(c.entry_id, c.action);
  }

  const toFetch = [...seen.entries()]
    .filter(([, action]) => action !== "deleted")
    .map(([id]) => id);

  const deleted = [...seen.entries()]
    .filter(([, action]) => action === "deleted")
    .map(([id]) => id);

  const entries = toFetch.length > 0
    ? await fetchEntries(config, toFetch)
    : [];

  return { entries, deleted, token: result.new_token };
}

/**
 * Download an attachment to the local cache directory.
 * Returns the local file:// URI (cached or freshly downloaded).
 */
export async function getAttachmentCached(
  config: SyncConfig,
  filename: string
): Promise<string | null> {
  const FileSystem = await import("expo-file-system");
  const cacheDir = ((FileSystem as any).cacheDirectory ?? "") + "attachments/";
  const localPath = cacheDir + filename;

  const info = await FileSystem.getInfoAsync(localPath);
  if (info.exists) return (info as any).uri ?? localPath;

  await (FileSystem as any).makeDirectoryAsync(cacheDir, { intermediates: true });
  return downloadAttachment(config, filename, localPath);
}

export async function testConnection(
  config: SyncConfig
): Promise<{ ok: boolean; error?: string }> {
  try {
    await fetchChanges(config, 0);
    return { ok: true };
  } catch (e: any) {
    return { ok: false, error: e.message };
  }
}
