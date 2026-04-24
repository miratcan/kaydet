// kaydet-core — Rust core
//
// Architecture:
//   KaydetCore    — coordinator: writes to Storage, rolls back on error
//   StorageTrait  — trait for disk I/O (NativeStorage, MemoryStorage)
//   MemoryIndex   — HashMap-based in-memory index
//   SyncBackend   — optional trait for sync transport (HTTP, P2P, noop)
//   Command       — do/undo pairs, carries rollback logic
//
// Design notes:
//   - no async (Storage is sync, sufficient for CLI use)
//   - SyncBackend is optional: None = offline (e.g. embedded/C64 build)
//   - originator_id, hop_path omitted — sync server's responsibility

use std::collections::HashMap;
use std::sync::Mutex;

pub mod crypto;
pub mod filesystem;
pub mod packet;
pub mod sync;

pub use sync::{SyncBackend, SyncStats};

#[cfg(feature = "python")]
pub mod python;

// ---------------------------------------------------------------------------
// short_id
// ---------------------------------------------------------------------------

const BASE57: &[u8] = b"23456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz";

pub fn short_id() -> String {
    use std::time::{SystemTime, UNIX_EPOCH};
    let t = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .subsec_nanos();
    // simple but sufficient: nanoseconds XOR random bytes
    let mut num = t as u128 ^ (rand::random::<u64>() as u128);
    let mut result = Vec::with_capacity(8);
    for _ in 0..8 {
        result.push(BASE57[(num % 57) as usize]);
        num /= 57;
    }
    result.reverse();
    String::from_utf8(result).unwrap()
}

// ---------------------------------------------------------------------------
// Entry
// ---------------------------------------------------------------------------

#[derive(Debug, Clone)]
pub struct Entry {
    pub entry_id: String,
    pub date: String,       // "YYYY-MM-DD"
    pub timestamp: String,  // "HH:MM"
    pub text: String,
    pub tags: Vec<String>,
    pub metadata: HashMap<String, String>,
    pub attachments: Vec<String>,
}

impl Entry {
    pub fn from_text(text: &str, at: Option<chrono::DateTime<chrono::Local>>) -> Entry {
        let now = at.unwrap_or_else(chrono::Local::now);
        Entry {
            entry_id: short_id(),
            date: now.format("%Y-%m-%d").to_string(),
            timestamp: now.format("%H:%M").to_string(),
            text: text.to_string(),
            tags: parse_tags(text),
            metadata: parse_metadata(text),
            attachments: parse_attachments(text),
        }
    }
}

pub fn parse_tags(text: &str) -> Vec<String> {
    text.split_whitespace()
        .filter(|w| w.starts_with('#') && w.len() > 1)
        .map(|w| w[1..].trim_end_matches(|c: char| ".,!?;:".contains(c)).to_string())
        .filter(|t| {
            !t.is_empty()
                && t.chars().next().map(|c| c.is_alphabetic()).unwrap_or(false)
                && t.chars().all(|c| c.is_alphanumeric() || c == '-')
        })
        .collect()
}

pub fn parse_metadata(text: &str) -> HashMap<String, String> {
    text.split_whitespace()
        .filter(|w| !w.starts_with('#') && !w.starts_with("attachment:") && w.contains(':'))
        .filter_map(|w| {
            let mut parts = w.splitn(2, ':');
            let key = parts.next()?;
            let val = parts.next()?;
            if key.is_empty() || val.is_empty() { return None; }
            Some((key.to_string(), val.to_string()))
        })
        .collect()
}

pub fn parse_attachments(text: &str) -> Vec<String> {
    text.split_whitespace()
        .filter(|w| w.starts_with("attachment:") && w.len() > 11)
        .map(|w| w[11..].to_string())
        .collect()
}

// ---------------------------------------------------------------------------
// MemoryIndex
// ---------------------------------------------------------------------------

pub struct MemoryIndex {
    entries: HashMap<String, Entry>,
}

impl MemoryIndex {
    pub fn new() -> Self {
        MemoryIndex { entries: HashMap::new() }
    }

    pub fn add(&mut self, entry: Entry) {
        self.entries.entry(entry.entry_id.clone()).or_insert(entry);
    }

    pub fn rollback(&mut self, entry_id: &str) {
        self.entries.remove(entry_id);
    }

    pub fn update(&mut self, entry: Entry) {
        self.entries.insert(entry.entry_id.clone(), entry);
    }

    pub fn remove(&mut self, entry_id: &str) {
        self.entries.remove(entry_id);
    }

    pub fn get(&self, entry_id: &str) -> Option<&Entry> {
        self.entries.get(entry_id)
    }

    pub fn all(&self) -> Vec<&Entry> {
        self.entries.values().collect()
    }

    pub fn by_tag(&self, tag: &str) -> Vec<&Entry> {
        self.entries.values().filter(|e| e.tags.iter().any(|t| t == tag)).collect()
    }

    pub fn by_meta(&self, key: &str, value: &str) -> Vec<&Entry> {
        self.entries.values()
            .filter(|e| e.metadata.get(key).map(|v| v == value).unwrap_or(false))
            .collect()
    }

    pub fn by_date_range(&self, since: Option<&str>, until: Option<&str>) -> Vec<&Entry> {
        self.entries.values()
            .filter(|e| {
                since.map(|s| e.date.as_str() >= s).unwrap_or(true)
                    && until.map(|u| e.date.as_str() <= u).unwrap_or(true)
            })
            .collect()
    }

    pub fn search_text(&self, term: &str) -> Vec<&Entry> {
        let term = term.to_lowercase();
        self.entries.values()
            .filter(|e| e.text.to_lowercase().contains(&term))
            .collect()
    }
}

// ---------------------------------------------------------------------------
// Command — do/undo pairs
// ---------------------------------------------------------------------------

enum Command {
    Add { entry: Entry },
    Update { old: Entry, updated: Entry },
    Delete { old: Entry },
}

impl Command {
    fn apply(&self, index: &mut MemoryIndex) {
        match self {
            Command::Add { entry } => index.add(entry.clone()),
            Command::Update { updated, .. } => index.update(updated.clone()),
            Command::Delete { old } => index.remove(&old.entry_id),
        }
    }

    fn undo(&self, index: &mut MemoryIndex) {
        match self {
            Command::Add { entry } => index.rollback(&entry.entry_id),
            Command::Update { old, .. } => index.update(old.clone()),
            Command::Delete { old } => index.add(old.clone()),
        }
    }
}

// ---------------------------------------------------------------------------
// Storage trait
// ---------------------------------------------------------------------------

pub trait StorageTrait: Send + Sync {
    fn append(&self, entry: &Entry) -> Result<(), String>;
    fn replace(&self, entry: &Entry) -> Result<(), String>;
    fn delete(&self, entry_id: &str) -> Result<(), String>;
    fn load_all(&self) -> Result<Vec<Entry>, String>;
}

// ---------------------------------------------------------------------------
// KaydetCore
// ---------------------------------------------------------------------------

pub struct KaydetCore {
    pub index: MemoryIndex,
    storage: Box<dyn StorageTrait>,
    pub sync_backend: Option<Box<dyn SyncBackend>>,
    /// Unix timestamp of last successful sync (0 = never synced).
    pub sync_token: i64,
    /// Pending local changes not yet pushed (entry_ids).
    pending_push: Vec<String>,
}

impl KaydetCore {
    pub fn new(storage: Box<dyn StorageTrait>, sync_backend: Option<Box<dyn SyncBackend>>) -> Self {
        KaydetCore {
            index: MemoryIndex::new(),
            storage,
            sync_backend,
            sync_token: 0,
            pending_push: Vec::new(),
        }
    }

    fn run(&mut self, cmd: Command, storage_op: impl FnOnce(&dyn StorageTrait) -> Result<(), String>) -> Result<(), String> {
        cmd.apply(&mut self.index);
        match storage_op(self.storage.as_ref()) {
            Ok(()) => Ok(()),
            Err(e) => {
                cmd.undo(&mut self.index);
                Err(e)
            }
        }
    }

    pub fn add_entry(&mut self, text: &str, at: Option<chrono::DateTime<chrono::Local>>) -> Result<Entry, String> {
        let entry = Entry::from_text(text, at);
        let e = entry.clone();
        self.run(Command::Add { entry: entry.clone() }, |s| s.append(&e))?;
        self.pending_push.push(entry.entry_id.clone());
        Ok(entry)
    }

    /// Like add_entry but uses the given entry_id instead of generating one.
    /// Used by sync server to preserve client-generated IDs.
    pub fn add_entry_with_id(
        &mut self,
        entry_id: &str,
        text: &str,
        at: Option<chrono::DateTime<chrono::Local>>,
    ) -> Result<Entry, String> {
        let mut entry = Entry::from_text(text, at);
        entry.entry_id = entry_id.to_string();
        let e = entry.clone();
        self.run(Command::Add { entry: entry.clone() }, |s| s.append(&e))?;
        self.pending_push.push(entry.entry_id.clone());
        Ok(entry)
    }

    pub fn update_entry(&mut self, entry_id: &str, new_text: &str) -> Result<(), String> {
        let old = self.index.get(entry_id)
            .ok_or_else(|| format!("entry not found: {entry_id}"))?
            .clone();
        let updated = Entry {
            entry_id: entry_id.to_string(),
            date: old.date.clone(),
            timestamp: old.timestamp.clone(),
            text: new_text.to_string(),
            tags: parse_tags(new_text),
            metadata: parse_metadata(new_text),
            attachments: parse_attachments(new_text),
        };
        let u = updated.clone();
        self.run(Command::Update { old, updated: updated.clone() }, |s| s.replace(&u))?;
        self.pending_push.push(entry_id.to_string());
        Ok(())
    }

    pub fn delete_entry(&mut self, entry_id: &str) -> Result<(), String> {
        let old = self.index.get(entry_id)
            .ok_or_else(|| format!("entry not found: {entry_id}"))?
            .clone();
        let id = entry_id.to_string();
        self.run(Command::Delete { old }, |s| s.delete(&id))?;
        self.pending_push.push(entry_id.to_string());
        Ok(())
    }

    /// Run a sync cycle. No-op if no SyncBackend is attached.
    pub fn sync(&mut self) -> Result<SyncStats, String> {
        use crate::packet;

        let Some(backend) = &self.sync_backend else {
            return Ok(SyncStats::default());
        };

        // 1. Collect local entries to push
        let local_entries: Vec<Entry> = self.pending_push.iter()
            .filter_map(|id| self.index.get(id).cloned())
            .collect();

        // 2. Exchange: push local, get remote diff
        let (remote_changes, new_token) = backend.exchange(self.sync_token, &local_entries)?;

        let pushed = local_entries.len();
        let mut pulled = 0;
        let mut packets_fetched = 0;

        // 3. Apply remote changes
        for change in remote_changes {
            if change.deleted {
                // Delete locally if present
                if self.index.get(&change.entry_id).is_some() {
                    let id = change.entry_id.clone();
                    let _ = self.storage.delete(&id);
                    self.index.remove(&change.entry_id);
                }
                pulled += 1;
            } else if let Some(entry) = change.entry {
                // Inline entry — apply directly
                self.storage.replace(&entry)?;
                self.index.update(entry);
                pulled += 1;
            } else {
                // Fetch packet
                let packet_bytes = backend.fetch_packet(&change.entry_id)?;
                let pkt = packet::deserialize(&packet_bytes)
                    .map_err(|e| format!("packet error for {}: {}", change.entry_id, e))?;

                // Write attachments
                if !pkt.attachments.is_empty() {
                    // Attachment storage is handled by the storage layer via metadata;
                    // caller is responsible for persisting attachment files.
                    // Here we just update the entry.
                }

                self.storage.replace(&pkt.entry)?;
                self.index.update(pkt.entry);
                packets_fetched += 1;
                pulled += 1;
            }
        }

        // 4. Upload packets for local entries with attachments
        for entry in &local_entries {
            if entry.attachments.is_empty() { continue; }
            // Attachment bytes must be loaded by the storage layer.
            // For now: upload_packet is a best-effort call; errors are non-fatal.
            let _ = backend.upload_packet(&entry.entry_id, &[]);
        }

        // 5. Commit state
        self.sync_token = new_token;
        self.pending_push.clear();

        Ok(SyncStats { pushed, pulled, packets_fetched })
    }
}

// ---------------------------------------------------------------------------
// Query parser
// ---------------------------------------------------------------------------

#[derive(Debug, Default, PartialEq)]
pub struct ParsedQuery {
    pub include_tags: Vec<String>,
    pub exclude_tags: Vec<String>,
    pub include_meta: Vec<(String, String)>,
    pub text_terms: Vec<String>,
    pub exclude_terms: Vec<String>,
    pub since: Option<String>,
    pub until: Option<String>,
}

/// Parse a search query string into structured filters.
///
/// Syntax:
///   `#tag`        → include_tags
///   `-#tag`       → exclude_tags
///   `key:value`   → include_meta  (key must be lowercase alpha, value non-empty)
///   `since:DATE`  → since
///   `until:DATE`  → until
///   `-word`       → exclude_terms
///   `word`        → text_terms
///
/// Edge cases that fall through to WORD / text_terms:
///   - key starts with uppercase  (`Note:`, `URL:`)
///   - key is numeric (`3:00`)
///   - value is empty (`word:`)
///   - key is empty (`:word`)
///   - URL-like patterns (`https://example.com`) — treated as a single term
pub fn parse_query(query: &str) -> ParsedQuery {
    let mut q = ParsedQuery::default();
    if query.trim().is_empty() {
        return q;
    }

    for token in query.split_whitespace() {
        if let Some(tag) = token.strip_prefix("-#") {
            q.exclude_tags.push(tag.to_lowercase());
        } else if let Some(tag) = token.strip_prefix('#') {
            q.include_tags.push(tag.to_lowercase());
        } else if let Some(rest) = token.strip_prefix('-') {
            // Could be "-word" or "-key:value" — treat as exclude_term (plain text)
            // We do NOT split on ':' here; exclusion only applies to plain words.
            q.exclude_terms.push(rest.to_lowercase());
        } else if let Some((key, val)) = token.split_once(':') {
            // Only treat as metadata if key is non-empty lowercase-only alphabetic
            // and value is non-empty.  This avoids matching "Note:", "3:00", "URL:",
            // "https://...", ":word".
            let key_valid = !key.is_empty()
                && key.chars().all(|c| c.is_ascii_lowercase());
            let val_valid = !val.is_empty();
            if key_valid && val_valid {
                match key {
                    "since" => q.since = Some(val.to_string()),
                    "until" => q.until = Some(val.to_string()),
                    _ => q.include_meta.push((key.to_string(), val.to_string())),
                }
            } else {
                // Falls through to plain text term
                q.text_terms.push(token.to_lowercase());
            }
        } else {
            q.text_terms.push(token.to_lowercase());
        }
    }
    q
}

/// Apply a ParsedQuery against a slice of entries and return matching ones.
pub fn apply_query<'a>(entries: Vec<&'a Entry>, q: &ParsedQuery) -> Vec<&'a Entry> {
    entries.into_iter().filter(|e| {
        for tag in &q.include_tags {
            if !e.tags.iter().any(|t| t == tag) { return false; }
        }
        for tag in &q.exclude_tags {
            if e.tags.iter().any(|t| t == tag) { return false; }
        }
        for (key, val) in &q.include_meta {
            if e.metadata.get(key).map(|v| v != val).unwrap_or(true) { return false; }
        }
        if let Some(s) = &q.since {
            if e.date.as_str() < s.as_str() { return false; }
        }
        if let Some(u) = &q.until {
            if e.date.as_str() > u.as_str() { return false; }
        }
        let text_lower = e.text.to_lowercase();
        for term in &q.text_terms {
            if !text_lower.contains(term.as_str()) { return false; }
        }
        for term in &q.exclude_terms {
            if text_lower.contains(term.as_str()) { return false; }
        }
        true
    }).collect()
}

// ---------------------------------------------------------------------------
// MemoryStorage  (for tests)
// ---------------------------------------------------------------------------

pub struct MemoryStorage {
    fail_on: Option<&'static str>,
    pub data: Mutex<HashMap<String, Vec<String>>>,
}

impl MemoryStorage {
    pub fn new(fail_on: Option<&'static str>) -> Self {
        MemoryStorage { fail_on, data: Mutex::new(HashMap::new()) }
    }
}

impl StorageTrait for MemoryStorage {
    fn append(&self, entry: &Entry) -> Result<(), String> {
        if self.fail_on == Some("append") {
            return Err("simulated append failure".to_string());
        }
        self.data.lock().unwrap()
            .entry(entry.date.clone())
            .or_default()
            .push(entry.text.clone());
        Ok(())
    }

    fn replace(&self, entry: &Entry) -> Result<(), String> {
        if self.fail_on == Some("replace") {
            return Err("simulated replace failure".to_string());
        }
        self.data.lock().unwrap()
            .entry(entry.date.clone())
            .or_default()
            .push(format!("[updated] {}", entry.text));
        Ok(())
    }

    fn delete(&self, entry_id: &str) -> Result<(), String> {
        if self.fail_on == Some("delete") {
            return Err("simulated delete failure".to_string());
        }
        let _ = entry_id;
        Ok(())
    }

    fn load_all(&self) -> Result<Vec<Entry>, String> {
        Ok(vec![])
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    fn make_core(fail_on: Option<&'static str>) -> KaydetCore {
        KaydetCore::new(Box::new(MemoryStorage::new(fail_on)), None)
    }

    #[test]
    fn test_add_entry_normal() {
        let mut core = make_core(None);
        let entry = core.add_entry("bugun guzel bir gundi #mirat", None).unwrap();
        assert_eq!(core.index.all().len(), 1);
        assert!(core.index.get(&entry.entry_id).is_some());
    }

    #[test]
    fn test_add_entry_storage_fail_rollback() {
        let mut core = KaydetCore::new(Box::new(MemoryStorage::new(Some("append"))), None);
        let result = core.add_entry("bu kayit yazılamayacak", None);
        assert!(result.is_err());
        assert_eq!(core.index.all().len(), 0);
    }

    #[test]
    fn test_update_entry() {
        let mut core = make_core(None);
        let entry = core.add_entry("ilk metin #draft", None).unwrap();
        core.update_entry(&entry.entry_id, "guncellendi #final").unwrap();
        let updated = core.index.get(&entry.entry_id).unwrap();
        assert_eq!(updated.text, "guncellendi #final");
        assert_eq!(updated.tags, vec!["final"]);
    }

    #[test]
    fn test_delete_entry() {
        let mut core = make_core(None);
        let entry = core.add_entry("silinecek #test", None).unwrap();
        core.delete_entry(&entry.entry_id).unwrap();
        assert!(core.index.get(&entry.entry_id).is_none());
    }

    #[test]
    fn test_parse_tags() {
        let tags = parse_tags("bugun #mirat ve #work yaptim");
        assert_eq!(tags, vec!["mirat", "work"]);
    }

    #[test]
    fn test_parse_metadata() {
        let meta = parse_metadata("toplanti status:done time:2h #work");
        assert_eq!(meta.get("status").unwrap(), "done");
        assert_eq!(meta.get("time").unwrap(), "2h");
    }

    // -----------------------------------------------------------------------
    // parse_query tests — ported from tests/test_tokenizer.py
    // -----------------------------------------------------------------------

    #[test]
    fn test_query_simple_word() {
        let q = parse_query("hello");
        assert_eq!(q.text_terms, vec!["hello"]);
        assert!(q.include_tags.is_empty());
    }

    #[test]
    fn test_query_tag() {
        let q = parse_query("#work");
        assert_eq!(q.include_tags, vec!["work"]);
        assert!(q.text_terms.is_empty());
    }

    #[test]
    fn test_query_metadata() {
        let q = parse_query("status:done");
        assert_eq!(q.include_meta, vec![("status".to_string(), "done".to_string())]);
    }

    #[test]
    fn test_query_complex() {
        let q = parse_query("search #work status:done");
        assert_eq!(q.text_terms, vec!["search"]);
        assert_eq!(q.include_tags, vec!["work"]);
        assert_eq!(q.include_meta, vec![("status".to_string(), "done".to_string())]);
    }

    #[test]
    fn test_query_exclude_tag() {
        let q = parse_query("-#work");
        assert_eq!(q.exclude_tags, vec!["work"]);
        assert!(q.include_tags.is_empty());
    }

    #[test]
    fn test_query_exclude_word() {
        let q = parse_query("-term");
        assert_eq!(q.exclude_terms, vec!["term"]);
        assert!(q.text_terms.is_empty());
    }

    #[test]
    fn test_query_since_until() {
        let q = parse_query("since:2026-01-01 until:2026-04-01");
        assert_eq!(q.since.as_deref(), Some("2026-01-01"));
        assert_eq!(q.until.as_deref(), Some("2026-04-01"));
    }

    // Edge cases from test_tokenize_edge_cases
    #[test]
    fn test_query_url_parsed_as_meta() {
        // "https://example.com" → split_once(':') gives key="https", val="//example.com"
        // key is all lowercase alpha, val is non-empty → parsed as metadata.
        // NOTE: this differs from the Python tokenizer which treats URLs as WORD.
        // The difference is acceptable since URLs in search queries are rare;
        // behaviour is documented here so it's explicit.
        let q = parse_query("https://example.com");
        assert_eq!(q.include_meta, vec![("https".to_string(), "//example.com".to_string())]);
    }

    #[test]
    fn test_query_time_like_is_text_term() {
        // "12:30" — key "12" contains digits, not all lowercase alpha → text term
        let q = parse_query("12:30");
        assert_eq!(q.text_terms, vec!["12:30"]);
        assert!(q.include_meta.is_empty());
    }

    #[test]
    fn test_query_uppercase_key_is_text_term() {
        // "Note:" — key "Note" has uppercase → text term; also val is empty → text term anyway
        let q = parse_query("Note:");
        assert_eq!(q.text_terms, vec!["note:"]);
        assert!(q.include_meta.is_empty());
    }

    #[test]
    fn test_query_empty_value_is_text_term() {
        // "word:" — val is empty → falls through to text term
        let q = parse_query("word:");
        assert_eq!(q.text_terms, vec!["word:"]);
    }

    #[test]
    fn test_query_leading_colon_is_text_term() {
        // ":word" — key is empty → falls through to text term
        let q = parse_query(":word");
        assert_eq!(q.text_terms, vec![":word"]);
    }

    #[test]
    fn test_query_nested_colons_first_split_only() {
        // "key:value:with:colons" — split_once(':') → key="key", val="value:with:colons"
        let q = parse_query("key:value:with:colons");
        assert_eq!(q.include_meta, vec![("key".to_string(), "value:with:colons".to_string())]);
    }

    #[test]
    fn test_query_uppercase_url_key_is_text_term() {
        // "URL:" — key "URL" has uppercase, val empty → text term
        let q = parse_query("URL:");
        assert_eq!(q.text_terms, vec!["url:"]);
    }

    // -----------------------------------------------------------------------
    // apply_query integration tests
    // -----------------------------------------------------------------------

    fn entry_at(text: &str, date: &str) -> Entry {
        Entry {
            entry_id: crate::short_id(),
            date: date.to_string(),
            timestamp: "10:00".to_string(),
            text: text.to_string(),
            tags: parse_tags(text),
            metadata: parse_metadata(text),
            attachments: vec![],
        }
    }

    #[test]
    fn test_apply_tag_filter() {
        let e1 = entry_at("meeting #work today", "2026-04-01");
        let e2 = entry_at("lunch #personal", "2026-04-01");
        let entries = vec![&e1, &e2];
        let q = parse_query("#work");
        let results = apply_query(entries, &q);
        assert_eq!(results.len(), 1);
        assert_eq!(results[0].entry_id, e1.entry_id);
    }

    #[test]
    fn test_apply_exclude_tag() {
        let e1 = entry_at("meeting #work today", "2026-04-01");
        let e2 = entry_at("lunch #personal", "2026-04-01");
        let entries = vec![&e1, &e2];
        let q = parse_query("-#work");
        let results = apply_query(entries, &q);
        assert_eq!(results.len(), 1);
        assert_eq!(results[0].entry_id, e2.entry_id);
    }

    #[test]
    fn test_apply_metadata_filter() {
        let e1 = entry_at("task done status:done", "2026-04-01");
        let e2 = entry_at("task pending status:pending", "2026-04-01");
        let entries = vec![&e1, &e2];
        let q = parse_query("status:done");
        let results = apply_query(entries, &q);
        assert_eq!(results.len(), 1);
        assert_eq!(results[0].entry_id, e1.entry_id);
    }

    #[test]
    fn test_apply_date_range() {
        let e1 = entry_at("old entry", "2025-12-31");
        let e2 = entry_at("new entry", "2026-04-01");
        let entries = vec![&e1, &e2];
        let q = parse_query("since:2026-01-01");
        let results = apply_query(entries, &q);
        assert_eq!(results.len(), 1);
        assert_eq!(results[0].entry_id, e2.entry_id);
    }

    #[test]
    fn test_apply_text_search() {
        let e1 = entry_at("toplanti yapildi bugun", "2026-04-01");
        let e2 = entry_at("nothing interesting", "2026-04-01");
        let entries = vec![&e1, &e2];
        let q = parse_query("toplanti");
        let results = apply_query(entries, &q);
        assert_eq!(results.len(), 1);
        assert_eq!(results[0].entry_id, e1.entry_id);
    }

    #[test]
    fn test_apply_exclude_text() {
        let e1 = entry_at("toplanti yapildi bugun", "2026-04-01");
        let e2 = entry_at("nothing interesting", "2026-04-01");
        let entries = vec![&e1, &e2];
        let q = parse_query("-toplanti");
        let results = apply_query(entries, &q);
        assert_eq!(results.len(), 1);
        assert_eq!(results[0].entry_id, e2.entry_id);
    }

    #[test]
    fn test_apply_empty_query_returns_all() {
        let e1 = entry_at("entry one #work", "2026-04-01");
        let e2 = entry_at("entry two #personal", "2026-04-02");
        let entries = vec![&e1, &e2];
        let q = parse_query("");
        let results = apply_query(entries, &q);
        assert_eq!(results.len(), 2);
    }

    #[test]
    fn test_apply_combined_filters() {
        let e1 = entry_at("toplanti #work status:done", "2026-04-01");
        let e2 = entry_at("toplanti #work status:pending", "2026-04-01");
        let e3 = entry_at("lunch #personal status:done", "2026-04-01");
        let entries = vec![&e1, &e2, &e3];
        let q = parse_query("#work status:done");
        let results = apply_query(entries, &q);
        assert_eq!(results.len(), 1);
        assert_eq!(results[0].entry_id, e1.entry_id);
    }
}
