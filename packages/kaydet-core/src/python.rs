// PyO3 bindings — Rust core'u Python'a expose eder
//
// Python'da kullanım:
//   import kaydet_core
//   core = kaydet_core.PyKaydetCore("phone", "/path/to/storage")
//   entry = core.add_entry("bugün #mirat")
//   print(entry.entry_id, entry.tags)

use pyo3::prelude::*;
use pyo3::exceptions::PyValueError;
use std::collections::HashMap;
use std::sync::{Arc, Mutex};

use crate::{Entry, KaydetCore, MemoryIndex, EventListener};
use crate::storage::Storage;
use crate::filesystem::NativeFs;
use crate::merkle::MerkleTree;

// ---------------------------------------------------------------------------
// PyEntry — Python'a açılan Entry
// ---------------------------------------------------------------------------

#[pyclass(name = "Entry")]
#[derive(Clone)]
pub struct PyEntry {
    #[pyo3(get)]
    pub entry_id: String,
    #[pyo3(get)]
    pub timestamp: String,
    #[pyo3(get)]
    pub text: String,
    #[pyo3(get)]
    pub tags: Vec<String>,
    #[pyo3(get)]
    pub attachments: Vec<String>,
    #[pyo3(get)]
    pub metadata: HashMap<String, String>,
}

impl From<Entry> for PyEntry {
    fn from(e: Entry) -> PyEntry {
        PyEntry {
            entry_id: e.entry_id,
            timestamp: e.timestamp,
            text: e.text,
            tags: e.tags,
            attachments: e.attachments,
            metadata: e.metadata,
        }
    }
}

#[pymethods]
impl PyEntry {
    fn __repr__(&self) -> String {
        format!("Entry(id={}, ts={}, text={})", self.entry_id, self.timestamp, &self.text[..self.text.len().min(40)])
    }
}

// ---------------------------------------------------------------------------
// PyKaydetCore — Python'a açılan ana sınıf
// ---------------------------------------------------------------------------

#[pyclass(name = "KaydetCore")]
pub struct PyKaydetCore {
    inner: Arc<Mutex<KaydetCoreInner>>,
}

struct KaydetCoreInner {
    core: KaydetCore,
    index: Arc<MemoryIndex>,
    storage: Arc<Storage>,
}

#[pymethods]
impl PyKaydetCore {
    #[new]
    fn new(device_id: &str, storage_dir: &str) -> PyResult<PyKaydetCore> {
        let fs = NativeFs::new(storage_dir);
        let storage = Arc::new(Storage::new(Box::new(fs)));
        let index = Arc::new(MemoryIndex::new());

        let mut core = KaydetCore::new(device_id);

        // storage ve index'i listener olarak ekle
        // Arc<T> where T: EventListener için wrapper lazım
        core.add_listener(Box::new(ArcListener(Arc::clone(&storage))));
        core.add_listener(Box::new(ArcListener(Arc::clone(&index))));

        // storage'daki mevcut entry'leri index'e yükle
        match storage.all_entries() {
            Ok(all) => {
                for (_date, day_entries) in &all {
                    for (entry_id, text) in day_entries {
                        let mut entry = Entry::from_text(text, device_id);
                        entry.entry_id = entry_id.clone();
                        index.on_entry_created(&entry);
                    }
                }
            }
            Err(e) => {
                // storage_dir henüz yoksa sorun değil
                eprintln!("[KaydetCore] storage load warning: {}", e);
            }
        }

        Ok(PyKaydetCore {
            inner: Arc::new(Mutex::new(KaydetCoreInner { core, index, storage })),
        })
    }

    fn add_entry(&self, text: &str) -> PyResult<PyEntry> {
        let inner = self.inner.lock().unwrap();
        let entry = inner.core.add_entry(text);
        Ok(PyEntry::from(entry))
    }

    fn get_entry(&self, entry_id: &str) -> PyResult<Option<PyEntry>> {
        let inner = self.inner.lock().unwrap();
        Ok(inner.index.get(entry_id).map(PyEntry::from))
    }

    fn search(&self, query: &str) -> PyResult<Vec<PyEntry>> {
        let inner = self.inner.lock().unwrap();
        let query_lower = query.to_lowercase();

        // tag araması: "#mirat" → by_tag("mirat")
        if let Some(tag) = query_lower.strip_prefix('#') {
            return Ok(inner.index.by_tag(tag).into_iter().map(PyEntry::from).collect());
        }

        // text araması: tüm entry'lerde ara
        Ok(inner.index
            .all()
            .into_iter()
            .filter(|e| e.text.to_lowercase().contains(&query_lower))
            .map(PyEntry::from)
            .collect())
    }

    fn list_tags(&self) -> PyResult<Vec<String>> {
        let inner = self.inner.lock().unwrap();
        let mut tags: std::collections::HashSet<String> = std::collections::HashSet::new();
        for entry in inner.index.all() {
            for tag in entry.tags {
                tags.insert(tag);
            }
        }
        let mut result: Vec<String> = tags.into_iter().collect();
        result.sort();
        Ok(result)
    }

    fn merkle_root(&self) -> PyResult<u32> {
        let inner = self.inner.lock().unwrap();
        inner.storage
            .merkle_tree()
            .map(|t| t.root)
            .map_err(|e| PyValueError::new_err(e.to_string()))
    }

    fn entry_count(&self) -> PyResult<usize> {
        let inner = self.inner.lock().unwrap();
        Ok(inner.index.all().len())
    }
}

// ---------------------------------------------------------------------------
// ArcListener — Arc<T> için EventListener wrapper
// ---------------------------------------------------------------------------
// Python karşılığı: bu Rust'a özgü bir pattern.
// Arc (Atomic Reference Counted) = Python'daki paylaşılan referans.
// Rust ownership kuralları gereği Box<dyn EventListener> içine
// Arc<T> koyamayız doğrudan — bu wrapper aracılık eder.

struct ArcListener<T: EventListener>(Arc<T>);

impl<T: EventListener + Send + Sync> EventListener for ArcListener<T> {
    fn on_entry_created(&self, entry: &Entry) {
        self.0.on_entry_created(entry);
    }
    fn on_entry_updated(&self, entry: &Entry) {
        self.0.on_entry_updated(entry);
    }
    fn on_entry_deleted(&self, entry_id: &str) {
        self.0.on_entry_deleted(entry_id);
    }
}

// ---------------------------------------------------------------------------
// Python module
// ---------------------------------------------------------------------------

#[pymodule]
fn kaydet_core_rs(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<PyKaydetCore>()?;
    m.add_class::<PyEntry>()?;
    Ok(())
}
