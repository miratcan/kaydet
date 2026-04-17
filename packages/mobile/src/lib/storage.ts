/**
 * Local storage for config and cached entries.
 * Uses AsyncStorage (works on web, iOS, Android).
 */

import AsyncStorage from "@react-native-async-storage/async-storage";
import type { EntryData, SyncConfig } from "./api";

const KEYS = {
  serverUrl: "kaydet_server_url",
  apiKey: "kaydet_api_key",
  syncToken: "kaydet_sync_token",
  entries: "kaydet_entries",
} as const;


const DEVICE_ID = "kaydet-mobile";

// -- Config --

export async function loadConfig(): Promise<SyncConfig> {
  const [serverUrl, apiKey] = await AsyncStorage.multiGet([
    KEYS.serverUrl,
    KEYS.apiKey,
  ]);
  return {
    serverUrl: serverUrl[1] ?? "",
    apiKey: apiKey[1] ?? "",
    deviceId: DEVICE_ID,
  };
}

export async function saveConfig(
  serverUrl: string,
  apiKey: string
): Promise<void> {
  await AsyncStorage.multiSet([
    [KEYS.serverUrl, serverUrl.replace(/\/+$/, "")],
    [KEYS.apiKey, apiKey],
  ]);
}

export async function isConfigured(): Promise<boolean> {
  const config = await loadConfig();
  return config.serverUrl.length > 0 && config.apiKey.length > 0;
}

// -- Sync token --

export async function getSyncToken(): Promise<number> {
  const val = await AsyncStorage.getItem(KEYS.syncToken);
  return val ? parseInt(val, 10) : 0;
}

export async function setSyncToken(token: number): Promise<void> {
  await AsyncStorage.setItem(KEYS.syncToken, String(token));
}

// -- Cached entries --

export async function getCachedEntries(): Promise<EntryData[]> {
  const raw = await AsyncStorage.getItem(KEYS.entries);
  if (!raw) return [];
  const entries: EntryData[] = JSON.parse(raw);
  return entries.sort((a, b) => {
    if (a.source_file !== b.source_file) {
      return b.source_file.localeCompare(a.source_file);
    }
    return b.timestamp.localeCompare(a.timestamp);
  });
}

export async function cacheEntries(
  incoming: EntryData[]
): Promise<void> {
  const existing = await getCachedEntries();
  const map = new Map(existing.map((e) => [e.entry_id, e]));
  for (const entry of incoming) {
    map.set(entry.entry_id, entry);
  }
  await AsyncStorage.setItem(
    KEYS.entries,
    JSON.stringify([...map.values()])
  );
}

export async function deleteCachedEntries(
  ids: string[]
): Promise<void> {
  const existing = await getCachedEntries();
  const idSet = new Set(ids);
  const filtered = existing.filter((e) => !idSet.has(e.entry_id));
  await AsyncStorage.setItem(KEYS.entries, JSON.stringify(filtered));
}

export async function clearAllData(): Promise<void> {
  await AsyncStorage.multiRemove(Object.values(KEYS));
}

