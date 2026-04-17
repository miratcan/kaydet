import React, { useState } from "react";
import {
  Alert,
  KeyboardAvoidingView,
  Platform,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from "react-native";
import type { EntryData, SyncConfig } from "../lib/api";
import { updateEntry } from "../lib/api";
import { cacheEntries } from "../lib/storage";
import { colors, fontSize, font, radius, spacing } from "../lib/tokens";

interface Props {
  config: SyncConfig;
  entry: EntryData;
  onDone: (saved: boolean) => void;
}

export default function EditScreen({ config, entry, onDone }: Props) {
  // Reconstruct the full text including metadata tokens (same logic as TagText)
  const kvTokens = Object.entries(entry.metadata).map(([k, v]) => `${k}:${v}`);
  const initialText = kvTokens.length > 0
    ? `${entry.text} ${kvTokens.join(" ")}`
    : entry.text;

  const [text, setText] = useState(initialText);
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    const trimmed = text.trim();
    if (!trimmed) return;

    setSaving(true);
    try {
      const result = await updateEntry(config, entry.entry_id, trimmed);
      if (result.updated) {
        // Re-fetch the updated entry by syncing; for now patch local cache
        await cacheEntries([{ ...entry, text: trimmed, tags: [], metadata: {} }]);
        onDone(true);
      } else {
        Alert.alert("Error", result.error ?? "Failed to update");
        setSaving(false);
      }
    } catch (e: any) {
      Alert.alert("Error", e.message);
      setSaving(false);
    }
  };

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <View style={styles.header}>
        <TouchableOpacity onPress={() => onDone(false)}>
          <Text style={styles.cancelBtn}>Cancel</Text>
        </TouchableOpacity>
        <Text style={styles.title}>Edit</Text>
        <TouchableOpacity onPress={handleSave} disabled={saving || !text.trim()}>
          <Text style={[styles.saveBtn, (!text.trim() || saving) && styles.saveBtnDisabled]}>
            {saving ? "..." : "Save"}
          </Text>
        </TouchableOpacity>
      </View>

      <TextInput
        style={styles.input}
        value={text}
        onChangeText={setText}
        multiline
        autoFocus
        textAlignVertical="top"
      />
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.bg.base,
    padding: spacing.md,
  },
  header: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: spacing.md,
    paddingTop: spacing.sm,
  },
  title: {
    fontSize: fontSize.lg,
    fontWeight: "600",
    color: colors.white,
  },
  cancelBtn: {
    color: colors.text.muted,
    fontSize: fontSize.lg,
  },
  saveBtn: {
    color: colors.primary.base,
    fontSize: fontSize.lg,
    fontWeight: "600",
  },
  saveBtnDisabled: {
    opacity: 0.4,
  },
  input: {
    flex: 1,
    backgroundColor: colors.surface.base,
    color: colors.white,
    borderRadius: radius.sm,
    padding: spacing.md,
    fontSize: fontSize.md,
    lineHeight: fontSize.md * 1.6,
    fontFamily: font.serif,
    borderWidth: 1,
    borderColor: colors.surface.border,
  },
});
