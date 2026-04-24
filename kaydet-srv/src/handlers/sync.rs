// handlers/sync.rs — POST /sync
//
// Request body (JSON):
// {
//   "since": 42,           // sync token (last seen sync_log id)
//   "device_id": "abc123",
//   "entries": [...]       // local changes to push
// }
//
// Response body (JSON):
// {
//   "entries": [...],      // remote changes to apply
//   "new_token": 55,
//   "has_more": false
// }

use axum::{extract::State, http::StatusCode, Json};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

use crate::AppState;
use crate::sync_log;
use kaydet_core_rs::Entry;

const PAGE_SIZE: usize = 500;

// ---------------------------------------------------------------------------
// Wire types
// ---------------------------------------------------------------------------

#[derive(Debug, Deserialize)]
pub struct SyncRequest {
    pub since: i64,
    pub device_id: String,
    #[serde(default)]
    pub entries: Vec<EntryData>,
}

#[derive(Debug, Serialize)]
pub struct SyncResponse {
    pub entries: Vec<EntryData>,
    pub new_token: i64,
    pub has_more: bool,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct EntryData {
    pub entry_id: String,
    pub source_file: String,
    pub timestamp: String,
    pub text: String,
    #[serde(default)]
    pub tags: Vec<String>,
    #[serde(default)]
    pub metadata: HashMap<String, String>,
    #[serde(default)]
    pub attachments: Vec<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub encrypted_secret: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub updated_at: Option<String>,
    #[serde(default)]
    pub deleted: bool,
}

// ---------------------------------------------------------------------------
// Handler
// ---------------------------------------------------------------------------

pub async fn handle_sync(
    State(state): State<AppState>,
    Json(req): Json<SyncRequest>,
) -> Result<Json<SyncResponse>, StatusCode> {
    let store = &state.store;

    // 1. Snapshot max sync_log id before applying client entries
    let pre_apply_max = {
        let db = store.db.lock().unwrap();
        sync_log::max_id(&db).unwrap_or(0)
    };

    // 2. Apply client's entries
    let mut applied = 0;
    for entry_data in &req.entries {
        if entry_data.deleted {
            let mut core = store.core.lock().unwrap();
            if core.delete_entry(&entry_data.entry_id).is_ok() {
                let db = store.db.lock().unwrap();
                let _ = sync_log::log_action(&db, &entry_data.entry_id, "deleted", Some(&req.device_id));
                applied += 1;
            }
        } else {
            match upsert_entry(store, entry_data, &req.device_id) {
                Ok(true) => applied += 1,
                Ok(false) => {}
                Err(e) => {
                    tracing::warn!("Failed to apply entry {}: {}", entry_data.entry_id, e);
                }
            }
        }
    }

    if applied > 0 {
        if let Err(e) = store.reload_core() {
            tracing::error!("Failed to reload core: {}", e);
        }
    }

    // 3. Collect changes since client's token (exclude entries from this device)
    let (changes, has_more) = {
        let db = store.db.lock().unwrap();
        sync_log::changes_since(&db, req.since, Some(&req.device_id), PAGE_SIZE)
            .map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?
    };

    // Limit to pre_apply_max so client doesn't see their own pushed entries
    let changes: Vec<_> = changes.into_iter()
        .filter(|c| c.id <= pre_apply_max)
        .collect();

    let new_token = changes.last().map(|c| c.id).unwrap_or(req.since);

    // 4. Deduplicate: last action wins per entry_id
    let mut to_send: HashMap<String, &str> = HashMap::new();
    for c in &changes {
        to_send.insert(c.entry_id.clone(), &c.action);
    }
    // We need owned strings for the action — collect properly
    let to_send: HashMap<String, String> = changes.iter()
        .fold(HashMap::new(), |mut m, c| {
            m.insert(c.entry_id.clone(), c.action.clone());
            m
        });

    // 5. Load full entry data
    let mut entries: Vec<EntryData> = Vec::new();
    for (entry_id, action) in &to_send {
        if action == "deleted" {
            entries.push(EntryData {
                entry_id: entry_id.clone(),
                source_file: String::new(),
                timestamp: String::new(),
                text: String::new(),
                tags: vec![],
                metadata: HashMap::new(),
                attachments: vec![],
                encrypted_secret: None,
                updated_at: None,
                deleted: true,
            });
        } else {
            let core = store.core.lock().unwrap();
            if let Some(entry) = core.index.get(entry_id) {
                let updated_at = {
                    let db = store.db.lock().unwrap();
                    sync_log::updated_at(&db, entry_id).ok().flatten()
                };
                let enc = load_secret(&store.storage_dir, entry_id);
                entries.push(entry_to_wire(entry, updated_at, enc));
            }
        }
    }

    Ok(Json(SyncResponse { entries, new_token, has_more }))
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

fn upsert_entry(
    store: &crate::store::ServerStore,
    data: &EntryData,
    device_id: &str,
) -> Result<bool, String> {
    // Check if exists
    let existing = {
        let core = store.core.lock().unwrap();
        core.index.get(&data.entry_id).cloned()
    };

    if let Some(existing) = existing {
        // Conflict check: server newer → skip
        let server_updated = {
            let db = store.db.lock().unwrap();
            sync_log::updated_at(&db, &data.entry_id).ok().flatten()
        };
        if let (Some(srv), Some(cli)) = (&server_updated, &data.updated_at) {
            if &srv[..19.min(srv.len())] > &cli[..19.min(cli.len())] {
                return Ok(false);
            }
        }

        let mut core = store.core.lock().unwrap();
        core.update_entry(&data.entry_id, &data.text)
            .map_err(|e| e.to_string())?;
        drop(core);

        let db = store.db.lock().unwrap();
        sync_log::log_action(&db, &data.entry_id, "updated", Some(device_id))
            .map_err(|e| e.to_string())?;
    } else {
        // Parse date from source_file ("2026-04-23.txt")
        let at = parse_entry_datetime(&data.source_file, &data.timestamp);

        let mut core = store.core.lock().unwrap();
        let _entry = core.add_entry_with_id(&data.entry_id, &data.text, at)
            .map_err(|e| e.to_string())?;
        drop(core);

        let db = store.db.lock().unwrap();
        sync_log::log_action(&db, &data.entry_id, "created", Some(device_id))
            .map_err(|e| e.to_string())?;
    }

    // Store encrypted secret if provided
    if let Some(enc_b64) = &data.encrypted_secret {
        if let Ok(enc_bytes) = base64_decode(enc_b64) {
            let secrets_dir = store.storage_dir.join("secrets");
            let _ = std::fs::create_dir_all(&secrets_dir);
            let path = secrets_dir.join(format!("{}.enc", data.entry_id));
            let _ = std::fs::write(path, enc_bytes);
        }
    }

    Ok(true)
}

fn entry_to_wire(
    entry: &Entry,
    updated_at: Option<String>,
    encrypted_secret: Option<String>,
) -> EntryData {
    EntryData {
        entry_id: entry.entry_id.clone(),
        source_file: format!("{}.txt", entry.date),
        timestamp: entry.timestamp.clone(),
        text: entry.text.clone(),
        tags: entry.tags.clone(),
        metadata: entry.metadata.clone(),
        attachments: entry.attachments.clone(),
        encrypted_secret,
        updated_at,
        deleted: false,
    }
}

fn load_secret(storage_dir: &std::path::Path, entry_id: &str) -> Option<String> {
    let path = storage_dir.join("secrets").join(format!("{}.enc", entry_id));
    if path.exists() {
        let bytes = std::fs::read(path).ok()?;
        Some(base64_encode(&bytes))
    } else {
        None
    }
}

fn parse_entry_datetime(source_file: &str, timestamp: &str) -> Option<chrono::DateTime<chrono::Local>> {
    use chrono::TimeZone;
    // source_file: "2026-04-23.txt"
    let date_str = source_file.strip_suffix(".txt")?;
    let dt_str = format!("{} {}:00", date_str, timestamp);
    chrono::NaiveDateTime::parse_from_str(&dt_str, "%Y-%m-%d %H:%M:%S")
        .ok()
        .and_then(|ndt| ndt.and_local_timezone(chrono::Local).single())
}

fn base64_encode(data: &[u8]) -> String {
    use std::fmt::Write;
    // simple base64 without external dep — use std or include manually
    // axum already pulls in base64 transitively via tower-http; use it.
    // For now: manual const table to stay dep-free.
    const TABLE: &[u8] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let mut out = String::with_capacity((data.len() + 2) / 3 * 4);
    for chunk in data.chunks(3) {
        let b0 = chunk[0] as usize;
        let b1 = chunk.get(1).copied().unwrap_or(0) as usize;
        let b2 = chunk.get(2).copied().unwrap_or(0) as usize;
        let n = (b0 << 16) | (b1 << 8) | b2;
        out.push(TABLE[(n >> 18) & 63] as char);
        out.push(TABLE[(n >> 12) & 63] as char);
        out.push(if chunk.len() > 1 { TABLE[(n >> 6) & 63] as char } else { '=' });
        out.push(if chunk.len() > 2 { TABLE[n & 63] as char } else { '=' });
    }
    out
}

fn base64_decode(s: &str) -> Result<Vec<u8>, String> {
    fn val(c: u8) -> Result<u8, String> {
        match c {
            b'A'..=b'Z' => Ok(c - b'A'),
            b'a'..=b'z' => Ok(c - b'a' + 26),
            b'0'..=b'9' => Ok(c - b'0' + 52),
            b'+' => Ok(62),
            b'/' => Ok(63),
            b'=' => Ok(0),
            _ => Err(format!("invalid base64 char: {c}")),
        }
    }
    let s = s.trim().as_bytes();
    let mut out = Vec::with_capacity(s.len() / 4 * 3);
    for chunk in s.chunks(4) {
        if chunk.len() < 4 { break; }
        let a = val(chunk[0])?;
        let b = val(chunk[1])?;
        let c = val(chunk[2])?;
        let d = val(chunk[3])?;
        let n = ((a as u32) << 18) | ((b as u32) << 12) | ((c as u32) << 6) | (d as u32);
        out.push((n >> 16) as u8);
        if chunk[2] != b'=' { out.push((n >> 8) as u8); }
        if chunk[3] != b'=' { out.push(n as u8); }
    }
    Ok(out)
}
