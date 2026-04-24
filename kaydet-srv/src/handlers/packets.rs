// handlers/packets.rs — KYDT binary packet transfer
//
// POST /v1/packets/{entry_id}                — upload (chunked)
// GET  /v1/packets/{entry_id}                — download
// GET  /v1/packets/{entry_id}/status         — resume info

use axum::{
    body::Body,
    extract::{Path, Request, State},
    http::{header, StatusCode},
    response::Response,
    Json,
};
use serde::Serialize;
use std::io::Write;

use kaydet_core_rs::packet::{deserialize, serialize};

use crate::AppState;

// ---------------------------------------------------------------------------
// POST /v1/packets/{entry_id} — upload chunk
// ---------------------------------------------------------------------------

pub async fn upload_chunk(
    State(state): State<AppState>,
    Path(entry_id): Path<String>,
    req: Request,
) -> Result<Response, StatusCode> {
    if !is_safe_id(&entry_id) {
        return Err(StatusCode::BAD_REQUEST);
    }

    let offset: u64 = req
        .headers()
        .get("X-Kaydet-Chunk-Offset")
        .and_then(|v| v.to_str().ok())
        .and_then(|v| v.parse().ok())
        .unwrap_or(0);

    let total_size: Option<u64> = req
        .headers()
        .get("X-Kaydet-Total-Size")
        .and_then(|v| v.to_str().ok())
        .and_then(|v| v.parse().ok());

    let body_bytes = axum::body::to_bytes(req.into_body(), 64 * 1024 * 1024)
        .await
        .map_err(|_| StatusCode::BAD_REQUEST)?;

    let packets_dir = state.store.storage_dir.join(".packets");
    std::fs::create_dir_all(&packets_dir).map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?;

    let part_path = packets_dir.join(format!("{entry_id}.part"));

    // Write chunk at offset
    let current_size = part_path.metadata().map(|m| m.len()).unwrap_or(0);
    if offset != current_size {
        return Err(StatusCode::CONFLICT); // offset mismatch
    }

    {
        let mut file = std::fs::OpenOptions::new()
            .create(true)
            .append(true)
            .open(&part_path)
            .map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?;
        file.write_all(&body_bytes)
            .map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?;
    }

    let received = part_path.metadata().map(|m| m.len()).unwrap_or(0);
    let is_complete = total_size.map(|t| received >= t).unwrap_or(false);

    if is_complete {
        // Read full packet, verify + apply
        let packet_bytes = std::fs::read(&part_path)
            .map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?;

        let packet = deserialize(&packet_bytes).map_err(|e| {
            tracing::warn!("Packet CRC/parse error for {entry_id}: {e}");
            let _ = std::fs::remove_file(&part_path);
            StatusCode::UNPROCESSABLE_ENTITY
        })?;

        // Apply entry to core
        {
            let mut core = state.store.core.lock().unwrap();
            let _ = core.add_entry_with_id(
                &packet.entry.entry_id,
                &packet.entry.text,
                None,
            );
        }

        // Write attachments atomically
        if !packet.attachments.is_empty() {
            let att_dir = state.store.storage_dir.join("attachments");
            std::fs::create_dir_all(&att_dir).map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?;
            for (name, data) in &packet.attachments {
                if !is_safe_filename(name) { continue; }
                let dest = att_dir.join(name);
                let tmp = att_dir.join(format!(".{name}.tmp"));
                std::fs::write(&tmp, data).map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?;
                std::fs::rename(&tmp, &dest).map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?;
            }
        }

        // Log to sync_log
        {
            let db = state.store.db.lock().unwrap();
            let _ = crate::sync_log::log_action(&db, &packet.entry.entry_id, "created", None);
        }

        std::fs::remove_file(&part_path).ok();

        let body = serde_json::json!({
            "entry_id": packet.entry.entry_id,
            "status": "complete"
        });
        return Ok(Response::builder()
            .status(StatusCode::OK)
            .header(header::CONTENT_TYPE, "application/json")
            .body(Body::from(body.to_string()))
            .unwrap());
    }

    let body = serde_json::json!({ "received": received });
    Ok(Response::builder()
        .status(StatusCode::ACCEPTED)
        .header(header::CONTENT_TYPE, "application/json")
        .body(Body::from(body.to_string()))
        .unwrap())
}

// ---------------------------------------------------------------------------
// GET /v1/packets/{entry_id} — download
// ---------------------------------------------------------------------------

pub async fn download_packet(
    State(state): State<AppState>,
    Path(entry_id): Path<String>,
) -> Result<Response, StatusCode> {
    if !is_safe_id(&entry_id) {
        return Err(StatusCode::BAD_REQUEST);
    }

    let entry = {
        let core = state.store.core.lock().unwrap();
        core.index.get(&entry_id).cloned()
    };

    let Some(entry) = entry else {
        return Err(StatusCode::NOT_FOUND);
    };

    // Load attachments from disk
    let mut attachments = std::collections::HashMap::new();
    let att_dir = state.store.storage_dir.join("attachments");
    for att_name in &entry.attachments {
        if !is_safe_filename(att_name) { continue; }
        let path = att_dir.join(att_name);
        if let Ok(data) = std::fs::read(&path) {
            attachments.insert(att_name.clone(), data);
        }
    }

    let packet_bytes = serialize(&entry, &attachments);

    Ok(Response::builder()
        .status(StatusCode::OK)
        .header(header::CONTENT_TYPE, "application/octet-stream")
        .header("X-Kaydet-Entry-Id", &entry_id)
        .header("X-Kaydet-Total-Size", packet_bytes.len().to_string())
        .body(Body::from(packet_bytes))
        .unwrap())
}

// ---------------------------------------------------------------------------
// GET /v1/packets/{entry_id}/status — resume info
// ---------------------------------------------------------------------------

#[derive(Serialize)]
pub struct PacketStatus {
    entry_id: String,
    received: u64,
    status: &'static str,
}

pub async fn packet_status(
    State(state): State<AppState>,
    Path(entry_id): Path<String>,
) -> Result<Json<PacketStatus>, StatusCode> {
    if !is_safe_id(&entry_id) {
        return Err(StatusCode::BAD_REQUEST);
    }

    let part_path = state.store.storage_dir.join(".packets").join(format!("{entry_id}.part"));
    let received = part_path.metadata().map(|m| m.len()).unwrap_or(0);
    let status = if received > 0 { "incomplete" } else { "not_started" };

    Ok(Json(PacketStatus { entry_id, received, status }))
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

fn is_safe_id(id: &str) -> bool {
    !id.is_empty()
        && id.len() <= 64
        && id.chars().all(|c| c.is_alphanumeric() || c == '-' || c == '_')
}

fn is_safe_filename(name: &str) -> bool {
    !name.is_empty()
        && !name.contains('/')
        && !name.contains("..")
        && name.chars().all(|c| c.is_alphanumeric() || "._-".contains(c))
}
