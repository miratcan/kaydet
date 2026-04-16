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
    backgroundColor: "#1a1a1a",
    padding: 20,
  },
  header: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 30,
    paddingTop: 10,
  },
  title: {
    fontSize: 24,
    fontWeight: "bold",
    color: "#fff",
  },
  headerRight: {
    flexDirection: "row",
    alignItems: "center",
    gap: 16,
  },
  qrBtn: {
    backgroundColor: "#2a2a2a",
    borderWidth: 1,
    borderColor: "#444",
    borderRadius: 6,
    paddingVertical: 4,
    paddingHorizontal: 10,
  },
  qrBtnText: {
    color: "#00bcd4",
    fontSize: 14,
    fontWeight: "600",
  },
  doneBtn: {
    color: "#00bcd4",
    fontSize: 17,
    fontWeight: "600",
  },
  label: {
    color: "#aaa",
    fontSize: 13,
    marginBottom: 6,
    marginTop: 16,
  },
  input: {
    backgroundColor: "#2a2a2a",
    color: "#fff",
    borderRadius: 8,
    padding: 14,
    fontSize: 16,
    borderWidth: 1,
    borderColor: "#333",
  },
  testBtn: {
    backgroundColor: "#00bcd4",
    borderRadius: 8,
    padding: 14,
    alignItems: "center",
    marginTop: 24,
  },
  testBtnText: {
    color: "#1a1a1a",
    fontSize: 16,
    fontWeight: "600",
  },
  status: {
    marginTop: 12,
    fontSize: 14,
    textAlign: "center",
  },
  statusOk: {
    color: "#4caf50",
  },
  statusError: {
    color: "#ef5350",
  },
});
