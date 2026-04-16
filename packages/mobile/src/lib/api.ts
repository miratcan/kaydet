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

export async function pushEntries(
  config: SyncConfig,
  entries: EntryData[]
): Promise<{ accepted: number; conflicts: number; errors: string[] }> {
  const resp = await send(config, {
    method: "push",
    body: { entries, device_id: config.deviceId },
  });
  return resp.body as any;
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

export async function pushAttachment(
  config: SyncConfig,
  filename: string,
  data: string // base64-encoded
): Promise<void> {
  await send(config, {
    method: "attachment_put",
    body: { filename, data },
  });
}

export async function getAttachment(
  config: SyncConfig,
  filename: string
): Promise<{ found: boolean; data?: string }> {
  const resp = await send(config, {
    method: "attachment_get",
    body: { filename },
  });
  return resp.body as any;
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

export async function getAttachmentCached(
  config: SyncConfig,
  filename: string
): Promise<string | null> {
  const { getCachedAttachment, setCachedAttachment } = await import(
    "./storage"
  );
  const cached = await getCachedAttachment(filename);
  if (cached) return cached;

  const result = await getAttachment(config, filename);
  if (result.found && result.data) {
    await setCachedAttachment(filename, result.data);
    return result.data;
  }
  return null;
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
