// kaydet-core — exp3.py'nin Rust karşılığı
//
// Mimari:
//   KaydetCore  — koordinatör, Storage'a yazar, hata olursa rollback
//   Storage     — trait, disk I/O (NativeStorage, MemoryStorage)
//   MemoryIndex — HashMap tabanlı in-memory index
//   SyncService — Storage observer, outbox + inbox yönetir
//   Command     — do/undo çiftleri, rollback mantığını taşır
//
// exp3.py'den farklar:
//   - async yok (Storage sync, CLI için yeterli)
//   - SyncService şimdilik stub — network impl arayüz katmanında
//   - originator_id, hop_path yok — sync server sorumluluğu

use std::collections::HashMap;
use std::sync::{Arc, Mutex};

pub mod filesystem;
pub mod merkle;
pub mod packet;

#[cfg(feature = "python")]
pub mod python;

// ---------------------------------------------------------------------------
// short_id
// ---------------------------------------------------------------------------

const BASE57: &[u8] = b"23456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz";

pub fn short_id() -> String {
    use std::time::{SystemTime, UNIX_EPOCH};
    // uuid bağımlılığı korunuyor — short_id için kullanıyoruz
    let t = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .subsec_nanos();
    // basit ama yeterli: nano + rastgele byte karışımı
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
    pub fn from_text(text: &str) -> Entry {
        let now = chrono::Local::now();
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
// Command — do/undo çiftleri
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
// StorageEvent — FileSystem'ın SyncService'e bildirdiği olaylar
// ---------------------------------------------------------------------------

pub enum StorageEvent {
    Created(Entry),
    Updated(Entry),
    Deleted(String),
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
// SyncService
// ---------------------------------------------------------------------------

pub struct SyncOutboxItem {
    pub op: &'static str,  // "created" | "updated" | "deleted"
    pub entry: Option<Entry>,
    pub entry_id: Option<String>,
}

pub struct SyncService {
    fail: bool,
    pub sent: Vec<SyncOutboxItem>,
    outbox: Vec<SyncOutboxItem>,
    inbox: Arc<Mutex<Vec<Entry>>>,
}

impl SyncService {
    pub fn new(fail: bool) -> Self {
        SyncService {
            fail,
            sent: Vec::new(),
            outbox: Vec::new(),
            inbox: Arc::new(Mutex::new(Vec::new())),
        }
    }

    pub fn inbox_handle(&self) -> Arc<Mutex<Vec<Entry>>> {
        Arc::clone(&self.inbox)
    }

    fn push(&mut self, item: SyncOutboxItem, label: &str) {
        if self.fail {
            println!("[SyncService] network unreachable, outbox -> {label}");
            self.outbox.push(item);
        } else {
            println!("[SyncService] pushed -> {label}");
            self.sent.push(item);
        }
    }

    pub fn on_event(&mut self, event: StorageEvent) {
        match event {
            StorageEvent::Created(entry) => {
                let label = format!("created:{}", entry.entry_id);
                self.push(SyncOutboxItem { op: "created", entry: Some(entry), entry_id: None }, &label);
            }
            StorageEvent::Updated(entry) => {
                let label = format!("updated:{}", entry.entry_id);
                self.push(SyncOutboxItem { op: "updated", entry: Some(entry), entry_id: None }, &label);
            }
            StorageEvent::Deleted(entry_id) => {
                let label = format!("deleted:{entry_id}");
                self.push(SyncOutboxItem { op: "deleted", entry: None, entry_id: Some(entry_id) }, &label);
            }
        }
    }

    pub fn retry(&mut self) {
        let pending = std::mem::take(&mut self.outbox);
        for item in pending {
            let label = match (&item.entry, &item.entry_id) {
                (Some(e), _) => format!("{}:{}", item.op, e.entry_id),
                (_, Some(id)) => format!("{}:{}", item.op, id),
                _ => item.op.to_string(),
            };
            println!("[SyncService] retry ok -> {label}");
            self.sent.push(item);
        }
    }

    pub fn deliver(&self, entry: Entry) {
        println!("[SyncService] inbox'a iletildi -> {}", entry.entry_id);
        self.inbox.lock().unwrap().push(entry);
    }

    pub fn outbox_len(&self) -> usize {
        self.outbox.len()
    }
}

// ---------------------------------------------------------------------------
// KaydetCore
// ---------------------------------------------------------------------------

pub struct KaydetCore {
    pub index: MemoryIndex,
    storage: Box<dyn StorageTrait>,
    sync: Option<Box<SyncService>>,
    inbox: Option<Arc<Mutex<Vec<Entry>>>>,
}

impl KaydetCore {
    pub fn new(storage: Box<dyn StorageTrait>, sync: Option<Box<SyncService>>) -> Self {
        let inbox = sync.as_ref().map(|s| s.inbox_handle());
        KaydetCore {
            index: MemoryIndex::new(),
            storage,
            sync,
            inbox,
        }
    }

    fn run(&mut self, cmd: Command, storage_op: impl FnOnce(&dyn StorageTrait) -> Result<(), String>) -> Result<(), String> {
        cmd.apply(&mut self.index);
        match storage_op(self.storage.as_ref()) {
            Ok(()) => Ok(()),
            Err(e) => {
                println!("[Core] storage error: {e} — rolling back");
                cmd.undo(&mut self.index);
                Err(e)
            }
        }
    }

    pub fn add_entry(&mut self, text: &str) -> Result<Entry, String> {
        let entry = Entry::from_text(text);
        let e = entry.clone();
        self.run(Command::Add { entry: entry.clone() }, |s| s.append(&e))?;
        if let Some(sync) = &mut self.sync {
            sync.on_event(StorageEvent::Created(entry.clone()));
        }
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
        if let Some(sync) = &mut self.sync {
            sync.on_event(StorageEvent::Updated(updated));
        }
        Ok(())
    }

    pub fn delete_entry(&mut self, entry_id: &str) -> Result<(), String> {
        let old = self.index.get(entry_id)
            .ok_or_else(|| format!("entry not found: {entry_id}"))?
            .clone();
        let id = entry_id.to_string();
        self.run(Command::Delete { old }, |s| s.delete(&id))?;
        if let Some(sync) = &mut self.sync {
            sync.on_event(StorageEvent::Deleted(entry_id.to_string()));
        }
        Ok(())
    }

    pub fn drain_inbox(&mut self) -> Vec<Entry> {
        let Some(inbox) = &self.inbox else { return vec![]; };
        let entries: Vec<Entry> = std::mem::take(&mut *inbox.lock().unwrap());
        for entry in &entries {
            println!("[Core] inbox'tan islendi -> {}", entry.entry_id);
            self.index.update(entry.clone());
        }
        entries
    }
}

// ---------------------------------------------------------------------------
// MemoryStorage  (test için)
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

    fn make_core(fail_on: Option<&'static str>, sync_fail: bool) -> (KaydetCore, Option<*mut SyncService>) {
        let sync = Box::new(SyncService::new(sync_fail));
        let core = KaydetCore::new(
            Box::new(MemoryStorage::new(fail_on)),
            Some(sync),
        );
        (core, None)
    }

    #[test]
    fn test_add_entry_normal() {
        let (mut core, _) = make_core(None, false);
        let entry = core.add_entry("bugun guzel bir gundi #mirat").unwrap();
        assert_eq!(core.index.all().len(), 1);
        assert!(core.index.get(&entry.entry_id).is_some());
    }

    #[test]
    fn test_add_entry_storage_fail_rollback() {
        let sync = Box::new(SyncService::new(false));
        let mut core = KaydetCore::new(Box::new(MemoryStorage::new(Some("append"))), Some(sync));
        let result = core.add_entry("bu kayit yazılamayacak");
        assert!(result.is_err());
        assert_eq!(core.index.all().len(), 0);
    }

    #[test]
    fn test_update_entry() {
        let (mut core, _) = make_core(None, false);
        let entry = core.add_entry("ilk metin #draft").unwrap();
        core.update_entry(&entry.entry_id, "guncellendi #final").unwrap();
        let updated = core.index.get(&entry.entry_id).unwrap();
        assert_eq!(updated.text, "guncellendi #final");
        assert_eq!(updated.tags, vec!["final"]);
    }

    #[test]
    fn test_delete_entry() {
        let (mut core, _) = make_core(None, false);
        let entry = core.add_entry("silinecek #test").unwrap();
        core.delete_entry(&entry.entry_id).unwrap();
        assert!(core.index.get(&entry.entry_id).is_none());
    }

    #[test]
    fn test_drain_inbox() {
        let sync = Box::new(SyncService::new(false));
        let inbox = sync.inbox_handle();
        let mut core = KaydetCore::new(Box::new(MemoryStorage::new(None)), Some(sync));

        let remote = Entry::from_text("baska cihazdan geldi #sync");
        inbox.lock().unwrap().push(remote.clone());

        assert_eq!(core.index.all().len(), 0);
        let applied = core.drain_inbox();
        assert_eq!(applied.len(), 1);
        assert_eq!(core.index.all().len(), 1);
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
}
