import { CameraView, useCameraPermissions } from "expo-camera";
import React, { useState } from "react";
import {
  ActivityIndicator,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from "react-native";

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
        <ActivityIndicator color="#00bcd4" />
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
  container: { flex: 1, backgroundColor: "#000" },
  center: {
    flex: 1,
    backgroundColor: "#1a1a1a",
    justifyContent: "center",
    alignItems: "center",
    padding: 20,
  },
  camera: { flex: 1 },
  overlay: {
    ...StyleSheet.absoluteFillObject,
    justifyContent: "space-between",
    paddingBottom: 40,
  },
  topBar: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingHorizontal: 20,
    paddingTop: 16,
    paddingBottom: 10,
    backgroundColor: "rgba(0,0,0,0.5)",
  },
  title: {
    color: "#fff",
    fontSize: 17,
    fontWeight: "600",
  },
  cancelText: {
    color: "#00bcd4",
    fontSize: 16,
    width: 60,
  },
  frame: {
    alignSelf: "center",
    width: 240,
    height: 240,
    borderWidth: 2,
    borderColor: "#00bcd4",
    borderRadius: 12,
    backgroundColor: "transparent",
  },
  hint: {
    color: "#fff",
    textAlign: "center",
    fontSize: 14,
    paddingHorizontal: 32,
    backgroundColor: "rgba(0,0,0,0.5)",
    paddingVertical: 10,
  },
  error: {
    color: "#ef5350",
    textAlign: "center",
    fontSize: 13,
    paddingHorizontal: 32,
  },
  message: { color: "#aaa", fontSize: 16, marginBottom: 20, textAlign: "center" },
  btn: {
    backgroundColor: "#00bcd4",
    borderRadius: 8,
    padding: 14,
    paddingHorizontal: 24,
    marginBottom: 12,
  },
  btnText: { color: "#1a1a1a", fontSize: 16, fontWeight: "600" },
  cancelBtn: { padding: 12 },
});
