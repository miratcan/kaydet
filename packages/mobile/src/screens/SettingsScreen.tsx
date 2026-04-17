import React, { useEffect, useState } from "react";
import {
  ActivityIndicator,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from "react-native";
import { testConnection } from "../lib/api";
import { loadConfig, saveConfig } from "../lib/storage";
import { colors, fontSize, radius, spacing } from "../lib/tokens";
import QRScanScreen from "./QRScanScreen";

interface Props {
  onDone: () => void;
}

export default function SettingsScreen({ onDone }: Props) {
  const [serverUrl, setServerUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [testing, setTesting] = useState(false);
  const [showQR, setShowQR] = useState(false);
  const [status, setStatus] = useState<{
    ok: boolean;
    message: string;
  } | null>(null);

  useEffect(() => {
    loadConfig().then((cfg) => {
      setServerUrl(cfg.serverUrl);
      setApiKey(cfg.apiKey);
    });
  }, []);

  const handleSave = async () => {
    const url = serverUrl.replace(/\/+$/, "");
    await saveConfig(url, apiKey);
    setServerUrl(url);
    setStatus(null);
  };

  const handleQRScanned = async (scannedUrl: string, scannedKey: string) => {
    setServerUrl(scannedUrl);
    setApiKey(scannedKey);
    await saveConfig(scannedUrl, scannedKey);
    setShowQR(false);
    setStatus({ ok: true, message: "Config loaded from QR" });
  };

  const handleTest = async () => {
    setTesting(true);
    setStatus(null);
    await handleSave();
    const cfg = { serverUrl, apiKey, deviceId: "kaydet-mobile" };
    const result = await testConnection(cfg);
    setTesting(false);
    if (result.ok) {
      setStatus({ ok: true, message: "Connected" });
    } else {
      setStatus({ ok: false, message: result.error ?? "Failed" });
    }
  };

  if (showQR) {
    return (
      <QRScanScreen
        onScanned={handleQRScanned}
        onCancel={() => setShowQR(false)}
      />
    );
  }

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.title}>Settings</Text>
        <View style={styles.headerRight}>
          <TouchableOpacity onPress={() => setShowQR(true)} style={styles.qrBtn}>
            <Text style={styles.qrBtnText}>QR</Text>
          </TouchableOpacity>
          <TouchableOpacity onPress={onDone}>
            <Text style={styles.doneBtn}>Done</Text>
          </TouchableOpacity>
        </View>
      </View>

      <Text style={styles.label}>Server URL</Text>
      <TextInput
        style={styles.input}
        value={serverUrl}
        onChangeText={setServerUrl}
        placeholder="https://example.com"
        placeholderTextColor="#666"
        autoCapitalize="none"
        autoCorrect={false}
        keyboardType="url"
      />

      <Text style={styles.label}>API Key</Text>
      <TextInput
        style={styles.input}
        value={apiKey}
        onChangeText={setApiKey}
        placeholder="kyd_..."
        placeholderTextColor="#666"
        autoCapitalize="none"
        autoCorrect={false}
        secureTextEntry
      />

      <TouchableOpacity
        style={styles.testBtn}
        onPress={handleTest}
        disabled={testing || !serverUrl || !apiKey}
      >
        {testing ? (
          <ActivityIndicator color="#1a1a1a" />
        ) : (
          <Text style={styles.testBtnText}>Test Connection</Text>
        )}
      </TouchableOpacity>

      {status && (
        <Text
          style={[
            styles.status,
            status.ok ? styles.statusOk : styles.statusError,
          ]}
        >
          {status.message}
        </Text>
      )}
    </View>
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
    marginBottom: spacing.lg,
    paddingTop: spacing.sm,
  },
  title: {
    fontSize: fontSize.xl,
    fontWeight: "bold",
    color: colors.white,
  },
  headerRight: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
  },
  qrBtn: {
    backgroundColor: colors.surface.base,
    borderWidth: 1,
    borderColor: colors.surface.border,
    borderRadius: radius.sm,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.sm,
  },
  qrBtnText: {
    color: colors.primary.base,
    fontSize: fontSize.sm,
    fontWeight: "600",
  },
  doneBtn: {
    color: colors.primary.base,
    fontSize: fontSize.lg,
    fontWeight: "600",
  },
  label: {
    color: colors.text.muted,
    fontSize: fontSize.sm,
    marginBottom: spacing.sm,
    marginTop: spacing.md,
  },
  input: {
    backgroundColor: colors.surface.base,
    color: colors.white,
    borderRadius: radius.sm,
    padding: spacing.sm,
    fontSize: fontSize.md,
    borderWidth: 1,
    borderColor: colors.surface.border,
  },
  testBtn: {
    backgroundColor: colors.primary.base,
    borderRadius: radius.sm,
    padding: spacing.sm,
    alignItems: "center",
    marginTop: spacing.lg,
  },
  testBtnText: {
    color: colors.primary.on,
    fontSize: fontSize.md,
    fontWeight: "600",
  },
  status: {
    marginTop: spacing.sm,
    fontSize: fontSize.sm,
    textAlign: "center",
  },
  statusOk: {
    color: colors.text.date,
  },
  statusError: {
    color: colors.error.onAction,
  },
});
