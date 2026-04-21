// Merkle Tree — storage hash hesaplama
//
// Python karşılığı:
//   def entry_hash(entry_text: str) -> int:
//       return crc32(entry_text.encode('utf-8'))
//
//   def day_hash(entry_hashes: list[int]) -> int:
//       data = b''.join(h.to_bytes(4, 'big') for h in sorted_hashes)
//       return crc32(data)
//
//   def root_hash(day_hashes: dict[str, int]) -> int:
//       data = b''.join(h.to_bytes(4, 'big') for h in sorted_day_hashes)
//       return crc32(data)
//
// Sıralama zorunlu: aynı entry'ler farklı sırada gelirse aynı hash çıkmalı.

use crc32fast::Hasher;
use std::collections::HashMap;

// ---------------------------------------------------------------------------
// Entry hash
// ---------------------------------------------------------------------------

pub fn entry_hash(text: &str) -> u32 {
    let mut h = Hasher::new();
    h.update(text.as_bytes());
    h.finalize()
}

// ---------------------------------------------------------------------------
// Day hash — o günün tüm entry hash'lerinin hash'i
// ---------------------------------------------------------------------------

pub fn day_hash(entry_hashes: &[u32]) -> u32 {
    // sırala — sıra bağımsız olmalı
    let mut sorted = entry_hashes.to_vec();
    sorted.sort();

    let mut h = Hasher::new();
    for hash in sorted {
        h.update(&hash.to_be_bytes());
    }
    h.finalize()
}

// ---------------------------------------------------------------------------
// Root hash — tüm storage'ın özeti
// ---------------------------------------------------------------------------

pub fn root_hash(day_hashes: &HashMap<String, u32>) -> u32 {
    // tarihe göre sırala
    let mut sorted_days: Vec<(&String, &u32)> = day_hashes.iter().collect();
    sorted_days.sort_by_key(|(date, _)| *date);

    let mut h = Hasher::new();
    for (_, hash) in sorted_days {
        h.update(&hash.to_be_bytes());
    }
    h.finalize()
}

// ---------------------------------------------------------------------------
// MerkleTree — storage'ın tam snapshot'u
// ---------------------------------------------------------------------------

// Python karşılığı:
//   @dataclass
//   class MerkleTree:
//       root: int
//       days: dict[str, int]          # date -> day_hash
//       entries: dict[str, dict[str, int]]  # date -> {entry_id -> entry_hash}

#[derive(Debug, Clone)]
pub struct MerkleTree {
    pub root: u32,
    pub days: HashMap<String, u32>,
    pub entries: HashMap<String, HashMap<String, u32>>,
}

impl MerkleTree {
    /// Storage'daki tüm entry'lerden tree hesapla.
    /// entries: { date -> { entry_id -> entry_text } }
    pub fn build(storage: &HashMap<String, HashMap<String, String>>) -> MerkleTree {
        let mut days: HashMap<String, u32> = HashMap::new();
        let mut entry_hashes: HashMap<String, HashMap<String, u32>> = HashMap::new();

        for (date, day_entries) in storage {
            let mut hashes_for_day: HashMap<String, u32> = HashMap::new();
            let mut hash_values: Vec<u32> = Vec::new();

            for (entry_id, text) in day_entries {
                let h = entry_hash(text);
                hashes_for_day.insert(entry_id.clone(), h);
                hash_values.push(h);
            }

            days.insert(date.clone(), day_hash(&hash_values));
            entry_hashes.insert(date.clone(), hashes_for_day);
        }

        let root = root_hash(&days);

        MerkleTree {
            root,
            days,
            entries: entry_hashes,
        }
    }

    /// Boş tree — hiç entry yok. root = 0.
    pub fn empty() -> MerkleTree {
        MerkleTree {
            root: 0,
            days: HashMap::new(),
            entries: HashMap::new(),
        }
    }

    /// İki tree'yi karşılaştır, hangi entry'ler farklı?
    /// Döner: (sadece self'de olanlar, sadece other'da olanlar, ikisinde de farklı olanlar)
    /// Her biri (date, entry_id) tuple listesi.
    pub fn diff(&self, other: &MerkleTree) -> DiffResult {
        let mut only_in_self: Vec<(String, String)> = Vec::new();
        let mut only_in_other: Vec<(String, String)> = Vec::new();
        let mut modified: Vec<(String, String)> = Vec::new();

        // self'deki günleri tara
        for (date, self_day_hash) in &self.days {
            match other.days.get(date) {
                None => {
                    // bu gün other'da yok — tüm entry'ler only_in_self
                    if let Some(day_entries) = self.entries.get(date) {
                        for entry_id in day_entries.keys() {
                            only_in_self.push((date.clone(), entry_id.clone()));
                        }
                    }
                }
                Some(other_day_hash) => {
                    if self_day_hash == other_day_hash {
                        continue; // bu gün aynı, atla
                    }
                    // gün hash'leri farklı — entry seviyesine in
                    let self_entries = self.entries.get(date).cloned().unwrap_or_default();
                    let other_entries = other.entries.get(date).cloned().unwrap_or_default();

                    for (entry_id, self_hash) in &self_entries {
                        match other_entries.get(entry_id) {
                            None => only_in_self.push((date.clone(), entry_id.clone())),
                            Some(other_hash) => {
                                if self_hash != other_hash {
                                    modified.push((date.clone(), entry_id.clone()));
                                }
                            }
                        }
                    }
                    for entry_id in other_entries.keys() {
                        if !self_entries.contains_key(entry_id) {
                            only_in_other.push((date.clone(), entry_id.clone()));
                        }
                    }
                }
            }
        }

        // other'da olup self'de olmayan günler
        for (date, _) in &other.days {
            if !self.days.contains_key(date) {
                if let Some(day_entries) = other.entries.get(date) {
                    for entry_id in day_entries.keys() {
                        only_in_other.push((date.clone(), entry_id.clone()));
                    }
                }
            }
        }

        DiffResult {
            only_in_self,
            only_in_other,
            modified,
        }
    }
}

#[derive(Debug)]
pub struct DiffResult {
    pub only_in_self: Vec<(String, String)>,   // (date, entry_id) — karşıda yok
    pub only_in_other: Vec<(String, String)>,  // (date, entry_id) — bizde yok
    pub modified: Vec<(String, String)>,        // (date, entry_id) — ikisinde de var ama farklı
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    fn make_storage(entries: &[(&str, &str, &str)]) -> HashMap<String, HashMap<String, String>> {
        // entries: [(date, entry_id, text), ...]
        let mut storage: HashMap<String, HashMap<String, String>> = HashMap::new();
        for (date, id, text) in entries {
            storage
                .entry(date.to_string())
                .or_default()
                .insert(id.to_string(), text.to_string());
        }
        storage
    }

    #[test]
    fn test_same_storage_same_root() {
        let s = make_storage(&[("2026-04-19", "d1", "test #mirat")]);
        let t1 = MerkleTree::build(&s);
        let t2 = MerkleTree::build(&s);
        assert_eq!(t1.root, t2.root);
    }

    #[test]
    fn test_different_entry_different_root() {
        let s1 = make_storage(&[("2026-04-19", "d1", "test #mirat")]);
        let s2 = make_storage(&[("2026-04-19", "d1", "test #mirat degistirildi")]);
        let t1 = MerkleTree::build(&s1);
        let t2 = MerkleTree::build(&s2);
        assert_ne!(t1.root, t2.root);
    }

    #[test]
    fn test_empty_tree_root_zero() {
        let t = MerkleTree::empty();
        assert_eq!(t.root, 0);
    }

    #[test]
    fn test_diff_only_in_self() {
        let s1 = make_storage(&[
            ("2026-04-19", "d1", "test"),
            ("2026-04-19", "d2", "yeni entry"),
        ]);
        let s2 = make_storage(&[("2026-04-19", "d1", "test")]);

        let t1 = MerkleTree::build(&s1);
        let t2 = MerkleTree::build(&s2);
        let diff = t1.diff(&t2);

        assert_eq!(diff.only_in_self.len(), 1);
        assert_eq!(diff.only_in_self[0].1, "d2");
        assert!(diff.only_in_other.is_empty());
        assert!(diff.modified.is_empty());
    }

    #[test]
    fn test_diff_modified() {
        let s1 = make_storage(&[("2026-04-19", "d1", "eski metin")]);
        let s2 = make_storage(&[("2026-04-19", "d1", "yeni metin")]);

        let t1 = MerkleTree::build(&s1);
        let t2 = MerkleTree::build(&s2);
        let diff = t1.diff(&t2);

        assert_eq!(diff.modified.len(), 1);
        assert_eq!(diff.modified[0].1, "d1");
    }

    #[test]
    fn test_diff_identical_no_changes() {
        let s = make_storage(&[
            ("2026-04-19", "d1", "test"),
            ("2026-04-20", "d2", "test2"),
        ]);
        let t1 = MerkleTree::build(&s);
        let t2 = MerkleTree::build(&s);
        let diff = t1.diff(&t2);

        assert!(diff.only_in_self.is_empty());
        assert!(diff.only_in_other.is_empty());
        assert!(diff.modified.is_empty());
    }
}
