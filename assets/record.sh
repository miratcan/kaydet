#!/usr/bin/env bash
set -euo pipefail

LANG="${1:-tr}"
case "$LANG" in
    tr) TAPE="kaydet-demo.tape" ;;
    en) TAPE="kaydet-demo-en.tape" ;;
    *)  echo "Usage: $0 {tr|en}" >&2; exit 1 ;;
esac

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TMP_DIR="$SCRIPT_DIR/tmp"
BACKUP_DIR="$SCRIPT_DIR/.record-backup"
CONFIG_FILE="${HOME}/.config/kaydet/config.ini"

cleanup() {
    echo "==> Restoring kaydet config..."
    if [ -f "$BACKUP_DIR/config.ini" ]; then
        cp "$BACKUP_DIR/config.ini" "$CONFIG_FILE"
    fi
    if [ -d "$BACKUP_DIR/storage" ]; then
        ORIG_STORAGE=$(grep "^storage_dir" "$BACKUP_DIR/config.ini" | head -1 | cut -d= -f2 | xargs)
        [ -n "$ORIG_STORAGE" ] && mkdir -p "$ORIG_STORAGE" && cp -r "$BACKUP_DIR/storage/." "$ORIG_STORAGE/" 2>/dev/null || true
    fi
    echo "==> Restore complete."
}

trap cleanup EXIT

echo "==> Backing up current kaydet state..."
mkdir -p "$BACKUP_DIR"
cp "$CONFIG_FILE" "$BACKUP_DIR/config.ini"
STORAGE_DIR=$(grep "^storage_dir" "$CONFIG_FILE" | head -1 | cut -d= -f2 | xargs)
[ -d "$STORAGE_DIR" ] && mkdir -p "$BACKUP_DIR/storage" && cp -r "$STORAGE_DIR/." "$BACKUP_DIR/storage/" 2>/dev/null || true

echo "==> Creating fresh tmp environment at $TMP_DIR"
rm -rf "$TMP_DIR"
mkdir -p "$TMP_DIR"

echo "==> Pointing kaydet to tmp..."
sed -i '' "s|^storage_dir = .*|storage_dir = ${TMP_DIR}|" "$CONFIG_FILE"
sed -i '' "s|^log_dir = .*|log_dir = ${TMP_DIR}|" "$CONFIG_FILE"
if grep -q "^index_dir" "$CONFIG_FILE"; then
    sed -i '' "s|^index_dir = .*|index_dir = ${TMP_DIR}|" "$CONFIG_FILE"
else
    echo "index_dir = ${TMP_DIR}" >> "$CONFIG_FILE"
fi

echo "==> Running VHS demo (${LANG})..."
cd "$SCRIPT_DIR"
vhs "$TAPE"

OUTPUT_GIF="$SCRIPT_DIR/demo.gif"
if [ -f "$OUTPUT_GIF" ]; then
    echo "==> Done: $OUTPUT_GIF ($(du -h "$OUTPUT_GIF" | cut -f1))"
else
    echo "==> WARNING: $OUTPUT_GIF not found, check VHS output"
fi
