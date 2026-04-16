import React from "react";
import {
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from "react-native";
import type { EntryData } from "../lib/api";

interface Props {
  entry: EntryData;
  onBack: () => void;
}

export default function EntryDetailScreen({ entry, onBack }: Props) {
  const date = entry.source_file.replace(/\.txt$/, "");

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={onBack} style={styles.backBtn}>
          <Text style={styles.backBtnText}>‹ Back</Text>
        </TouchableOpacity>
        <Text style={styles.headerDate}>{date}</Text>
        <View style={{ width: 60 }} />
      </View>

      <ScrollView
        style={styles.scroll}
        contentContainerStyle={styles.content}
      >
        <View style={styles.meta}>
          <Text style={styles.timestamp}>{entry.timestamp}</Text>
          <Text style={styles.entryId}>[{entry.entry_id}]</Text>
        </View>

        <Text style={styles.text}>{entry.text}</Text>

        {entry.tags.length > 0 && (
          <View style={styles.tagsRow}>
            {entry.tags.map((tag) => (
              <View key={tag} style={styles.tagChip}>
                <Text style={styles.tagChipText}>#{tag}</Text>
              </View>
            ))}
          </View>
        )}

        {Object.keys(entry.metadata).length > 0 && (
          <View style={styles.metadataBox}>
            {Object.entries(entry.metadata).map(([k, v]) => (
              <Text key={k} style={styles.metadataItem}>
                <Text style={styles.metadataKey}>{k}:</Text> {v}
              </Text>
            ))}
          </View>
        )}

        {entry.attachments.length > 0 && (
          <View style={styles.attachmentsBox}>
            <Text style={styles.attachmentsTitle}>Attachments</Text>
            {entry.attachments.map((name) => (
              <Text key={name} style={styles.attachmentName}>
                📎 {name}
              </Text>
            ))}
          </View>
        )}
      </ScrollView>
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
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: "#333",
  },
  backBtn: { width: 60 },
  backBtnText: { color: "#00bcd4", fontSize: 17 },
  headerDate: { color: "#4caf50", fontSize: 14, fontWeight: "600" },
  scroll: { flex: 1 },
  content: { padding: 20, paddingBottom: 60 },
  meta: {
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
    marginBottom: 16,
  },
  timestamp: { color: "#aaa", fontSize: 14, fontWeight: "600" },
  entryId: { color: "#ffeb3b", fontSize: 12 },
  text: {
    color: "#e8e8e8",
    fontSize: 17,
    lineHeight: 28,
    fontFamily: "Lora_400Regular",
  },
  tagsRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
    marginTop: 20,
  },
  tagChip: {
    backgroundColor: "#2a1a3a",
    borderRadius: 12,
    paddingVertical: 4,
    paddingHorizontal: 10,
    borderWidth: 1,
    borderColor: "#ce93d8",
  },
  tagChipText: { color: "#ce93d8", fontSize: 13 },
  metadataBox: {
    marginTop: 20,
    backgroundColor: "#222",
    borderRadius: 8,
    padding: 12,
    gap: 4,
  },
  metadataItem: { color: "#aaa", fontSize: 13 },
  metadataKey: { color: "#888", fontWeight: "600" },
  attachmentsBox: { marginTop: 20 },
  attachmentsTitle: {
    color: "#888",
    fontSize: 13,
    fontWeight: "600",
    marginBottom: 8,
  },
  attachmentName: { color: "#aaa", fontSize: 14, marginBottom: 4 },
});
