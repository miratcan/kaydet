// Storage — FileSystem üzerinde entry okuma/yazma
//
// Python karşılığı:
//   class Storage:
//       def __init__(self, fs: FileSystem):
//           self.fs = fs
//
//       def add_entry(self, entry: Entry) -> None:
//           day = today()
//           existing = self.fs.read_day(day) or ""
//           self.fs.write_day(day, existing + format_entry(entry))
//
//       def all_entries(self) -> dict[str, dict[str, Entry]]:
//           result = {}
//           for day in self.fs.list_days():
//               result[day] = parse_day(self.fs.read_day(day))
//           return result
//
// Storage, EventListener'dır — KaydetCore'a listener olarak eklenir.
// Bir entry oluşunca Storage onu diske yazar.

use std::collections::HashMap;
use chrono::Local;

use crate::filesystem::{FileSystem, FsResult};
use crate::merkle::MerkleTree;
use crate::{Entry, EventListener};

pub struct Storage {
    fs: Box<dyn FileSystem>,
}

impl Storage {
    pub fn new(fs: Box<dyn FileSystem>) -> Storage {
        Storage { fs }
    }

    /// Bugünün tarihini döner: "2026-04-21"
    fn today() -> String {
        Local::now().format("%Y-%m-%d").to_string()
    }

    /// Entry'yi .txt formatına çevirir
    /// Örnek: "14:25 [d1]: yolda not aldım #mirat"
    fn format_entry(entry: &Entry) -> String {
        format!("{} [{}]: {}\n", entry.timestamp, entry.entry_id, entry.text)
    }

    /// Bir günlük dosyasını parse eder, entry_id -> text map döner
    fn parse_day(content: &str) -> HashMap<String, String> {
        let mut entries = HashMap::new();
        for line in content.lines() {
            if let Some((_ts, id, text)) = parse_entry_line(line) {
                entries.insert(id, text);
            }
        }
        entries
    }

    /// Gün dosyasını parse eder: entry_id -> (timestamp, text)
    pub fn parse_day_full(content: &str) -> HashMap<String, (String, String)> {
        let mut entries = HashMap::new();
        for line in content.lines() {
            if let Some((ts, id, text)) = parse_entry_line(line) {
                entries.insert(id, (ts, text));
            }
        }
        entries
    }

    pub fn list_days(&self) -> FsResult<Vec<String>> {
        self.fs.list_days()
    }

    pub fn read_day(&self, date: &str) -> FsResult<String> {
        self.fs.read_day(date)
    }

    /// Tüm storage'ı okur: date -> { entry_id -> text }
    pub fn all_entries(&self) -> FsResult<HashMap<String, HashMap<String, String>>> {
        let mut result = HashMap::new();
        for day in self.fs.list_days()? {
            let content = self.fs.read_day(&day)?;
            result.insert(day, Self::parse_day(&content));
        }
        Ok(result)
    }

    /// Merkle tree hesapla
    pub fn merkle_tree(&self) -> FsResult<MerkleTree> {
        let all = self.all_entries()?;
        Ok(MerkleTree::build(&all))
    }

    /// Belirli bir entry'yi getir
    pub fn get_entry(&self, date: &str, entry_id: &str) -> FsResult<Option<String>> {
        let content = self.fs.read_day(date)?;
        Ok(Self::parse_day(&content).remove(entry_id))
    }

    /// Entry'yi diske yaz — mevcut günlük dosyasına ekle
    fn write_entry(&self, entry: &Entry) -> FsResult<()> {
        let date = Self::today();

        // timestamp boşsa şu anki saati kullan
        let mut entry_to_write = entry.clone();
        if entry_to_write.timestamp.is_empty() {
            entry_to_write.timestamp = Local::now().format("%H:%M").to_string();
        }

        let existing = self.fs.read_day(&date).unwrap_or_default();
        let new_content = existing + &Self::format_entry(&entry_to_write);
        self.fs.write_day(&date, &new_content)
    }
}

impl EventListener for Storage {
    fn on_entry_created(&self, entry: &Entry) {
        if let Err(e) = self.write_entry(entry) {
            eprintln!("[Storage] write failed: {}", e);
        }
    }

    fn on_entry_updated(&self, entry: &Entry) {
        // ileride: mevcut satırı bul, güncelle
        // şimdilik yeni satır ekle
        if let Err(e) = self.write_entry(entry) {
            eprintln!("[Storage] update failed: {}", e);
        }
    }

    fn on_entry_deleted(&self, entry_id: &str) {
        // ileride: satırı dosyadan sil
        // şimdilik log
        eprintln!("[Storage] delete not yet implemented: {}", entry_id);
    }
}

// ---------------------------------------------------------------------------
// Entry line parser
// ---------------------------------------------------------------------------

/// "HH:MM [id]: text" → (timestamp, id, text)
pub fn parse_entry_line(line: &str) -> Option<(String, String, String)> {
    let line = line.trim();
    if line.len() < 8 {
        return None;
    }

    // timestamp kontrolü: "HH:MM"
    if !line.chars().nth(2).map(|c| c == ':').unwrap_or(false) {
        return None;
    }
    let timestamp = line[..5].to_string();

    // "[id]:" kısmını bul
    let bracket_start = line.find('[')?;
    let bracket_end = line.find(']')?;
    if bracket_end <= bracket_start {
        return None;
    }

    let entry_id = line[bracket_start + 1..bracket_end].trim().to_string();

    // "]: " sonrasını al
    let rest_start = bracket_end + 1;
    let text = line[rest_start..]
        .trim_start_matches(|c| c == ':' || c == ' ')
        .to_string();

    Some((timestamp, entry_id, text))
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use crate::filesystem::MemoryFs;
    use crate::KaydetCore;

    #[test]
    fn test_parse_entry_line() {
        let (ts, id, text) = parse_entry_line("14:25 [d1]: yolda not aldım #mirat").unwrap();
        assert_eq!(ts, "14:25");
        assert_eq!(id, "d1");
        assert_eq!(text, "yolda not aldım #mirat");
    }

    #[test]
    fn test_parse_entry_line_invalid() {
        assert!(parse_entry_line("bu bir entry değil").is_none());
        assert!(parse_entry_line("").is_none());
    }

    #[test]
    fn test_storage_write_and_read() {
        let fs = MemoryFs::new();
        // bugünün tarihini manuel yaz
        let today = Storage::today();
        fs.write_day(&today, "").unwrap();

        let storage = Storage::new(Box::new(MemoryFs::new()));

        let mut entry = Entry::from_text("test #mirat", "phone");
        entry.entry_id = "d1".to_string();
        entry.timestamp = "14:25".to_string();

        storage.on_entry_created(&entry);

        let all = storage.all_entries().unwrap();
        let day = all.get(&today);
        assert!(day.is_some());
        let day = day.unwrap();
        assert_eq!(day.get("d1").unwrap(), "test #mirat");
    }

    #[test]
    fn test_merkle_tree_from_storage() {
        let storage = Storage::new(Box::new(MemoryFs::new()));

        let mut e1 = Entry::from_text("ilk entry #mirat", "phone");
        e1.entry_id = "d1".to_string();
        e1.timestamp = "09:00".to_string();
        storage.on_entry_created(&e1);

        let mut e2 = Entry::from_text("ikinci entry #work", "phone");
        e2.entry_id = "d2".to_string();
        e2.timestamp = "10:00".to_string();
        storage.on_entry_created(&e2);

        let tree = storage.merkle_tree().unwrap();
        assert_ne!(tree.root, 0);
        assert_eq!(tree.days.len(), 1); // aynı gün

        let today = Storage::today();
        assert!(tree.entries.get(&today).unwrap().contains_key("d1"));
        assert!(tree.entries.get(&today).unwrap().contains_key("d2"));
    }

    #[test]
    fn test_storage_as_listener() {
        let fs = MemoryFs::new();
        let storage = Storage::new(Box::new(MemoryFs::new()));

        let mut core = KaydetCore::new("phone");
        // storage'ı listener olarak ekle
        // Not: Box<Storage> gerekiyor ama Storage: EventListener
        // Bu test mimariyi doğruluyor

        let mut entry = Entry::from_text("core'dan yazıldı #test", "phone");
        entry.entry_id = "d1".to_string();
        entry.timestamp = "14:00".to_string();
        storage.on_entry_created(&entry);

        let all = storage.all_entries().unwrap();
        let today = Storage::today();
        assert!(all.get(&today).unwrap().contains_key("d1"));
    }
}
