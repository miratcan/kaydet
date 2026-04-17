/**
 * Design tokens — single source of truth for all visual values.
 * No raw colors, numbers, or font names anywhere else.
 */

export const colors = {
  // Neutral surfaces — no paired text tokens, use colors.text.*
  bg: { base: "#1a1a1a" },
  surface: { base: "#2a2a2a", border: "#333" },

  // Global text hierarchy — works on all neutral surfaces
  text: {
    primary: "#e8e8e8",
    muted: "#888",
    faint: "#555",
    tag: "#ce93d8",
    date: "#4caf50",
    entryId: "#ffeb3b",
  },

  // Accent surfaces — each has its own paired text token(s)
  primary: { base: "#00bcd4", on: "#1a1a1a" },
  error:   { base: "#3a1a1a", on: "#ef9a9a", onAction: "#ef5350", border: "#5a2a2a" },

  overlay: "rgba(0,0,0,0.95)",
  white: "#fff",
  black: "#000",
};

export const spacing = {
  sm: 8,
  md: 16,
  lg: 24,
  xl: 40,
};

/**
 * md = 14, React Native system default.
 * All other values are relative to this anchor.
 */
export const fontSize = {
  sm: 12,
  md: 14,  // platform default — never change this
  lg: 17,
  xl: 22,
};

export const font = {
  serif: "Lora_400Regular",
  serifBold: "Lora_700Bold",
  serifItalic: "Lora_400Regular_Italic",
};

export const radius = {
  sm: 8,
  md: 20,
  full: 999,
};

/** Component-specific sizes — not part of the scale */
export const size = {
  thumb: 64,
  thumbLg: 80,
  fab: 56,
  fabRadius: 28,
  iconBtn: 36,
};
