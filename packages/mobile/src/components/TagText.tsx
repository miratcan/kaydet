import React from "react";
import { Text, StyleSheet } from "react-native";
import { colors } from "../lib/tokens";

interface Props {
  text: string;
  style?: object;
  onTagPress: (tag: string) => void;
}

const TAG_SPLIT = /(#[a-z][a-z0-9_-]*)/g;
const TAG_MATCH = /^#[a-z][a-z0-9_-]*$/;

export default function TagText({ text, style, onTagPress }: Props) {
  const parts = text.split(TAG_SPLIT);

  return (
    <Text style={style}>
      {parts.map((part, i) =>
        TAG_MATCH.test(part) ? (
          <Text key={i} style={styles.tag} onPress={() => onTagPress(part.slice(1))}>
            {part}
          </Text>
        ) : (
          part
        )
      )}
    </Text>
  );
}

const styles = StyleSheet.create({
  tag: { color: colors.text.tag },
});
