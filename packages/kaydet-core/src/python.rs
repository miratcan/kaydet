// PyO3 bindings — Rust core'u Python'a expose eder
//
// Python'da kullanım:
//   import kaydet_core_rs
//   core = kaydet_core_rs.KaydetCore("/path/to/storage")
//   entry = core.add_entry("bugün #mirat")
//   print(entry.entry_id, entry.tags)

#![cfg(feature = "python")]
use pyo3::prelude::*;
use pyo3::exceptions::PyValueError;
use std::collections::HashMap;
use std::sync::Mutex;

use crate::{Entry, KaydetCore, StorageTrait};
use crate::filesystem::NativeFs;
use chrono::Datelike;

// ---------------------------------------------------------------------------
// NativeStorage — gerçek disk I/O, StorageTrait implement eder
// ---------------------------------------------------------------------------

struct NativeStorage {
    fs: NativeFs,
}

impl NativeStorage {
    fn new(storage_dir: &str) -> Self {
        NativeStorage { fs: NativeFs::new(storage_dir) }
    }
}

impl StorageTrait for NativeStorage {
    fn append(&self, entry: &Entry) -> Result<(), String> {
        use crate::filesystem::FileSystem;
        let existing = self.fs.read_day(&entry.date).unwrap_or_default();
        let new_content = inject_entry(&existing, entry);
        self.fs.write_day(&entry.date, &new_content).map_err(|e| e.to_string())
    }

    fn replace(&self, entry: &Entry) -> Result<(), String> {
        use crate::filesystem::FileSystem;
        let existing = self.fs.read_day(&entry.date).unwrap_or_default();
        let without = remove_entry_from_content(&existing, &entry.entry_id);
        let replaced = inject_entry(&without, entry);
        self.fs.write_day(&entry.date, &replaced).map_err(|e| e.to_string())
    }

    fn delete(&self, entry_id: &str) -> Result<(), String> {
        use crate::filesystem::FileSystem;
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
        use crate::filesystem::FileSystem;
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

fn update_metadata_in_text(text: &str, key: &str, value: &str) -> String {
    let token = format!("{key}:");
    let new_token = format!("{key}:{value}");
    // varsa güncelle
    if text.split_whitespace().any(|w| w.starts_with(&token)) {
        text.split_whitespace()
            .map(|w| if w.starts_with(&token) { new_token.as_str() } else { w })
            .collect::<Vec<_>>()
            .join(" ")
    } else {
        // yoksa sona ekle
        format!("{text} {new_token}")
    }
}

fn format_entry(entry: &Entry) -> String {
    // Format: "HH:MM [ID]: text\n"
    // Çok satırlı text: ilk satır header'da, geri kalanlar alt satırlarda
    let mut lines = entry.text.lines();
    let first = lines.next().unwrap_or("");
    let header = format!("{} [{}]: {}\n", entry.timestamp, entry.entry_id, first);
    let rest: String = lines.map(|l| format!("{l}\n")).collect();
    header + &rest
}

fn inject_entry(content: &str, entry: &Entry) -> String {
    // Zaman sıralı yerleştirme: HH:MM karşılaştırması ile doğru yere ekle
    let new_line = format_entry(entry);
    let mut result = String::new();
    let mut inserted = false;

    for line in content.lines() {
        // Entry header satırı mı? "HH:MM [ID]:" formatı
        if !inserted {
            if let Some(ts) = line.split_whitespace().next() {
                // "HH:MM" formatında mı?
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

    if !inserted {
        result.push_str(&new_line);
    }
    result
}

fn remove_entry_from_content(content: &str, entry_id: &str) -> String {
    // Her entry tek satır: "HH:MM [ID]: text"
    // Çok satırlı entry: header + devam satırları (HH:MM ile başlamayan)
    let marker = format!("[{entry_id}]:");
    let mut result = String::new();
    let mut skip = false;

    for line in content.lines() {
        // Yeni entry header mi?
        let is_header = line.split_whitespace().next()
            .map(|ts| ts.len() == 5 && ts.as_bytes().get(2) == Some(&b':'))
            .unwrap_or(false);

        if line.contains(&marker) {
            skip = true;
            continue;
        }
        if skip && is_header {
            skip = false;
        }
        if !skip {
            result.push_str(line);
            result.push('\n');
        }
    }
    result
}

fn parse_day(content: &str, date: &str) -> Vec<Entry> {
    use crate::{parse_tags, parse_metadata, parse_attachments};
    let mut entries = Vec::new();

    for line in content.lines() {
        // Format: "HH:MM [ID]: text..."
        // Satir bos, yorum veya baslik ise atla
        let trimmed = line.trim();
        if trimmed.is_empty() || trimmed.starts_with('-') || trimmed.starts_with('#') {
            continue;
        }

        // entry_id ve timestamp ayikla
        let Some(entry_id) = extract_entry_id(trimmed) else { continue };
        let Some(timestamp) = extract_timestamp(trimmed) else { continue };

        // "[ID]: " sonrasini text olarak al
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
    }
    entries
}

fn extract_entry_id(line: &str) -> Option<String> {
    let start = line.find('[')? + 1;
    let end = line.find(']')?;
    if end > start { Some(line[start..end].to_string()) } else { None }
}

fn extract_timestamp(line: &str) -> Option<String> {
    // "HH:MM [ID]: text"
    let parts: Vec<&str> = line.split_whitespace().collect();
    if parts.len() >= 1 { Some(parts[0].to_string()) } else { None }
}

// ---------------------------------------------------------------------------
// PyEntry
// ---------------------------------------------------------------------------

#[pyclass(name = "Entry")]
#[derive(Clone)]
pub struct PyEntry {
    #[pyo3(get)] pub entry_id: String,
    #[pyo3(get)] pub date: String,
    #[pyo3(get)] pub timestamp: String,
    #[pyo3(get)] pub text: String,
    #[pyo3(get)] pub tags: Vec<String>,
    #[pyo3(get)] pub attachments: Vec<String>,
    #[pyo3(get)] pub metadata: HashMap<String, String>,
}

impl From<Entry> for PyEntry {
    fn from(e: Entry) -> PyEntry {
        PyEntry {
            entry_id: e.entry_id,
            date: e.date,
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
        format!("Entry(id={}, date={}, text={:?})", self.entry_id, self.date, &self.text[..self.text.len().min(40)])
    }
}

// ---------------------------------------------------------------------------
// PyKaydetCore
// ---------------------------------------------------------------------------

#[pyclass(name = "KaydetCore")]
pub struct PyKaydetCore {
    inner: Mutex<KaydetCore>,
}

#[pymethods]
impl PyKaydetCore {
    #[new]
    fn new(storage_dir: &str) -> PyResult<PyKaydetCore> {
        let storage = Box::new(NativeStorage::new(storage_dir));

        // startup: mevcut entry'leri yükle
        let existing = storage.load_all()
            .map_err(|e| PyValueError::new_err(e.to_string()))?;

        let mut core = KaydetCore::new(storage, None);

        for entry in existing {
            core.index.update(entry);
        }

        Ok(PyKaydetCore { inner: Mutex::new(core) })
    }

    fn add_entry(&self, text: &str) -> PyResult<PyEntry> {
        let mut core = self.inner.lock().unwrap();
        core.add_entry(text)
            .map(PyEntry::from)
            .map_err(|e| PyValueError::new_err(e))
    }

    fn update_entry(&self, entry_id: &str, new_text: &str) -> PyResult<()> {
        let mut core = self.inner.lock().unwrap();
        core.update_entry(entry_id, new_text)
            .map_err(|e| PyValueError::new_err(e))
    }

    fn delete_entry(&self, entry_id: &str) -> PyResult<()> {
        let mut core = self.inner.lock().unwrap();
        core.delete_entry(entry_id)
            .map_err(|e| PyValueError::new_err(e))
    }

    fn get_entry(&self, entry_id: &str) -> PyResult<Option<PyEntry>> {
        let core = self.inner.lock().unwrap();
        Ok(core.index.get(entry_id).map(|e| PyEntry::from(e.clone())))
    }

    fn all_entries(&self) -> PyResult<Vec<PyEntry>> {
        let core = self.inner.lock().unwrap();
        Ok(core.index.all().into_iter().map(|e| PyEntry::from(e.clone())).collect())
    }

    fn by_tag(&self, tag: &str) -> PyResult<Vec<PyEntry>> {
        let core = self.inner.lock().unwrap();
        Ok(core.index.by_tag(tag).into_iter().map(|e| PyEntry::from(e.clone())).collect())
    }

    fn by_meta(&self, key: &str, value: &str) -> PyResult<Vec<PyEntry>> {
        let core = self.inner.lock().unwrap();
        Ok(core.index.by_meta(key, value).into_iter().map(|e| PyEntry::from(e.clone())).collect())
    }

    #[pyo3(signature = (since=None, until=None))]
    fn by_date_range(&self, since: Option<&str>, until: Option<&str>) -> PyResult<Vec<PyEntry>> {
        let core = self.inner.lock().unwrap();
        Ok(core.index.by_date_range(since, until).into_iter().map(|e| PyEntry::from(e.clone())).collect())
    }

    fn search_text(&self, term: &str) -> PyResult<Vec<PyEntry>> {
        let core = self.inner.lock().unwrap();
        Ok(core.index.search_text(term).into_iter().map(|e| PyEntry::from(e.clone())).collect())
    }

    fn list_tags(&self) -> PyResult<Vec<String>> {
        let core = self.inner.lock().unwrap();
        let mut tags: std::collections::HashSet<String> = std::collections::HashSet::new();
        for entry in core.index.all() {
            for tag in &entry.tags {
                tags.insert(tag.clone());
            }
        }
        let mut result: Vec<String> = tags.into_iter().collect();
        result.sort();
        Ok(result)
    }

    // search_entries: query string'i parse edip MemoryIndex'i filtreler.
    // Query syntax:
    //   #tag        → tag filter
    //   -#tag       → exclude tag
    //   key:value   → metadata filter
    //   since:DATE  → date range (YYYY-MM-DD)
    //   until:DATE  → date range (YYYY-MM-DD)
    //   word        → full-text search
    #[pyo3(signature = (query="", limit=0))]
    fn search_entries(&self, query: &str, limit: usize) -> PyResult<Vec<PyEntry>> {
        let core = self.inner.lock().unwrap();
        let mut results: Vec<&Entry> = core.index.all();

        if !query.trim().is_empty() {
            let mut since: Option<String> = None;
            let mut until: Option<String> = None;
            let mut include_tags: Vec<String> = vec![];
            let mut exclude_tags: Vec<String> = vec![];
            let mut include_meta: Vec<(String, String)> = vec![];
            let mut text_terms: Vec<String> = vec![];
            let mut exclude_terms: Vec<String> = vec![];

            for token in query.split_whitespace() {
                if let Some(tag) = token.strip_prefix("-#") {
                    exclude_tags.push(tag.to_lowercase());
                } else if let Some(tag) = token.strip_prefix('#') {
                    include_tags.push(tag.to_lowercase());
                } else if token.starts_with('-') {
                    exclude_terms.push(token[1..].to_lowercase());
                } else if let Some((key, val)) = token.split_once(':') {
                    match key {
                        "since" => since = Some(val.to_string()),
                        "until" => until = Some(val.to_string()),
                        _ => include_meta.push((key.to_string(), val.to_string())),
                    }
                } else {
                    text_terms.push(token.to_lowercase());
                }
            }

            results = results.into_iter().filter(|e| {
                // tag filters
                for tag in &include_tags {
                    if !e.tags.iter().any(|t| t == tag) { return false; }
                }
                for tag in &exclude_tags {
                    if e.tags.iter().any(|t| t == tag) { return false; }
                }
                // metadata filters
                for (key, val) in &include_meta {
                    if e.metadata.get(key).map(|v| v != val).unwrap_or(true) { return false; }
                }
                // date range
                if let Some(s) = &since {
                    if e.date.as_str() < s.as_str() { return false; }
                }
                if let Some(u) = &until {
                    if e.date.as_str() > u.as_str() { return false; }
                }
                // text search
                let text_lower = e.text.to_lowercase();
                for term in &text_terms {
                    if !text_lower.contains(term.as_str()) { return false; }
                }
                for term in &exclude_terms {
                    if text_lower.contains(term.as_str()) { return false; }
                }
                true
            }).collect();
        }

        // entry_id'ye göre azalan sıra (en yeni önce)
        results.sort_by(|a, b| b.entry_id.cmp(&a.entry_id));

        if limit > 0 {
            results.truncate(limit);
        }

        Ok(results.into_iter().map(|e| PyEntry::from(e.clone())).collect())
    }

    fn entry_count(&self) -> PyResult<usize> {
        let core = self.inner.lock().unwrap();
        Ok(core.index.all().len())
    }

    // get_stats: yil+ay icin gun bazi entry sayilari
    // { "2026-04-01": 3, "2026-04-02": 1, ... }
    #[pyo3(signature = (year=None, month=None))]
    fn get_stats(&self, year: Option<i32>, month: Option<i32>) -> PyResult<pyo3::PyObject> {
        use pyo3::types::PyDict;
        use pyo3::Python;

        let now = chrono::Local::now();
        let target_year = year.unwrap_or(now.year());
        let target_month = month.unwrap_or(now.month() as i32);

        let prefix = format!("{:04}-{:02}", target_year, target_month);

        let core = self.inner.lock().unwrap();
        let mut counts: HashMap<String, usize> = HashMap::new();

        for entry in core.index.all() {
            if entry.date.starts_with(&prefix) {
                *counts.entry(entry.date.clone()).or_insert(0) += 1;
            }
        }

        Python::with_gil(|py| {
            let dict = PyDict::new_bound(py);
            let total: usize = counts.values().sum();
            let mut days: Vec<(String, usize)> = counts.into_iter().collect();
            days.sort_by(|a, b| a.0.cmp(&b.0));
            let days_dict = PyDict::new_bound(py);
            for (date, count) in days {
                days_dict.set_item(date, count)?;
            }
            dict.set_item("year", target_year)?;
            dict.set_item("month", target_month)?;
            dict.set_item("total_entries", total)?;
            dict.set_item("days", days_dict)?;
            Ok(dict.into())
        })
    }

    // list_todos: #todo tag'li entry'leri döner
    #[pyo3(signature = (status=None))]
    fn list_todos(&self, status: Option<&str>) -> PyResult<Vec<PyEntry>> {
        let core = self.inner.lock().unwrap();
        let status = status.unwrap_or("pending");

        Ok(core.index.by_tag("todo")
            .into_iter()
            .filter(|e| {
                let entry_status = e.metadata.get("status").map(|s| s.as_str()).unwrap_or("pending");
                entry_status == status
            })
            .map(|e| PyEntry::from(e.clone()))
            .collect())
    }

    // mark_todo_done: entry'nin status'unu done yap, completed_at ekle
    fn mark_todo_done(&self, entry_id: &str) -> PyResult<()> {
        let mut core = self.inner.lock().unwrap();
        let old = core.index.get(entry_id)
            .ok_or_else(|| pyo3::exceptions::PyValueError::new_err(format!("entry not found: {entry_id}")))?
            .clone();

        let now = chrono::Local::now();
        let completed_at = now.format("%H:%M").to_string();

        // mevcut metne status:done ve completed_at ekle (varsa güncelle)
        let text = &old.text;
        let new_text = update_metadata_in_text(text, "status", "done");
        let new_text = update_metadata_in_text(&new_text, "completed_at", &completed_at);

        core.update_entry(entry_id, &new_text)
            .map_err(|e| pyo3::exceptions::PyValueError::new_err(e))
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
