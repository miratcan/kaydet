import { CameraView, useCameraPermissions } from "expo-camera";
import React, { useState } from "react";
import {
  ActivityIndicator,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from "react-native";
import { colors, fontSize, radius, spacing } from "../lib/tokens";

interface Props {
  onScanned: (serverUrl: string, apiKey: string) => void;
  onCancel: () => void;
}

export default function QRScanScreen({ onScanned, onCancel }: Props) {
  const [permission, requestPermission] = useCameraPermissions();
  const [scanned, setScanned] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!permission) {
    return (
      <View style={styles.center}>
        <ActivityIndicator color={colors.primary.base} />
      </View>
    );
  }

  if (!permission.granted) {
    return (
      <View style={styles.center}>
        <Text style={styles.message}>Camera permission is required.</Text>
        <TouchableOpacity style={styles.btn} onPress={requestPermission}>
          <Text style={styles.btnText}>Grant Permission</Text>
        </TouchableOpacity>
        <TouchableOpacity style={styles.cancelBtn} onPress={onCancel}>
          <Text style={styles.cancelText}>Cancel</Text>
        </TouchableOpacity>
      </View>
    );
  }

  const handleBarcode = ({ data }: { data: string }) => {
    if (scanned) return;
    setScanned(true);

    // Expected format: kaydet://<api_key>@<host:port>
    try {
      const match = data.match(/^kaydet:\/\/([^@]+)@(.+)$/);
      if (!match) {
        setError("Invalid QR code. Not a kaydet config.");
        setScanned(false);
        return;
      }
      const apiKey = match[1];
      const hostPort = match[2];
      const serverUrl = `http://${hostPort}`;
      onScanned(serverUrl, apiKey);
    } catch {
      setError("Failed to parse QR code.");
      setScanned(false);
    }
  };

  return (
    <View style={styles.container}>
      <CameraView
        style={styles.camera}
        facing="back"
        onBarcodeScanned={scanned ? undefined : handleBarcode}
        barcodeScannerSettings={{ barcodeTypes: ["qr"] }}
      />

      <View style={styles.overlay}>
        <View style={styles.topBar}>
          <TouchableOpacity onPress={onCancel}>
            <Text style={styles.cancelText}>Cancel</Text>
          </TouchableOpacity>
          <Text style={styles.title}>Scan QR Code</Text>
          <View style={{ width: 60 }} />
        </View>

        <View style={styles.frame} />

        <Text style={styles.hint}>
          Point at the QR code shown on your kaydet server
        </Text>

        {error && <Text style={styles.error}>{error}</Text>}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.black },
  center: {
    flex: 1,
    backgroundColor: colors.bg.base,
    justifyContent: "center",
    alignItems: "center",
    padding: spacing.lg,
  },
  camera: { flex: 1 },
  overlay: {
    ...StyleSheet.absoluteFillObject,
    justifyContent: "space-between",
    paddingBottom: spacing.xl,
  },
  topBar: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingHorizontal: spacing.md,
    paddingTop: spacing.md,
    paddingBottom: spacing.sm,
    backgroundColor: "rgba(0,0,0,0.5)",
  },
  title: {
    color: colors.white,
    fontSize: fontSize.lg,
    fontWeight: "600",
  },
  cancelText: {
    color: colors.primary.base,
    fontSize: fontSize.md,
    width: 60,
  },
  frame: {
    alignSelf: "center",
    width: 240,
    height: 240,
    borderWidth: 2,
    borderColor: colors.primary.base,
    borderRadius: radius.sm,
    backgroundColor: "transparent",
  },
  hint: {
    color: colors.white,
    textAlign: "center",
    fontSize: fontSize.md,
    paddingHorizontal: spacing.xl,
    backgroundColor: "rgba(0,0,0,0.5)",
    paddingVertical: spacing.sm,
  },
  error: {
    color: colors.error.onAction,
    textAlign: "center",
    fontSize: fontSize.sm,
    paddingHorizontal: spacing.xl,
  },
  message: { color: colors.text.muted, fontSize: fontSize.md, marginBottom: spacing.md, textAlign: "center" },
  btn: {
    backgroundColor: colors.primary.base,
    borderRadius: radius.sm,
    padding: spacing.sm,
    paddingHorizontal: spacing.md,
    marginBottom: spacing.sm,
  },
  btnText: { color: colors.primary.on, fontSize: fontSize.md, fontWeight: "600" },
  cancelBtn: { padding: spacing.sm },
});
