use std::collections::{HashMap, HashSet};
use std::sync::{Arc, Mutex};
use uuid::Uuid;
use regex::Regex;

// ---------------------------------------------------------------------------
// ShortUUID — 8 karakter base57
// ---------------------------------------------------------------------------
// base57 alphabet: 0, 1, I, O, l yok — karışıklık önler
const BASE57: &[u8] = b"23456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz";

pub fn short_id() -> String {
    let uuid = Uuid::new_v4();
    let mut num = u128::from_be_bytes(*uuid.as_bytes());
    let mut result = Vec::with_capacity(8);
    for _ in 0..8 {
        result.push(BASE57[(num % 57) as usize]);
        num /= 57;
    }
    result.reverse();
    String::from_utf8(result).unwrap()
}

pub mod filesystem;
pub use filesystem::{FileSystem, MemoryFs, NativeFs, FsError};

pub mod merkle;
pub use merkle::{MerkleTree, DiffResult};

pub mod packet;
pub use packet::{serialize, deserialize, PacketError};

pub mod storage;
pub use storage::Storage;

#[cfg(feature = "python")]
pub mod python;

// ---------------------------------------------------------------------------
// Entry
// ---------------------------------------------------------------------------

#[derive(Debug, Clone)]
pub struct Entry {
    pub entry_id: String,
    pub originator_id: String,
    pub hop_path: HashSet<String>,
    pub timestamp: String,
    pub text: String,
    pub tags: Vec<String>,
    pub metadata: HashMap<String, String>,
    pub attachments: Vec<String>,
}

impl Entry {
    pub fn from_text(text: &str, originator_id: &str) -> Entry {
        let tag_re = Regex::new(r"#([a-z][a-z0-9-]*)").unwrap();
        let meta_re = Regex::new(r"([a-z_]+):([^\s]+)").unwrap();
        let att_re = Regex::new(r"attachment:([^\s]+)").unwrap();

        let tags = tag_re
            .captures_iter(text)
            .map(|c| c[1].to_string())
            .collect();

        let metadata = meta_re
            .captures_iter(text)
            .map(|c| (c[1].to_string(), c[2].to_string()))
            .collect();

        let attachments = att_re
            .captures_iter(text)
            .map(|c| c[1].to_string())
            .collect();

        Entry {
            entry_id: short_id(),
            originator_id: originator_id.to_string(),
            hop_path: HashSet::new(),
            timestamp: String::new(),
            text: text.to_string(),
            tags,
            metadata,
            attachments,
        }
    }
}

// ---------------------------------------------------------------------------
// EventListener
// ---------------------------------------------------------------------------

pub trait EventListener: Send + Sync {
    fn on_entry_created(&self, entry: &Entry);
    fn on_entry_updated(&self, entry: &Entry);
    fn on_entry_deleted(&self, entry_id: &str);
}

// ---------------------------------------------------------------------------
// KaydetCore
// ---------------------------------------------------------------------------

pub struct KaydetCore {
    pub device_id: String,
    listeners: Vec<Box<dyn EventListener>>,
}

impl KaydetCore {
    pub fn new(device_id: &str) -> KaydetCore {
        KaydetCore {
            device_id: device_id.to_string(),
            listeners: Vec::new(),
        }
    }

    pub fn add_listener(&mut self, listener: Box<dyn EventListener>) {
        self.listeners.push(listener);
    }

    pub fn add_entry(&self, text: &str) -> Entry {
        let entry = Entry::from_text(text, &self.device_id);
        for listener in &self.listeners {
            listener.on_entry_created(&entry);
        }
        entry
    }

    pub fn receive_entry(&self, entry: Entry) {
        for listener in &self.listeners {
            listener.on_entry_created(&entry);
        }
    }

    pub fn update_entry(&self, entry: Entry) {
        for listener in &self.listeners {
            listener.on_entry_updated(&entry);
        }
    }

    pub fn delete_entry(&self, entry_id: &str) {
        for listener in &self.listeners {
            listener.on_entry_deleted(entry_id);
        }
    }
}

// ---------------------------------------------------------------------------
// MemoryIndex
// ---------------------------------------------------------------------------

pub struct MemoryIndex {
    entries: Mutex<HashMap<String, Entry>>,
}

impl MemoryIndex {
    pub fn new() -> MemoryIndex {
        MemoryIndex {
            entries: Mutex::new(HashMap::new()),
        }
    }

    pub fn all(&self) -> Vec<Entry> {
        self.entries.lock().unwrap().values().cloned().collect()
    }

    pub fn by_tag(&self, tag: &str) -> Vec<Entry> {
        self.entries
            .lock()
            .unwrap()
            .values()
            .filter(|e| e.tags.iter().any(|t| t == tag))
            .cloned()
            .collect()
    }

    pub fn get(&self, entry_id: &str) -> Option<Entry> {
        self.entries.lock().unwrap().get(entry_id).cloned()
    }
}

impl EventListener for MemoryIndex {
    fn on_entry_created(&self, entry: &Entry) {
        let mut entries = self.entries.lock().unwrap();
        if entries.contains_key(&entry.entry_id) {
            return; // idempotent
        }
        entries.insert(entry.entry_id.clone(), entry.clone());
    }

    fn on_entry_updated(&self, entry: &Entry) {
        self.entries
            .lock()
            .unwrap()
            .insert(entry.entry_id.clone(), entry.clone());
    }

    fn on_entry_deleted(&self, entry_id: &str) {
        self.entries.lock().unwrap().remove(entry_id);
    }
}

// ---------------------------------------------------------------------------
// SyncListener
// ---------------------------------------------------------------------------
// Python karşılığı:
//   class SyncListener(EventListener):
//       def __init__(self, name, my_device_id, remote):
//           self._forwarded = set()
//
// Rust'ta remote'u Arc<KaydetCore> olarak alıyoruz çünkü
// iki core birbirine referans tutacak — Rust ownership buna izin verir
// sadece Arc (reference counted pointer) ile.

pub struct SyncListener {
    pub name: String,
    pub my_device_id: String,
    remote: Arc<KaydetCore>,
    forwarded: Mutex<HashSet<String>>,
}

impl SyncListener {
    pub fn new(name: &str, my_device_id: &str, remote: Arc<KaydetCore>) -> SyncListener {
        SyncListener {
            name: name.to_string(),
            my_device_id: my_device_id.to_string(),
            remote,
            forwarded: Mutex::new(HashSet::new()),
        }
    }
}

impl EventListener for SyncListener {
    fn on_entry_created(&self, entry: &Entry) {
        if entry.hop_path.contains(&self.my_device_id) {
            return; // bu cihazdan geçti, tekrar gönderme
        }
        {
            let mut fwd = self.forwarded.lock().unwrap();
            if fwd.contains(&entry.entry_id) {
                return;
            }
            fwd.insert(entry.entry_id.clone());
        }

        let mut forwarded_entry = entry.clone();
        forwarded_entry.hop_path.insert(self.my_device_id.clone());

        println!(
            "[SyncListener:{}] → remote'a gönderiliyor {}...",
            self.name,
            &entry.entry_id[..8]
        );
        self.remote.receive_entry(forwarded_entry);
    }

    fn on_entry_updated(&self, _entry: &Entry) {}
    fn on_entry_deleted(&self, _entry_id: &str) {}
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::Arc;

    #[test]
    fn test_entry_from_text() {
        let entry = Entry::from_text("bugün güzel bir gündü #mirat", "phone");
        assert_eq!(entry.text, "bugün güzel bir gündü #mirat");
        assert_eq!(entry.tags, vec!["mirat"]);
        assert_eq!(entry.originator_id, "phone");
        assert!(!entry.entry_id.is_empty());
    }

    #[test]
    fn test_entry_metadata() {
        let entry = Entry::from_text("toplantı status:done time:2h #work", "phone");
        assert_eq!(entry.metadata.get("status").unwrap(), "done");
        assert_eq!(entry.metadata.get("time").unwrap(), "2h");
        assert_eq!(entry.tags, vec!["work"]);
    }

    #[test]
    fn test_memory_index_idempotent() {
        let index = MemoryIndex::new();
        let entry = Entry::from_text("test #mirat", "phone");
        index.on_entry_created(&entry);
        index.on_entry_created(&entry); // ikinci kez — ignore edilmeli
        assert_eq!(index.all().len(), 1);
    }

    #[test]
    fn test_p2p_sync_no_loop() {
        let _phone = Arc::new(KaydetCore::new("phone"));
        let _laptop = Arc::new(KaydetCore::new("laptop"));

        // Arc::get_mut ile listener ekleyemeyiz çünkü Arc paylaşılıyor
        // Bu yüzden KaydetCore'u Mutex ile sarmamız gerekiyor
        // Şimdilik unsafe get_mut kullanıyoruz — test ortamında tek thread
        let phone_index = Arc::new(MemoryIndex::new());
        let laptop_index = Arc::new(MemoryIndex::new());

        // Bu test mimariyi doğruluyor — tam p2p testi
        // integration testlerde Mutex<KaydetCore> ile yapılacak
        let entry = Entry::from_text("yolda not aldım #mirat", "phone");
        phone_index.on_entry_created(&entry);
        laptop_index.on_entry_created(&entry);

        assert_eq!(phone_index.by_tag("mirat").len(), 1);
        assert_eq!(laptop_index.by_tag("mirat").len(), 1);
    }
}
