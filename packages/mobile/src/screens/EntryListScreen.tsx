import React from "react";
import {
  SectionList,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from "react-native";
import type { EntryData } from "../lib/api";

interface Props {
  entries: EntryData[];
  syncing: boolean;
  onSync: () => void;
  onSettings: () => void;
  onCapture: () => void;
}

interface Section {
  title: string;
  data: EntryData[];
}

function groupByDate(entries: EntryData[]): Section[] {
  const groups = new Map<string, EntryData[]>();
  for (const entry of entries) {
    const day = entry.source_file.replace(/\.txt$/, "");
    if (!groups.has(day)) groups.set(day, []);
    groups.get(day)!.push(entry);
  }
  return [...groups.entries()]
    .sort((a, b) => b[0].localeCompare(a[0]))
    .map(([title, data]) => ({ title, data }));
}

function formatTags(tags: string[]): string {
  return tags.map((t) => `#${t}`).join(" ");
}

function EntryCard({ entry }: { entry: EntryData }) {
  const lines = entry.text.split("\n");
  const preview =
    lines[0].length > 140 ? lines[0].slice(0, 140) + "..." : lines[0];

  return (
    <View style={styles.card}>
      <View style={styles.cardHeader}>
        <Text style={styles.timestamp}>{entry.timestamp}</Text>
        <Text style={styles.entryId}>[{entry.entry_id}]</Text>
      </View>
      <Text style={styles.text}>{preview}</Text>
      {entry.tags.length > 0 && (
        <Text style={styles.tags}>{formatTags(entry.tags)}</Text>
      )}
      {entry.attachments.length > 0 && (
        <Text style={styles.attachments}>
          {entry.attachments.length} attachment
          {entry.attachments.length > 1 ? "s" : ""}
        </Text>
      )}
    </View>
  );
}

export default function EntryListScreen({
  entries,
  syncing,
  onSync,
  onSettings,
  onCapture,
}: Props) {
  const sections = groupByDate(entries);

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.title}>kaydet</Text>
        <View style={styles.headerButtons}>
          <TouchableOpacity
            onPress={onSync}
            disabled={syncing}
            style={styles.headerBtn}
          >
            <Text style={styles.headerBtnText}>
              {syncing ? "..." : "Sync"}
            </Text>
          </TouchableOpacity>
          <TouchableOpacity
            onPress={onSettings}
            style={styles.headerBtn}
          >
            <Text style={styles.headerBtnText}>Settings</Text>
          </TouchableOpacity>
        </View>
      </View>

      {entries.length === 0 ? (
        <View style={styles.empty}>
          <Text style={styles.emptyText}>No entries yet.</Text>
          <Text style={styles.emptyHint}>
            Tap + to capture, or sync from server.
          </Text>
        </View>
      ) : (
        <SectionList
          sections={sections}
          keyExtractor={(item) => item.entry_id}
          renderItem={({ item }) => <EntryCard entry={item} />}
          renderSectionHeader={({ section }) => (
            <View style={styles.sectionHeader}>
              <Text style={styles.sectionTitle}>{section.title}</Text>
            </View>
          )}
          contentContainerStyle={styles.list}
          stickySectionHeadersEnabled
        />
      )}

      <TouchableOpacity style={styles.fab} onPress={onCapture}>
        <Text style={styles.fabText}>+</Text>
      </TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: "#1a1a1a",
  },
  header: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingHorizontal: 16,
    paddingTop: 10,
    paddingBottom: 10,
    backgroundColor: "#1a1a1a",
    borderBottomWidth: 1,
    borderBottomColor: "#333",
  },
  title: {
    fontSize: 22,
    fontWeight: "bold",
    color: "#00bcd4",
  },
  headerButtons: {
    flexDirection: "row",
    gap: 12,
  },
  headerBtn: {
    paddingVertical: 6,
    paddingHorizontal: 12,
  },
  headerBtnText: {
    color: "#00bcd4",
    fontSize: 15,
  },
  list: {
    paddingBottom: 80,
  },
  sectionHeader: {
    backgroundColor: "#222",
    paddingHorizontal: 16,
    paddingVertical: 6,
  },
  sectionTitle: {
    color: "#4caf50",
    fontSize: 13,
    fontWeight: "600",
  },
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
  timestamp: {
    color: "#aaa",
    fontSize: 13,
    fontWeight: "600",
  },
  entryId: {
    color: "#ffeb3b",
    fontSize: 12,
  },
  text: {
    color: "#e0e0e0",
    fontSize: 15,
    lineHeight: 22,
  },
  tags: {
    color: "#ce93d8",
    fontSize: 13,
    marginTop: 4,
  },
  attachments: {
    color: "#888",
    fontSize: 12,
    marginTop: 4,
  },
  empty: {
    flex: 1,
    justifyContent: "center",
    alignItems: "center",
    padding: 40,
  },
  emptyText: {
    color: "#888",
    fontSize: 18,
    marginBottom: 8,
  },
  emptyHint: {
    color: "#555",
    fontSize: 14,
    textAlign: "center",
  },
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
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.3,
    shadowRadius: 4,
    elevation: 5,
  },
  fabText: {
    color: "#1a1a1a",
    fontSize: 28,
    fontWeight: "300",
    marginTop: -2,
  },
});
