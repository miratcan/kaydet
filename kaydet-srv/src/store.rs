// store.rs — ServerStore: kaydet-core + rusqlite per storage_dir
//
// Her storage_dir için:
//   - kaydet-core (KaydetCore) in-memory index
//   - SQLite (sync_log, sync_keys tabloları)

use std::path::PathBuf;
use std::sync::Mutex;

use rusqlite::Connection;

use kaydet_core_rs::{KaydetCore, Entry};

pub struct ServerStore {
    pub storage_dir: PathBuf,
    pub core: Mutex<KaydetCore>,
    pub db: Mutex<Connection>,
}

impl ServerStore {
    pub fn open(storage_dir: PathBuf) -> Result<Self, String> {
        // Rust core
        let core = open_core(&storage_dir)?;

        // SQLite
        let db_path = storage_dir.join("sync.db");
        let conn = Connection::open(&db_path)
            .map_err(|e| e.to_string())?;
        init_db(&conn).map_err(|e| e.to_string())?;

        Ok(ServerStore {
            storage_dir,
            core: Mutex::new(core),
            db: Mutex::new(conn),
        })
    }

    pub fn reload_core(&self) -> Result<(), String> {
        let new_core = open_core(&self.storage_dir)?;
        *self.core.lock().unwrap() = new_core;
        Ok(())
    }
}

fn open_core(storage_dir: &PathBuf) -> Result<KaydetCore, String> {
    use kaydet_core_rs::filesystem::{FileSystem, NativeFs};

    let fs = NativeFs::new(storage_dir.to_str().unwrap());
    let days = fs.list_days().map_err(|e| e.to_string())?;

    let storage = Box::new(SrvStorage {
        fs: NativeFs::new(storage_dir.to_str().unwrap()),
    });

    let existing: Vec<Entry> = days.iter()
        .flat_map(|day| {
            fs.read_day(day)
                .map(|content| parse_day(&content, day))
                .unwrap_or_default()
        })
        .collect();

    let mut core = KaydetCore::new(storage, None);
    for entry in existing {
        core.index.update(entry);
    }

    Ok(core)
}

// ---------------------------------------------------------------------------
// SrvStorage — NativeStorage equivalent for the server (no PyO3 dependency)
// ---------------------------------------------------------------------------

use kaydet_core_rs::filesystem::{FileSystem, NativeFs};
use kaydet_core_rs::StorageTrait;

struct SrvStorage {
    fs: NativeFs,
}

impl StorageTrait for SrvStorage {
    fn append(&self, entry: &Entry) -> Result<(), String> {
        let existing = self.fs.read_day(&entry.date).unwrap_or_default();
        let new_content = inject_entry(&existing, entry);
        self.fs.write_day(&entry.date, &new_content).map_err(|e| e.to_string())
    }

    fn replace(&self, entry: &Entry) -> Result<(), String> {
        let existing = self.fs.read_day(&entry.date).unwrap_or_default();
        let without = remove_entry_from_content(&existing, &entry.entry_id);
        let replaced = inject_entry(&without, entry);
        self.fs.write_day(&entry.date, &replaced).map_err(|e| e.to_string())
    }

    fn delete(&self, entry_id: &str) -> Result<(), String> {
        let days = self.fs.list_days().map_err(|e| e.to_string())?;
        for day in days {
            let content = self.fs.read_day(&day).unwrap_or_default();
            if content.contains(&format!("[{entry_id}]:")) {
                let new_content = remove_entry_from_content(&content, entry_id);
                self.fs.write_day(&day, &new_content).map_err(|e| e.to_string())?;
                return Ok(());
            }
        }
        Ok(())
    }

    fn load_all(&self) -> Result<Vec<Entry>, String> {
        let days = self.fs.list_days().map_err(|e| e.to_string())?;
        let mut entries = Vec::new();
        for day in days {
            let content = self.fs.read_day(&day).unwrap_or_default();
            for entry in parse_day(&content, &day) {
                entries.push(entry);
            }
        }
        Ok(entries)
    }
}

// ---------------------------------------------------------------------------
// Day file parsing + formatting (mirrors python.rs)
// ---------------------------------------------------------------------------

fn parse_day(content: &str, date: &str) -> Vec<Entry> {
    use kaydet_core_rs::{parse_attachments, parse_metadata, parse_tags};
    let mut entries: Vec<Entry> = Vec::new();

    for line in content.lines() {
        let trimmed = line.trim();
        if trimmed.starts_with('-') { continue; }
        if trimmed.is_empty() {
            if let Some(last) = entries.last_mut() { last.text.push('\n'); }
            continue;
        }

        let entry_id = extract_entry_id(trimmed);
        let timestamp = trimmed.split_whitespace().next().map(|s| s.to_string());

        if let (Some(entry_id), Some(timestamp)) = (entry_id, timestamp) {
            if timestamp.len() != 5 || timestamp.as_bytes().get(2) != Some(&b':') { continue; }
            let text = match trimmed.find("]: ") {
                Some(pos) => trimmed[pos + 3..].trim().to_string(),
                None => continue,
            };
            if text.is_empty() { continue; }
            entries.push(Entry {
                entry_id,
                date: date.to_string(),
                timestamp,
                tags: parse_tags(&text),
                metadata: parse_metadata(&text),
                attachments: parse_attachments(&text),
                text,
            });
        } else if let Some(last) = entries.last_mut() {
            last.text.push('\n');
            last.text.push_str(trimmed);
            last.tags = parse_tags(&last.text);
            last.metadata = parse_metadata(&last.text);
            last.attachments = parse_attachments(&last.text);
        }
    }
    entries
}

fn extract_entry_id(line: &str) -> Option<String> {
    let start = line.find('[')? + 1;
    let end = line.find(']')?;
    if end > start { Some(line[start..end].to_string()) } else { None }
}

fn format_entry(entry: &Entry) -> String {
    let mut lines = entry.text.lines();
    let first = lines.next().unwrap_or("");
    let header = format!("{} [{}]: {}\n", entry.timestamp, entry.entry_id, first);
    let rest: String = lines.map(|l| format!("{l}\n")).collect();
    header + &rest
}

fn inject_entry(content: &str, entry: &Entry) -> String {
    let new_line = format_entry(entry);
    let mut result = String::new();
    let mut inserted = false;

    for line in content.lines() {
        if !inserted {
            if let Some(ts) = line.split_whitespace().next() {
                if ts.len() == 5 && ts.as_bytes().get(2) == Some(&b':') {
                    if entry.timestamp.as_str() < ts {
                        result.push_str(&new_line);
                        inserted = true;
                    }
                }
            }
        }
        result.push_str(line);
        result.push('\n');
    }
    if !inserted { result.push_str(&new_line); }
    result
}

fn remove_entry_from_content(content: &str, entry_id: &str) -> String {
    let marker = format!("[{entry_id}]:");
    let mut result = String::new();
    let mut skip = false;

    for line in content.lines() {
        let is_header = line.split_whitespace().next()
            .map(|ts| ts.len() == 5 && ts.as_bytes().get(2) == Some(&b':'))
            .unwrap_or(false);

        if line.contains(&marker) { skip = true; continue; }
        if skip && is_header { skip = false; }
        if !skip { result.push_str(line); result.push('\n'); }
    }
    result
}

// ---------------------------------------------------------------------------
// SQLite schema
// ---------------------------------------------------------------------------

fn init_db(conn: &Connection) -> rusqlite::Result<()> {
    conn.execute_batch("PRAGMA journal_mode=WAL;")?;
    conn.execute_batch("
        CREATE TABLE IF NOT EXISTS sync_log (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_id  TEXT NOT NULL,
            action    TEXT NOT NULL,
            device_id TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS sync_keys (
            key        TEXT PRIMARY KEY,
            name       TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            last_used_at TEXT
        );
    ")?;
    Ok(())
}
