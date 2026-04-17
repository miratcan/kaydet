import React from "react";
import { Text, StyleSheet } from "react-native";
import { colors } from "../lib/tokens";

interface Props {
  text: string;
  tags: string[];
  metadata: Record<string, string>;
  style?: object;
  onTokenPress: (query: string) => void;
}

export default function TagText({ text, tags, metadata, style, onTokenPress }: Props) {
  const tagSet = new Set(tags.map((t) => `#${t}`));
  // Build metadata token strings: "key:value"
  const kvTokens = Object.entries(metadata).map(([k, v]) => `${k}:${v}`);
  const kvSet = new Set(kvTokens);

  // The stored text has #tags but metadata key:value tokens are stripped by the server.
  // Reconstruct the full display text by appending metadata tokens.
  const fullText = kvTokens.length > 0
    ? `${text} ${kvTokens.join(" ")}`
    : text;

  const tokens = fullText.split(/(\S+)/g);

  return (
    <Text style={style}>
      {tokens.map((token, i) => {
        if (tagSet.has(token)) {
          return (
            <Text key={i} style={styles.tag} onPress={() => onTokenPress(token)}>
              {token}
            </Text>
          );
        }
        if (kvSet.has(token)) {
          return (
            <Text key={i} style={styles.kv} onPress={() => onTokenPress(token)}>
              {token}
            </Text>
          );
        }
        return token;
      })}
    </Text>
  );
}

const styles = StyleSheet.create({
  tag: { color: colors.text.tag },
  kv:  { color: colors.text.tag },
});
