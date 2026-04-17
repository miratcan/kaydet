import {
  Lora_400Regular,
  Lora_400Regular_Italic,
  Lora_700Bold,
  useFonts,
} from "@expo-google-fonts/lora";
import { StatusBar } from "expo-status-bar";
import React, { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, StyleSheet, View } from "react-native";
import {
  SafeAreaProvider,
  SafeAreaView,
} from "react-native-safe-area-context";
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
import EntryDetailScreen from "./src/screens/EntryDetailScreen";
import EntryListScreen from "./src/screens/EntryListScreen";
import SettingsScreen from "./src/screens/SettingsScreen";

type Screen = "list" | "settings" | "capture" | "detail";

export default function App() {
  const [fontsLoaded] = useFonts({
    Lora_400Regular,
    Lora_400Regular_Italic,
    Lora_700Bold,
  });

  const [screen, setScreen] = useState<Screen>("list");
  const [entries, setEntries] = useState<EntryData[]>([]);
  const [syncing, setSyncing] = useState(false);
  const [config, setConfig] = useState<SyncConfig | null>(null);
  const [configured, setConfigured] = useState(false);
  const [lastSyncAt, setLastSyncAt] = useState<Date | null>(null);
  const [syncError, setSyncError] = useState<string | null>(null);
  const [selectedEntry, setSelectedEntry] = useState<EntryData | null>(null);
  const [searchQuery, setSearchQuery] = useState("");

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
      setLastSyncAt(new Date());
      setSyncError(null);
    } catch (e: any) {
      const msg = e?.message ?? "Sync failed";
      setSyncError(
        msg.includes("Network") || msg.includes("fetch")
          ? "Offline"
          : msg
      );
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

  if (!fontsLoaded) {
    return (
      <View style={styles.container}>
        <ActivityIndicator color="#00bcd4" />
      </View>
    );
  }

  return (
    <SafeAreaProvider>
    <SafeAreaView style={styles.container} edges={["top", "bottom"]}>
      <StatusBar style="light" />
      {screen === "settings" && (
        <SettingsScreen onDone={handleSettingsDone} />
      )}
      {screen === "capture" && config && (
        <CaptureScreen config={config} onDone={handleCaptureDone} />
      )}
      {screen === "detail" && selectedEntry && (
        <EntryDetailScreen
          entry={selectedEntry}
          config={config}
          onBack={() => setScreen("list")}
          onTagPress={(tag) => {
            setSearchQuery(`#${tag}`);
            setScreen("list");
          }}
        />
      )}
      {screen === "list" && (
        <EntryListScreen
          entries={entries}
          syncing={syncing}
          lastSyncAt={lastSyncAt}
          syncError={syncError}
          config={config}
          query={searchQuery}
          onQueryChange={setSearchQuery}
          onSync={() => doSync()}
          onSettings={() => setScreen("settings")}
          onEntryPress={(entry) => {
            setSelectedEntry(entry);
            setScreen("detail");
          }}
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
    </SafeAreaProvider>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: "#1a1a1a",
  },
});
