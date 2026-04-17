import React from "react";
import { colors, fontSize, font, radius, spacing } from "../lib/tokens";
import {
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from "react-native";
import AttachmentViewer from "../components/AttachmentViewer";
import TagText from "../components/TagText";
import type { EntryData, SyncConfig } from "../lib/api";

interface Props {
  entry: EntryData;
  config: SyncConfig | null;
  onBack: () => void;
  onTagPress: (tag: string) => void;
}

export default function EntryDetailScreen({ entry, config, onBack, onTagPress }: Props) {
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

        <TagText
          text={entry.text}
          style={styles.text}
          onTagPress={onTagPress}
        />

        {Object.keys(entry.metadata).length > 0 && (
          <View style={styles.metadataBox}>
            {Object.entries(entry.metadata).map(([k, v]) => (
              <Text key={k} style={styles.metadataItem}>
                <Text style={styles.metadataKey}>{k}:</Text> {v}
              </Text>
            ))}
          </View>
        )}

        <AttachmentViewer filenames={entry.attachments} config={config} />
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg.base },
  header: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderBottomWidth: 1,
    borderBottomColor: colors.surface.border,
  },
  backBtn: { width: 60 },
  backBtnText: { color: colors.primary.base, fontSize: fontSize.lg },
  headerDate: { color: colors.text.date, fontSize: fontSize.sm, fontWeight: "600" },
  scroll: { flex: 1 },
  content: { padding: spacing.md, paddingBottom: spacing.xl },
  meta: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    marginBottom: spacing.md,
  },
  timestamp: { color: colors.text.muted, fontSize: fontSize.md, fontWeight: "600" },
  entryId: { color: colors.text.entryId, fontSize: fontSize.sm },
  text: {
    color: colors.text.primary,
    fontSize: fontSize.lg,
    lineHeight: fontSize.lg * 1.65,
    fontFamily: font.serif,
  },
  metadataBox: {
    marginTop: spacing.lg,
    backgroundColor: colors.surface.base,
    borderRadius: radius.sm,
    padding: spacing.sm,
    gap: spacing.sm,
  },
  metadataItem: { color: colors.text.muted, fontSize: fontSize.sm },
  metadataKey: { color: colors.text.primary, fontWeight: "600" },
});
