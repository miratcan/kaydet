import { StatusBar } from "expo-status-bar";
import React, { useCallback, useEffect, useState } from "react";
import { SafeAreaView, StyleSheet } from "react-native";
import type { EntryData, SyncConfig } from "./src/lib/api";
import { fullFetch, incrementalSync } from "./src/lib/api";
import {
  cacheEntries,
  deleteCachedEntries,
  getCachedEntries,
  getSyncToken,
  isConfigured,
  loadConfig,
  setSyncToken,
} from "./src/lib/storage";
import CaptureScreen from "./src/screens/CaptureScreen";
import EntryListScreen from "./src/screens/EntryListScreen";
import SettingsScreen from "./src/screens/SettingsScreen";

type Screen = "list" | "settings" | "capture";

export default function App() {
  const [screen, setScreen] = useState<Screen>("list");
  const [entries, setEntries] = useState<EntryData[]>([]);
  const [syncing, setSyncing] = useState(false);
  const [config, setConfig] = useState<SyncConfig | null>(null);
  const [configured, setConfigured] = useState(false);

  useEffect(() => {
    (async () => {
      const cfg = await loadConfig();
      setConfig(cfg);
      const ok = await isConfigured();
      setConfigured(ok);
      const cached = await getCachedEntries();
      setEntries(cached);
      if (ok) {
        doSync(cfg);
      }
    })();
  }, []);

  const doSync = useCallback(async (cfg?: SyncConfig) => {
    const syncConfig = cfg ?? (await loadConfig());
    if (!syncConfig.serverUrl || !syncConfig.apiKey) return;

    setSyncing(true);
    try {
      const token = await getSyncToken();
      if (token === 0) {
        const result = await fullFetch(syncConfig);
        await cacheEntries(result.entries);
        await setSyncToken(result.token);
      } else {
        const result = await incrementalSync(syncConfig, token);
        if (result.entries.length > 0) {
          await cacheEntries(result.entries);
        }
        if (result.deleted.length > 0) {
          await deleteCachedEntries(result.deleted);
        }
        await setSyncToken(result.token);
      }
      const cached = await getCachedEntries();
      setEntries(cached);
    } catch (e) {
      console.error("Sync failed:", e);
    } finally {
      setSyncing(false);
    }
  }, []);

  const handleSettingsDone = useCallback(async () => {
    const cfg = await loadConfig();
    setConfig(cfg);
    const ok = await isConfigured();
    setConfigured(ok);
    setScreen("list");
    if (ok) {
      doSync(cfg);
    }
  }, [doSync]);

  const handleCaptureDone = useCallback(
    async (saved: boolean) => {
      setScreen("list");
      if (saved) {
        await doSync();
      }
    },
    [doSync]
  );

  return (
    <SafeAreaView style={styles.container}>
      <StatusBar style="light" />
      {screen === "settings" && (
        <SettingsScreen onDone={handleSettingsDone} />
      )}
      {screen === "capture" && config && (
        <CaptureScreen config={config} onDone={handleCaptureDone} />
      )}
      {screen === "list" && (
        <EntryListScreen
          entries={entries}
          syncing={syncing}
          onSync={() => doSync()}
          onSettings={() => setScreen("settings")}
          onCapture={() => {
            if (!configured) {
              setScreen("settings");
            } else {
              setScreen("capture");
            }
          }}
        />
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: "#1a1a1a",
  },
});
