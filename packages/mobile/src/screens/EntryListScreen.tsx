import React, { useEffect, useMemo, useState } from "react";
import {
  Image,
  RefreshControl,
  SectionList,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from "react-native";
import type { EntryData, SyncConfig } from "../lib/api";
import { getAttachmentCached } from "../lib/api";
import {
  filterEntries,
  formatLastSync,
  groupByDate,
} from "../lib/entryUtils";

interface Props {
  entries: EntryData[];
  syncing: boolean;
  lastSyncAt: Date | null;
  syncError: string | null;
  config: SyncConfig | null;
  onSync: () => void;
  onSettings: () => void;
  onCapture: () => void;
  onEntryPress: (entry: EntryData) => void;
}

const IMAGE_EXTS = /\.(jpg|jpeg|png|gif|webp)$/i;

function AttachmentThumb({
  filename,
  config,
}: {
  filename: string;
  config: SyncConfig | null;
}) {
  const [uri, setUri] = useState<string | null>(null);

  useEffect(() => {
    if (!config) return;
    let cancelled = false;
    getAttachmentCached(config, filename).then((b64) => {
      if (!cancelled && b64) {
        const ext = filename.split(".").pop()?.toLowerCase() ?? "jpeg";
        const mime =
          ext === "png"
            ? "image/png"
            : ext === "gif"
            ? "image/gif"
            : "image/jpeg";
        setUri(`data:${mime};base64,${b64}`);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [filename, config]);

  if (!uri) return <View style={styles.thumbPlaceholder} />;
  return <Image source={{ uri }} style={styles.thumb} />;
}

function formatTags(tags: string[]): string {
  return tags.map((t) => `#${t}`).join(" ");
}

function EntryCard({
  entry,
  config,
  onPress,
}: {
  entry: EntryData;
  config: SyncConfig | null;
  onPress: () => void;
}) {
  const lines = entry.text.split("\n");
  const isLong = entry.text.length > 140 || lines.length > 3;
  const preview = isLong
    ? lines[0].length > 140
      ? lines[0].slice(0, 140) + "…"
      : lines[0]
    : entry.text;

  return (
    <TouchableOpacity style={styles.card} onPress={onPress} activeOpacity={0.7}>
      <View style={styles.cardHeader}>
        <Text style={styles.timestamp}>{entry.timestamp}</Text>
        <Text style={styles.entryId}>[{entry.entry_id}]</Text>
      </View>
      <Text style={styles.text}>{preview}</Text>
      {isLong && <Text style={styles.expandHint}>tap to read more</Text>}
      {entry.tags.length > 0 && (
        <Text style={styles.tags}>{formatTags(entry.tags)}</Text>
      )}
      {entry.attachments.length > 0 && (
        <View style={styles.thumbRow}>
          {entry.attachments
            .filter((f) => IMAGE_EXTS.test(f))
            .slice(0, 4)
            .map((f) => (
              <AttachmentThumb key={f} filename={f} config={config} />
            ))}
          {entry.attachments.some((f) => !IMAGE_EXTS.test(f)) && (
            <Text style={styles.attachments}>
              📎 {entry.attachments.filter((f) => !IMAGE_EXTS.test(f)).length}
            </Text>
          )}
        </View>
      )}
    </TouchableOpacity>
  );
}

export default function EntryListScreen({
  entries,
  syncing,
  lastSyncAt,
  syncError,
  config,
  onSync,
  onSettings,
  onCapture,
  onEntryPress,
}: Props) {
  const [query, setQuery] = useState("");

  const filtered = useMemo(
    () => filterEntries(entries, query),
    [entries, query]
  );
  const sections = useMemo(() => groupByDate(filtered), [filtered]);

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <View>
          <Text style={styles.title}>kaydet</Text>
          {lastSyncAt && (
            <Text style={styles.syncHint}>
              synced {formatLastSync(lastSyncAt)}
            </Text>
          )}
        </View>
        <View style={styles.headerButtons}>
          <TouchableOpacity
            onPress={onSync}
            disabled={syncing}
            style={styles.headerBtn}
          >
            <Text style={styles.headerBtnText}>
              {syncing ? "…" : "Sync"}
            </Text>
          </TouchableOpacity>
          <TouchableOpacity onPress={onSettings} style={styles.headerBtn}>
            <Text style={styles.headerBtnText}>Settings</Text>
          </TouchableOpacity>
        </View>
      </View>

      {syncError && (
        <View style={styles.errorBanner}>
          <Text style={styles.errorBannerText}>
            {syncError === "Offline" ? "⚡ No connection" : `⚠ ${syncError}`}
          </Text>
          <TouchableOpacity onPress={onSync}>
            <Text style={styles.errorBannerRetry}>Retry</Text>
          </TouchableOpacity>
        </View>
      )}

      <View style={styles.searchBar}>
        <TextInput
          style={styles.searchInput}
          value={query}
          onChangeText={setQuery}
          placeholder="Search entries, #tags…"
          placeholderTextColor="#555"
          autoCapitalize="none"
          autoCorrect={false}
          clearButtonMode="while-editing"
        />
        {query.length > 0 && (
          <TouchableOpacity onPress={() => setQuery("")} style={styles.clearBtn}>
            <Text style={styles.clearBtnText}>✕</Text>
          </TouchableOpacity>
        )}
      </View>

      {query.length > 0 && (
        <Text style={styles.resultCount}>
          {filtered.length} result{filtered.length !== 1 ? "s" : ""}
        </Text>
      )}

      {filtered.length === 0 ? (
        <View style={styles.empty}>
          {entries.length === 0 ? (
            <>
              <Text style={styles.emptyText}>No entries yet.</Text>
              <Text style={styles.emptyHint}>
                Tap + to capture, or sync from server.
              </Text>
            </>
          ) : (
            <Text style={styles.emptyText}>No results for "{query}"</Text>
          )}
        </View>
      ) : (
        <SectionList
          sections={sections}
          keyExtractor={(item) => item.entry_id}
          renderItem={({ item }) => (
            <EntryCard
              entry={item}
              config={config}
              onPress={() => onEntryPress(item)}
            />
          )}
          renderSectionHeader={({ section }) => (
            <View style={styles.sectionHeader}>
              <Text style={styles.sectionTitle}>{section.title}</Text>
            </View>
          )}
          contentContainerStyle={styles.list}
          stickySectionHeadersEnabled
          refreshControl={
            <RefreshControl
              refreshing={syncing}
              onRefresh={onSync}
              tintColor="#00bcd4"
              colors={["#00bcd4"]}
            />
          }
        />
      )}

      <TouchableOpacity style={styles.fab} onPress={onCapture}>
        <Text style={styles.fabText}>+</Text>
      </TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#1a1a1a" },
  header: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingHorizontal: 16,
    paddingTop: 10,
    paddingBottom: 8,
    backgroundColor: "#1a1a1a",
    borderBottomWidth: 1,
    borderBottomColor: "#333",
  },
  title: {
    fontSize: 22,
    fontFamily: "Lora_700Bold",
    color: "#00bcd4",
  },
  syncHint: {
    fontSize: 11,
    color: "#555",
    marginTop: 1,
  },
  headerButtons: { flexDirection: "row", gap: 12 },
  headerBtn: { paddingVertical: 6, paddingHorizontal: 12 },
  headerBtnText: { color: "#00bcd4", fontSize: 15 },
  errorBanner: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    backgroundColor: "#3a1a1a",
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: "#5a2a2a",
  },
  errorBannerText: {
    color: "#ef9a9a",
    fontSize: 13,
  },
  errorBannerRetry: {
    color: "#ef5350",
    fontSize: 13,
    fontWeight: "600",
  },
  searchBar: {
    flexDirection: "row",
    alignItems: "center",
    marginHorizontal: 12,
    marginVertical: 8,
    backgroundColor: "#2a2a2a",
    borderRadius: 10,
    borderWidth: 1,
    borderColor: "#333",
    paddingHorizontal: 12,
  },
  searchInput: {
    flex: 1,
    color: "#fff",
    fontSize: 15,
    paddingVertical: 8,
  },
  clearBtn: { padding: 4 },
  clearBtnText: { color: "#555", fontSize: 14 },
  resultCount: {
    color: "#555",
    fontSize: 12,
    paddingHorizontal: 16,
    marginBottom: 4,
  },
  list: { paddingBottom: 80 },
  sectionHeader: {
    backgroundColor: "#222",
    paddingHorizontal: 16,
    paddingVertical: 6,
  },
  sectionTitle: { color: "#4caf50", fontSize: 13, fontWeight: "600" },
  card: {
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: "#2a2a2a",
  },
  cardHeader: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    marginBottom: 4,
  },
  timestamp: { color: "#aaa", fontSize: 13, fontWeight: "600" },
  entryId: { color: "#ffeb3b", fontSize: 12 },
  text: {
    color: "#e0e0e0",
    fontSize: 15,
    lineHeight: 24,
    fontFamily: "Lora_400Regular",
  },
  expandHint: {
    color: "#555",
    fontSize: 12,
    marginTop: 4,
  },
  tags: { color: "#ce93d8", fontSize: 13, marginTop: 4 },
  attachments: { color: "#888", fontSize: 12, marginTop: 4 },
  thumbRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 6,
    marginTop: 8,
    alignItems: "center",
  },
  thumb: {
    width: 64,
    height: 64,
    borderRadius: 6,
    backgroundColor: "#333",
  },
  thumbPlaceholder: {
    width: 64,
    height: 64,
    borderRadius: 6,
    backgroundColor: "#2a2a2a",
  },
  empty: {
    flex: 1,
    justifyContent: "center",
    alignItems: "center",
    padding: 40,
  },
  emptyText: { color: "#888", fontSize: 18, marginBottom: 8 },
  emptyHint: { color: "#555", fontSize: 14, textAlign: "center" },
  fab: {
    position: "absolute",
    right: 20,
    bottom: 30,
    width: 56,
    height: 56,
    borderRadius: 28,
    backgroundColor: "#00bcd4",
    justifyContent: "center",
    alignItems: "center",
    elevation: 5,
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.3,
    shadowRadius: 4,
  },
  fabText: {
    color: "#1a1a1a",
    fontSize: 28,
    fontWeight: "300",
    marginTop: -2,
  },
});
