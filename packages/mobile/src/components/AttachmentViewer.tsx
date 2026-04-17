import { useVideoPlayer, VideoView } from "expo-video";
import { colors, fontSize, radius, size, spacing } from "../lib/tokens";
import React, { useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  Dimensions,
  Image,
  Modal,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from "react-native";
import type { SyncConfig } from "../lib/api";
import { getAttachmentCached } from "../lib/api";

const IMAGE_EXTS = /\.(jpg|jpeg|png|gif|webp)$/i;
const VIDEO_EXTS = /\.(mp4|mov|m4v|webm|mkv)$/i;

interface AttachmentItemProps {
  filename: string;
  config: SyncConfig | null;
  onPress: (filename: string, localUri: string | null, isVideo: boolean) => void;
}

function AttachmentItem({ filename, config, onPress }: AttachmentItemProps) {
  const [localUri, setLocalUri] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const isImage = IMAGE_EXTS.test(filename);
  const isVideo = VIDEO_EXTS.test(filename);
  const isMedia = isImage || isVideo;

  useEffect(() => {
    if (!config || !isMedia) return;
    setLoading(true);
    getAttachmentCached(config, filename)
      .then(setLocalUri)
      .finally(() => setLoading(false));
  }, [filename, config]);

  return (
    <TouchableOpacity
      style={styles.item}
      onPress={() => onPress(filename, localUri, isVideo)}
      activeOpacity={0.7}
    >
      <View style={styles.thumb}>
        {loading ? (
          <ActivityIndicator color={colors.primary.base} />
        ) : isImage && localUri ? (
          <Image source={{ uri: localUri }} style={styles.thumbImage} />
        ) : isVideo ? (
          <View style={styles.thumbVideo}>
            <Text style={styles.playIcon}>▶</Text>
          </View>
        ) : (
          <View style={styles.thumbFile}>
            <Text style={styles.fileIcon}>F</Text>
          </View>
        )}
      </View>
    </TouchableOpacity>
  );
}

interface LightboxProps {
  visible: boolean;
  uri: string | null;
  isVideo: boolean;
  onClose: () => void;
}

function Lightbox({ visible, uri, isVideo, onClose }: LightboxProps) {
  const player = useVideoPlayer(isVideo && uri ? uri : null, (p) => {
    p.loop = false;
  });

  if (!visible || !uri) return null;

  return (
    <Modal
      visible={visible}
      transparent
      animationType="fade"
      onRequestClose={onClose}
      statusBarTranslucent
    >
      <View style={styles.overlay}>
        <TouchableOpacity style={styles.closeBtn} onPress={onClose}>
          <Text style={styles.closeText}>✕</Text>
        </TouchableOpacity>

        {isVideo ? (
          <VideoView
            player={player}
            style={styles.video}
            allowsFullscreen
            allowsPictureInPicture={false}
            contentFit="contain"
          />
        ) : (
          <ScrollView
            maximumZoomScale={4}
            minimumZoomScale={1}
            contentContainerStyle={styles.imageContainer}
          >
            <Image
              source={{ uri }}
              style={styles.fullImage}
              resizeMode="contain"
            />
          </ScrollView>
        )}
      </View>
    </Modal>
  );
}

interface AttachmentViewerProps {
  filenames: string[];
  config: SyncConfig | null;
}

export default function AttachmentViewer({
  filenames,
  config,
}: AttachmentViewerProps) {
  const [lightbox, setLightbox] = useState<{
    uri: string;
    isVideo: boolean;
  } | null>(null);

  const handlePress = (
    filename: string,
    localUri: string | null,
    isVideo: boolean
  ) => {
    if (!localUri) return; // not loaded yet or non-media
    setLightbox({ uri: localUri, isVideo });
  };

  if (filenames.length === 0) return null;

  return (
    <View style={styles.container}>
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={styles.strip}
      >
        {filenames.map((f, i) => (
          <AttachmentItem
            key={`${i}-${f}`}
            filename={f}
            config={config}
            onPress={handlePress}
          />
        ))}
      </ScrollView>

      <Lightbox
        visible={!!lightbox}
        uri={lightbox?.uri ?? null}
        isVideo={lightbox?.isVideo ?? false}
        onClose={() => setLightbox(null)}
      />
    </View>
  );
}

const { width, height } = Dimensions.get("window");

const styles = StyleSheet.create({
  container: { marginTop: spacing.sm },
  strip: { gap: spacing.sm, paddingBottom: spacing.sm },
  item: { alignItems: "center" },
  thumb: {
    width: size.thumbLg,
    height: size.thumbLg,
    borderRadius: radius.sm,
    backgroundColor: colors.surface.base,
    justifyContent: "center",
    alignItems: "center",
    overflow: "hidden",
    borderWidth: 1,
    borderColor: colors.surface.border,
  },
  thumbImage: { width: size.thumbLg, height: size.thumbLg, borderRadius: radius.sm },
  thumbVideo: {
    width: size.thumbLg,
    height: size.thumbLg,
    borderRadius: radius.sm,
    backgroundColor: colors.surface.base,
    justifyContent: "center",
    alignItems: "center",
  },
  playIcon: { color: colors.primary.base, fontSize: fontSize.xl },
  thumbFile: {
    width: size.thumbLg,
    height: size.thumbLg,
    justifyContent: "center",
    alignItems: "center",
  },
  fileIcon: { color: colors.text.faint, fontSize: fontSize.xl, fontWeight: "bold" },
  overlay: {
    flex: 1,
    backgroundColor: colors.overlay,
    justifyContent: "center",
    alignItems: "center",
  },
  closeBtn: {
    position: "absolute",
    top: spacing.xl,
    right: spacing.md,
    zIndex: 10,
    width: size.iconBtn,
    height: size.iconBtn,
    borderRadius: size.iconBtn / 2,
    backgroundColor: "rgba(255,255,255,0.15)",
    justifyContent: "center",
    alignItems: "center",
  },
  closeText: { color: colors.white, fontSize: fontSize.lg, fontWeight: "bold" },
  imageContainer: {
    width,
    height,
    justifyContent: "center",
    alignItems: "center",
  },
  fullImage: { width, height },
  video: { width, height: height * 0.7 },
});
