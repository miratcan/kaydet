import React, { useRef, useState, useMemo, useEffect } from "react";
import type { SectionList as SectionListType } from "react-native";
import { colors, fontSize, font, radius, size, spacing } from "../lib/tokens";
import {
  Animated,
  Easing,
  RefreshControl,
  SectionList,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from "react-native";
import { RectButton, Swipeable } from "react-native-gesture-handler";
import ViewShot from "react-native-view-shot";
import type { EntryData, SyncConfig } from "../lib/api";
import {
  filterEntries,
  formatLastSync,
  groupByDate,
} from "../lib/entryUtils";
import TagText from "../components/TagText";
import AttachmentViewer from "../components/AttachmentViewer";
import ShardExplosion from "../components/ShardExplosion";

interface Props {
  entries: EntryData[];
  syncing: boolean;
  lastSyncAt: Date | null;
  syncError: string | null;
  config: SyncConfig | null;
  query: string;
  onQueryChange: (q: string) => void;
  onSync: () => void;
  onSettings: () => void;
  onCapture: () => void;
  onEditEntry: (entry: EntryData) => void;
  onDeleteEntry: (entry: EntryData) => void;
}

function EntryCard({
  entry,
  config,
  onTagPress,
  onEdit,
  onDelete,
}: {
  entry: EntryData;
  config: SyncConfig | null;
  onTagPress: (query: string) => void;
  onEdit: () => void;
  onDelete: () => void;
}) {
  const viewShotRef = useRef<ViewShot>(null);
  const cardRef = useRef<View>(null);
  const [shardUri, setShardUri] = useState<string | null>(null);
  const [shardLayout, setShardLayout] = useState<{ x: number; y: number; w: number; h: number } | null>(null);
  const collapseAnim = useRef(new Animated.Value(1)).current;
  const [collapsing, setCollapsing] = useState(false);

  const handleDelete = async () => {
    // 1. Capture screenshot of card
    let uri: string | null = null;
    try { uri = await (viewShotRef.current as any)?.capture?.(); } catch {}
    if (!uri) {
      // Web fallback: just collapse
      setCollapsing(true);
      Animated.timing(collapseAnim, {
        toValue: 0,
        duration: 280,
        easing: Easing.in(Easing.cubic),
        useNativeDriver: false,
      }).start(() => onDelete());
      return;
    }

    // 2. Measure card position on screen
    cardRef.current?.measureInWindow((x, y, w, h) => {
      setShardLayout({ x, y, w, h });
      setShardUri(uri);
    });
  };

  const handleShardDone = () => {
    // 3. Shards done → collapse card height
    setShardUri(null);
    setCollapsing(true);
    Animated.timing(collapseAnim, {
      toValue: 0,
      duration: 280,
      easing: Easing.in(Easing.cubic),
      useNativeDriver: false,
    }).start(() => {
      onDelete();
    });
  };

  const renderRightActions = () => (
    <View style={styles.swipeActions}>
      <RectButton style={styles.swipeEdit} onPress={onEdit}>
        <Text style={styles.swipeEditText}>Edit</Text>
      </RectButton>
      <RectButton style={styles.swipeDelete} onPress={handleDelete}>
        <Text style={styles.swipeDeleteText}>Delete</Text>
      </RectButton>
    </View>
  );

  return (
    <>
      <Animated.View
        style={[
          collapsing && {
            overflow: "hidden",
            maxHeight: collapseAnim.interpolate({
              inputRange: [0, 1],
              outputRange: [0, 500],
            }),
            opacity: collapseAnim,
          },
        ]}
      >
        <Swipeable renderRightActions={renderRightActions} overshootRight={false}>
          <ViewShot ref={viewShotRef} options={{ format: "png", quality: 0.8 }}>
            <View ref={cardRef} style={styles.card}>
              <View style={styles.cardHeader}>
                <Text style={styles.timestamp}>{entry.timestamp}</Text>
                <Text style={styles.entryId}>[{entry.entry_id}]</Text>
              </View>
              <TagText text={entry.text} tags={entry.tags} metadata={entry.metadata} style={styles.text} onTokenPress={onTagPress} />
              <AttachmentViewer filenames={entry.attachments} config={config} />
            </View>
          </ViewShot>
        </Swipeable>
      </Animated.View>

      {shardUri && shardLayout && (
        <ShardExplosion
          imageUri={shardUri}
          entryWidth={shardLayout.w}
          entryHeight={shardLayout.h}
          originX={shardLayout.x}
          originY={shardLayout.y}
          onDone={handleShardDone}
        />
      )}
    </>
  );
}

export default function EntryListScreen({
  entries,
  syncing,
  lastSyncAt,
  syncError,
  config,
  query,
  onQueryChange,
  onSync,
  onSettings,
  onCapture,
  onEditEntry,
  onDeleteEntry,
}: Props) {
  const listRef = useRef<SectionListType<any>>(null);
  const filtered = useMemo(
    () => filterEntries(entries, query),
    [entries, query]
  );
  const sections = useMemo(() => groupByDate(filtered), [filtered]);

  useEffect(() => {
    if (sections.length > 0) {
      listRef.current?.scrollToLocation({ sectionIndex: 0, itemIndex: 0, animated: false });
    }
  }, [query]);

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => onQueryChange("")}>
          <Text style={styles.title}>kaydet</Text>
          {lastSyncAt && (
            <Text style={styles.syncHint}>
              synced {formatLastSync(lastSyncAt)}
            </Text>
          )}
        </TouchableOpacity>
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
          onChangeText={onQueryChange}
          placeholder="Search entries, #tags…"
          placeholderTextColor={colors.text.faint}
          autoCapitalize="none"
          autoCorrect={false}
          clearButtonMode="while-editing"
        />
        {query.length > 0 && (
          <TouchableOpacity onPress={() => onQueryChange("")} style={styles.clearBtn}>
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
          ref={listRef}
          sections={sections}
          keyExtractor={(item) => item.entry_id}
          renderItem={({ item }) => (
            <EntryCard
              entry={item}
              config={config}
              onTagPress={(query) => onQueryChange(query)}
              onEdit={() => onEditEntry(item)}
              onDelete={() => onDeleteEntry(item)}
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
              tintColor={colors.primary.base}
              colors={[colors.primary.base]}
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
  container: { flex: 1, backgroundColor: colors.bg.base },
  header: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    backgroundColor: colors.bg.base,
    borderBottomWidth: 1,
    borderBottomColor: colors.surface.border,
  },
  title: {
    fontSize: fontSize.xl,
    fontFamily: font.serifBold,
    color: colors.primary.base,
  },
  syncHint: {
    fontSize: fontSize.sm,
    color: colors.text.faint,
    marginTop: 1,
  },
  headerButtons: { flexDirection: "row", gap: spacing.sm },
  headerBtn: { paddingVertical: spacing.sm, paddingHorizontal: spacing.sm },
  headerBtnText: { color: colors.primary.base, fontSize: fontSize.md },
  errorBanner: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    backgroundColor: colors.error.base,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderBottomWidth: 1,
    borderBottomColor: colors.error.border,
  },
  errorBannerText: {
    color: colors.error.on,
    fontSize: fontSize.sm,
  },
  errorBannerRetry: {
    color: colors.error.onAction,
    fontSize: fontSize.sm,
    fontWeight: "600",
  },
  searchBar: {
    flexDirection: "row",
    alignItems: "center",
    marginHorizontal: spacing.sm,
    marginVertical: spacing.sm,
    backgroundColor: colors.surface.base,
    borderRadius: radius.sm,
    borderWidth: 1,
    borderColor: colors.surface.border,
    paddingHorizontal: spacing.sm,
  },
  searchInput: {
    flex: 1,
    color: colors.white,
    fontSize: fontSize.md,
    paddingVertical: spacing.sm,
  },
  clearBtn: { padding: spacing.sm },
  clearBtnText: { color: colors.text.faint, fontSize: fontSize.sm },
  resultCount: {
    color: colors.text.faint,
    fontSize: fontSize.sm,
    paddingHorizontal: spacing.md,
    marginBottom: spacing.sm,
  },
  list: { paddingBottom: size.fab + spacing.lg },
  sectionHeader: {
    backgroundColor: colors.bg.base,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
  sectionTitle: { color: colors.text.date, fontSize: fontSize.sm },
  card: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderBottomWidth: 1,
    borderBottomColor: colors.surface.border,
    backgroundColor: colors.bg.base,
  },
  cardHeader: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    marginBottom: spacing.sm,
  },
  timestamp: { color: colors.text.muted, fontSize: fontSize.sm, fontWeight: "600" },
  entryId: { color: colors.text.entryId, fontSize: fontSize.sm },
  text: {
    color: colors.text.primary,
    fontSize: fontSize.md,
    lineHeight: fontSize.md * 1.6,
    fontFamily: font.serif,
  },
  swipeActions: {
    flexDirection: "row",
  },
  swipeEdit: {
    backgroundColor: colors.primary.base,
    justifyContent: "center",
    alignItems: "center",
    paddingHorizontal: spacing.lg,
  },
  swipeEditText: {
    color: colors.primary.on,
    fontSize: fontSize.sm,
    fontWeight: "600",
  },
  swipeDelete: {
    backgroundColor: colors.error.onAction,
    justifyContent: "center",
    alignItems: "center",
    paddingHorizontal: spacing.lg,
  },
  swipeDeleteText: {
    color: colors.white,
    fontSize: fontSize.sm,
    fontWeight: "600",
  },
  empty: {
    flex: 1,
    justifyContent: "center",
    alignItems: "center",
    padding: spacing.xl,
  },
  emptyText: { color: colors.text.muted, fontSize: fontSize.lg, marginBottom: spacing.sm },
  emptyHint: { color: colors.text.faint, fontSize: fontSize.md, textAlign: "center" },
  fab: {
    position: "absolute",
    right: spacing.md,
    bottom: spacing.lg,
    width: size.fab,
    height: size.fab,
    borderRadius: size.fabRadius,
    backgroundColor: colors.primary.base,
    justifyContent: "center",
    alignItems: "center",
    elevation: 5,
    boxShadow: "0px 2px 4px rgba(0,0,0,0.3)",
  },
  fabText: {
    color: colors.primary.on,
    fontSize: fontSize.xl,
    fontWeight: "300",
    marginTop: -2,
  },
});
