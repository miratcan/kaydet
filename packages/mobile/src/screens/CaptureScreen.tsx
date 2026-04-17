import * as DocumentPicker from "expo-document-picker";
import * as ImagePicker from "expo-image-picker";
import React, { useState } from "react";
import {
  Alert,
  Image,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from "react-native";
import type { SyncConfig } from "../lib/api";
import { colors, fontSize, font, radius, size, spacing } from "../lib/tokens";
import { pushAttachment, pushEntries } from "../lib/api";
import { cacheEntries } from "../lib/storage";

interface Attachment {
  uri: string;
  name: string;
  type: string;
}

interface Props {
  config: SyncConfig;
  onDone: (saved: boolean) => void;
}

export default function CaptureScreen({ config, onDone }: Props) {
  const [text, setText] = useState("");
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [saving, setSaving] = useState(false);

  const pickFromCamera = async () => {
    const perm = await ImagePicker.requestCameraPermissionsAsync();
    if (!perm.granted) {
      Alert.alert("Permission required", "Camera access is needed.");
      return;
    }
    const result = await ImagePicker.launchCameraAsync({
      quality: 0.8,
    });
    if (!result.canceled && result.assets[0]) {
      const asset = result.assets[0];
      const name = asset.fileName ?? `photo_${Date.now()}.jpg`;
      setAttachments((prev) => [
        ...prev,
        { uri: asset.uri, name, type: asset.mimeType ?? "image/jpeg" },
      ]);
    }
  };

  const pickFromGallery = async () => {
    const perm = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!perm.granted) {
      Alert.alert("Permission required", "Gallery access is needed.");
      return;
    }
    const result = await ImagePicker.launchImageLibraryAsync({
      quality: 0.8,
      allowsMultipleSelection: true,
    });
    if (!result.canceled) {
      const newAtts = result.assets.map((asset) => ({
        uri: asset.uri,
        name: asset.fileName ?? `image_${Date.now()}.jpg`,
        type: asset.mimeType ?? "image/jpeg",
      }));
      setAttachments((prev) => [...prev, ...newAtts]);
    }
  };

  const pickFile = async () => {
    const result = await DocumentPicker.getDocumentAsync({
      multiple: true,
    });
    if (!result.canceled) {
      const newAtts = result.assets.map((asset) => ({
        uri: asset.uri,
        name: asset.name,
        type: asset.mimeType ?? "application/octet-stream",
      }));
      setAttachments((prev) => [...prev, ...newAtts]);
    }
  };

  const removeAttachment = (index: number) => {
    setAttachments((prev) => prev.filter((_, i) => i !== index));
  };

  const handleSave = async () => {
    const trimmed = text.trim();
    if (!trimmed && attachments.length === 0) return;

    setSaving(true);
    const now = new Date();
    const sourceFile = now.toISOString().slice(0, 10) + ".txt";
    const timestamp =
      String(now.getHours()).padStart(2, "0") +
      ":" +
      String(now.getMinutes()).padStart(2, "0");

    const entry = {
      entry_id: "",
      source_file: sourceFile,
      timestamp,
      text: trimmed || "(attachment)",
      attachments: attachments.map((a) => a.name),
      updated_at: now.toISOString(),
    };

    try {
      const result = await pushEntries(config, [entry]);
      if (result.accepted > 0) {
        // Cache the server-resolved entry (with parsed tags, metadata, entry_id)
        if (result.entries.length > 0) {
          await cacheEntries(result.entries);
        }
        // Upload attachments (best-effort)
        for (const att of attachments) {
          try {
            await uploadAttachment(config, att);
          } catch {
            // Attachment upload failure is non-fatal
          }
        }
        setSaving(false);
        onDone(true);
      } else {
        setSaving(false);
        Alert.alert("Error", result.errors?.[0] ?? "Failed to save");
      }
    } catch (e: any) {
      setSaving(false);
      Alert.alert("Error", e.message);
    }
  };

  const hasContent = text.trim().length > 0 || attachments.length > 0;

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <View style={styles.header}>
        <TouchableOpacity onPress={() => onDone(false)}>
          <Text style={styles.cancelBtn}>Cancel</Text>
        </TouchableOpacity>
        <Text style={styles.title}>Capture</Text>
        <TouchableOpacity
          onPress={handleSave}
          disabled={saving || !hasContent}
        >
          <Text
            style={[
              styles.saveBtn,
              (!hasContent || saving) && styles.saveBtnDisabled,
            ]}
          >
            {saving ? "..." : "Save"}
          </Text>
        </TouchableOpacity>
      </View>

      <TextInput
        style={styles.input}
        value={text}
        onChangeText={setText}
        placeholder="What's on your mind?"
        placeholderTextColor={colors.text.faint}
        multiline
        autoFocus
        textAlignVertical="top"
      />

      {attachments.length > 0 && (
        <ScrollView
          horizontal
          style={styles.attachmentStrip}
          contentContainerStyle={styles.attachmentStripContent}
          showsHorizontalScrollIndicator={false}
        >
          {attachments.map((att, i) => (
            <View key={i} style={styles.attachmentThumb}>
              {att.type.startsWith("image/") ? (
                <Image
                  source={{ uri: att.uri }}
                  style={styles.thumbImage}
                />
              ) : (
                <View style={styles.thumbFile}>
                  <Text style={styles.thumbFileIcon}>F</Text>
                </View>
              )}
              <TouchableOpacity
                style={styles.thumbRemove}
                onPress={() => removeAttachment(i)}
              >
                <Text style={styles.thumbRemoveText}>x</Text>
              </TouchableOpacity>
              <Text style={styles.thumbName} numberOfLines={1}>
                {att.name}
              </Text>
            </View>
          ))}
        </ScrollView>
      )}

      <View style={styles.toolbar}>
        <TouchableOpacity style={styles.toolBtn} onPress={pickFromCamera}>
          <Text style={styles.toolBtnText}>Camera</Text>
        </TouchableOpacity>
        <TouchableOpacity style={styles.toolBtn} onPress={pickFromGallery}>
          <Text style={styles.toolBtnText}>Gallery</Text>
        </TouchableOpacity>
        <TouchableOpacity style={styles.toolBtn} onPress={pickFile}>
          <Text style={styles.toolBtnText}>File</Text>
        </TouchableOpacity>
      </View>

      <Text style={styles.hint}>
        Use #tags and key:value for metadata
      </Text>
    </KeyboardAvoidingView>
  );
}

async function uploadAttachment(
  config: SyncConfig,
  att: Attachment
): Promise<void> {
  const response = await fetch(att.uri);
  const blob = await response.blob();
  const reader = new FileReader();
  const base64 = await new Promise<string>((resolve) => {
    reader.onloadend = () => {
      const result = reader.result as string;
      resolve(result.split(",")[1] ?? "");
    };
    reader.readAsDataURL(blob);
  });
  await pushAttachment(config, att.name, base64);
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
  attachmentStrip: {
    maxHeight: 100,
    marginTop: spacing.sm,
  },
  attachmentStripContent: {
    gap: spacing.sm,
  },
  attachmentThumb: {
    width: size.thumb + spacing.sm,
    alignItems: "center",
  },
  thumbImage: {
    width: size.thumb,
    height: size.thumb,
    borderRadius: radius.sm,
    backgroundColor: colors.surface.border,
  },
  thumbFile: {
    width: size.thumb,
    height: size.thumb,
    borderRadius: radius.sm,
    backgroundColor: colors.surface.border,
    justifyContent: "center",
    alignItems: "center",
  },
  thumbFileIcon: {
    color: colors.text.muted,
    fontSize: fontSize.xl,
    fontWeight: "bold",
  },
  thumbRemove: {
    position: "absolute",
    top: -4,
    right: 0,
    width: spacing.lg,
    height: spacing.lg,
    borderRadius: radius.full,
    backgroundColor: colors.error.onAction,
    justifyContent: "center",
    alignItems: "center",
  },
  thumbRemoveText: {
    color: colors.white,
    fontSize: fontSize.sm,
    fontWeight: "bold",
  },
  thumbName: {
    color: colors.text.muted,
    fontSize: fontSize.sm,
    marginTop: 2,
    width: size.thumb,
    textAlign: "center",
  },
  toolbar: {
    flexDirection: "row",
    justifyContent: "center",
    gap: spacing.sm,
    marginTop: spacing.sm,
    paddingVertical: spacing.sm,
  },
  toolBtn: {
    backgroundColor: colors.surface.base,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.surface.border,
  },
  toolBtnText: {
    color: colors.primary.base,
    fontSize: fontSize.md,
  },
  hint: {
    color: colors.text.faint,
    fontSize: fontSize.sm,
    marginTop: spacing.sm,
    textAlign: "center",
  },
});
