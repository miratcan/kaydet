// PyO3 bindings — exposes the Rust core to Python
//
// Usage:
//   import kaydet_core_rs
//   core = kaydet_core_rs.KaydetCore("/path/to/storage")
//   entry = core.add_entry("today #tag")
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
// NativeStorage — real disk I/O, implements StorageTrait
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
    if text.split_whitespace().any(|w| w.starts_with(&token)) {
        // update existing token
        text.split_whitespace()
            .map(|w| if w.starts_with(&token) { new_token.as_str() } else { w })
            .collect::<Vec<_>>()
            .join(" ")
    } else {
        // append new token
        format!("{text} {new_token}")
    }
}

fn format_entry(entry: &Entry) -> String {
    // Format: "HH:MM [ID]: text\n"
    // Multi-line text: first line in the header, remaining lines as continuation
    let mut lines = entry.text.lines();
    let first = lines.next().unwrap_or("");
    let header = format!("{} [{}]: {}\n", entry.timestamp, entry.entry_id, first);
    let rest: String = lines.map(|l| format!("{l}\n")).collect();
    header + &rest
}

fn inject_entry(content: &str, entry: &Entry) -> String {
    // Insert in timestamp order by comparing HH:MM strings
    let new_line = format_entry(entry);
    let mut result = String::new();
    let mut inserted = false;

    for line in content.lines() {
        // Is this an entry header line? "HH:MM [ID]:" format
        if !inserted {
            if let Some(ts) = line.split_whitespace().next() {
                // Is it in "HH:MM" format?
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
    // Each entry: header line "HH:MM [ID]: text" + optional continuation lines
    // Continuation lines do not start with "HH:MM"
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
    let mut entries: Vec<Entry> = Vec::new();

    for line in content.lines() {
        // Format: "HH:MM [ID]: text..."
        let trimmed = line.trim();

        // Separator lines (---) are always skipped
        if trimmed.starts_with('-') {
            continue;
        }

        // Empty lines: pass through to current entry as blank lines (preserve paragraph breaks)
        if trimmed.is_empty() {
            if let Some(last) = entries.last_mut() {
                last.text.push('\n');
            }
            continue;
        }

        // Try to parse as an entry header line
        let entry_id = extract_entry_id(trimmed);
        let timestamp = extract_timestamp(trimmed);

        if let (Some(entry_id), Some(timestamp)) = (entry_id, timestamp) {
            // Header line: "HH:MM [ID]: text"
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
            // Continuation line: append to the previous entry's text
            last.text.push('\n');
            last.text.push_str(trimmed);
            // Re-parse tags/metadata/attachments from full updated text
            last.tags = parse_tags(&last.text);
            last.metadata = parse_metadata(&last.text);
            last.attachments = parse_attachments(&last.text);
        }
        // Lines before the first entry are ignored
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

        // startup: load all existing entries from disk
        let existing = storage.load_all()
            .map_err(|e| PyValueError::new_err(e.to_string()))?;

        let mut core = KaydetCore::new(storage, None);

        for entry in existing {
            core.index.update(entry);
        }

        Ok(PyKaydetCore { inner: Mutex::new(core) })
    }

    #[pyo3(signature = (text, at_date=None, at_time=None))]
    fn add_entry(&self, text: &str, at_date: Option<&str>, at_time: Option<&str>) -> PyResult<PyEntry> {
        let at = match (at_date, at_time) {
            (Some(date), Some(time)) => {
                let dt_str = format!("{} {}:00", date, time);
                chrono::NaiveDateTime::parse_from_str(&dt_str, "%Y-%m-%d %H:%M:%S")
                    .map(|ndt| ndt.and_local_timezone(chrono::Local).single())
                    .ok()
                    .flatten()
            }
            _ => None,
        };
        let mut core = self.inner.lock().unwrap();
        core.add_entry(text, at)
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
        use crate::{apply_query, parse_query};
        let core = self.inner.lock().unwrap();
        let all = core.index.all();
        let q = parse_query(query);
        let mut results = apply_query(all, &q);

        // sort ascending by date + timestamp (oldest first, newest last)
        results.sort_by(|a, b| {
            a.date.cmp(&b.date).then_with(|| a.timestamp.cmp(&b.timestamp))
        });

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

    // list_todos: returns entries tagged with #todo
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

        // add status:done and completed_at to the text (update if already present)
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

#[pyfunction]
fn generate_id() -> String {
    crate::short_id()
}

#[pyfunction]
fn encrypt_secret(plaintext: &str, password: &str) -> PyResult<Vec<u8>> {
    crate::sync::crypto::encrypt_secret(plaintext, password)
        .map_err(|e| PyValueError::new_err(e.to_string()))
}

#[pyfunction]
fn decrypt_secret(encrypted: &[u8], password: &str) -> PyResult<String> {
    crate::sync::crypto::decrypt_secret(encrypted, password)
        .map_err(|e| PyValueError::new_err(e.to_string()))
}

#[pyfunction]
fn serialize_packet(
    py: Python<'_>,
    entry_id: &str,
    timestamp: &str,
    text: &str,
    attachments: HashMap<String, Vec<u8>>,
) -> PyResult<pyo3::PyObject> {
    use crate::sync::packet::serialize;
    use pyo3::types::PyBytes;
    let mut entry = crate::Entry::from_text(text, None);
    entry.entry_id = entry_id.to_string();
    entry.timestamp = timestamp.to_string();
    let data = serialize(&entry, &attachments);
    Ok(PyBytes::new_bound(py, &data).into())
}

#[pyfunction]
fn deserialize_packet(data: &[u8]) -> PyResult<pyo3::PyObject> {
    use crate::sync::packet::deserialize;
    use pyo3::types::{PyBytes, PyDict};
    use pyo3::Python;

    let packet = deserialize(data)
        .map_err(|e| PyValueError::new_err(e.to_string()))?;

    Python::with_gil(|py| {
        let result = PyDict::new_bound(py);
        result.set_item("entry_id", &packet.entry.entry_id)?;
        result.set_item("timestamp", &packet.entry.timestamp)?;
        result.set_item("text", &packet.entry.text)?;

        let atts = PyDict::new_bound(py);
        for (name, data) in &packet.attachments {
            atts.set_item(name, PyBytes::new_bound(py, data))?;
        }
        result.set_item("attachments", atts)?;
        Ok(result.into())
    })
}

#[pymodule]
fn kaydet_core_rs(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<PyKaydetCore>()?;
    m.add_class::<PyEntry>()?;
    m.add_function(wrap_pyfunction!(generate_id, m)?)?;
    m.add_function(wrap_pyfunction!(encrypt_secret, m)?)?;
    m.add_function(wrap_pyfunction!(decrypt_secret, m)?)?;
    m.add_function(wrap_pyfunction!(serialize_packet, m)?)?;
    m.add_function(wrap_pyfunction!(deserialize_packet, m)?)?;
    m.add("__all__", vec![
        "KaydetCore", "Entry", "generate_id",
        "encrypt_secret", "decrypt_secret",
        "serialize_packet", "deserialize_packet",
    ])?;
    Ok(())
}
