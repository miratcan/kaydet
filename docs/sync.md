# Cloud Sync

Kaydet separates storage (plain text files) from index (SQLite database), making cloud sync simple and safe.

## How it works

```
~/Documents/Kaydet/        → Synced (Google Drive, iCloud, Dropbox)
  ├── 2025-01-15.txt
  ├── 2025-01-16.txt
  └── ...

~/.local/share/kaydet/     → Local only (not synced)
  └── index.db
```

**Why this works:**
- Plain text files are the single source of truth
- Each device builds its own search index locally
- Sync conflicts don't happen because only plain text files are synchronized
- Zero infrastructure cost

## Setup for cloud sync

1. **First run** — Kaydet will ask where to store entries:
   ```bash
   kaydet "First entry"

   # Choose your cloud folder:
   Path: ~/Google Drive/Kaydet
   ```

2. **Change location later** — Edit config and migrate:
   ```bash
   kaydet --config

   # Edit storage_dir in your editor
   # Kaydet will offer to move files automatically
   ```

3. **On other devices** — Install Kaydet, set same folder:
   ```bash
   kaydet "First entry on phone"
   Path: ~/Google Drive/Kaydet  # Same path
   ```

## Supported cloud providers

- **Google Drive** (recommended for Android)
- **iCloud Drive** (recommended for iOS/macOS)
- **Dropbox** (cross-platform)
- **Any folder sync** (Syncthing, Resilio, etc.)

**Note:** Index is always local. Each device maintains its own `index.db` for fast search.
