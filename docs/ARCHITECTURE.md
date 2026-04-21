# kaydet Architecture

|             |                    |
|-------------|--------------------|
| Version     | 0.1                |
| Status      | Draft              |
| Date        | 2026-04-21         |

## Principle

kaydet is a protocol, not an app. CLI, MCP, mobile, browser extensions — these
are all interfaces. The core is the same everywhere.

**[ZEN-DOOM]:** If Doom runs on it, kaydet runs on it. The core has zero fat
dependencies. Only byte reads, CRC32, UTF-8.

---

## Layer Model

```
┌─────────────────────────────────────────────────────┐
│                   Interfaces                        │
│  CLI (Python)  │  MCP Server  │  React Native  │ …  │
└────────────────────────┬────────────────────────────┘
                         │  kaydet_core_rs API
┌────────────────────────▼────────────────────────────┐
│                  kaydet-core (Rust)                 │
│                                                     │
│  Storage  │  MemoryIndex  │  Merkle  │  Secrets     │
└────────────────────────┬────────────────────────────┘
                         │  FileSystem trait
┌────────────────────────▼────────────────────────────┐
│                    Platform                         │
│  NativeFs (disk)  │  MemoryFs (test)  │  RNFs (…)   │
└─────────────────────────────────────────────────────┘
```

Interfaces call core. Core never calls interfaces. Platform I/O is injected
via trait — core never touches platform APIs directly.

---

## kaydet-core (Rust)

Source: `packages/kaydet-core/src/`

### Responsibilities

| Module | Responsibility |
|--------|---------------|
| `lib.rs` | Entry, KaydetCore, MemoryIndex, EventListener trait |
| `storage.rs` | Read/write day files, parse entry format |
| `merkle.rs` | Merkle tree for sync diff |
| `packet.rs` | Binary entry packet serialize/deserialize |
| `filesystem.rs` | FileSystem trait + NativeFs, MemoryFs |
| `python.rs` | PyO3 bindings (optional feature) |

### Entry

```
Entry {
    entry_id:     String       // 8-char base57 ShortUUID
    originator_id: String      // device that created this entry
    date:         String       // "YYYY-MM-DD" — which day file
    timestamp:    String       // "HH:MM"
    text:         String       // full body text
    tags:         Vec<String>  // extracted from #tag tokens
    metadata:     HashMap      // extracted from key:value tokens
    attachments:  Vec<String>  // extracted from attachment:filename tokens
    hop_path:     HashSet      // sync loop prevention
}
```

### MemoryIndex

Loaded at startup by reading all day files. No SQLite, no schema migrations.
109 days / ~500 entries loads in milliseconds.

Query methods:

| Method | Use case |
|--------|---------|
| `all()` | list all entries |
| `by_tag(tag)` | `#valocom` entries |
| `by_meta(key, value)` | `status:pending` → todo list |
| `by_date_range(since, until)` | date filter |
| `search_text(term)` | full-text search (case-insensitive contains) |
| `get(entry_id)` | single entry lookup |

### EventListener

KaydetCore broadcasts events to registered listeners. Listeners are
independent — order does not matter.

```
add_entry("bugün #mirat")
    → EntryCreated event
        ├── Storage      → writes to day file
        ├── MemoryIndex  → updates in-memory index
        └── SyncService  → sends to remote (if configured)
```

### FileSystem trait

```rust
trait FileSystem: Send + Sync {
    fn read_day(&self, date: &str) -> FsResult<String>;
    fn write_day(&self, date: &str, content: &str) -> FsResult<()>;
    fn list_days(&self) -> FsResult<Vec<String>>;
    // attachments …
}
```

Implementations: `NativeFs` (disk), `MemoryFs` (tests), `RNFs` (React Native, future).

### Secrets

`storage/secrets/{entry_id}.enc` — AES-256-GCM, key derived via scrypt.
Secret payload is separate from the entry text. Entry exists without its
secret; secret is an optional attachment.

Sync: encrypted blob syncs to server. Server never sees plaintext.
Devices that have the password can decrypt.

### Todo

Not a separate data type. A todo is an entry with:
- `#todo` tag
- `status:pending` metadata

Completing a todo: `update_entry` sets `status:done`, `completed_at:HH:MM`.
Listing todos: `index.by_meta("status", "pending")`.

---

## Interfaces

Interfaces use `kaydet_core_rs` (PyO3 binding) or the native Rust API.
They are responsible for:

- Argument parsing / routing
- Output formatting
- Platform-specific features (editor, notifications, HTTP transport)
- Sync transport (HTTP client/server)

### Python CLI + MCP

Source: `packages/core/`, `packages/mcp/`

Uses `kaydet_core_rs` via PyO3. Falls back to pure Python if Rust lib is
not available (transition period).

### React Native (future)

Embeds `kaydet-core` as a native module via Android NDK / iOS framework.
Same Rust binary, different FileSystem implementation.

### CLI binary (Rust, experimental)

Source: `packages/kaydet-core/src/main.rs`

Direct Rust CLI, no Python. Useful for embedded/server environments.

---

## Storage Layout

```
~/.local/share/kaydet/        (or --storage <path>)
  2026-04-21.txt              day files
  2026-04-22.txt
  attachments/
    kW3mJ8vq_photo.jpg        {entry_id}_{filename}
  secrets/
    kW3mJ8vq.enc              AES-256-GCM blobs
```

The index is never persisted. It is rebuilt from day files at startup.

---

## What Core Does NOT Do

- HTTP requests
- Push notifications
- Open `$EDITOR`
- Render output (colors, tables)
- Store config (storage path, device ID, server URL)

These belong to the interface layer.
