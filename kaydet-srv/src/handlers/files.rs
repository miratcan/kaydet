// handlers/files.rs — POST /files/upload, GET /files/{filename}

use axum::{
    body::Body,
    extract::{Multipart, Path, State},
    http::{header, StatusCode},
    response::Response,
};
use std::io::Write;

use crate::AppState;

const MAX_FILE_SIZE: usize = 100 * 1024 * 1024; // 100 MB

// POST /files/upload — multipart/form-data with field "file" and "filename"
pub async fn upload(
    State(state): State<AppState>,
    mut multipart: Multipart,
) -> Result<StatusCode, StatusCode> {
    let attachments_dir = state.store.storage_dir.join("attachments");
    std::fs::create_dir_all(&attachments_dir).map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?;

    let mut filename: Option<String> = None;
    let mut data: Vec<u8> = Vec::new();

    while let Some(field) = multipart.next_field().await.map_err(|_| StatusCode::BAD_REQUEST)? {
        match field.name() {
            Some("filename") => {
                filename = Some(field.text().await.map_err(|_| StatusCode::BAD_REQUEST)?);
            }
            Some("file") => {
                let bytes = field.bytes().await.map_err(|_| StatusCode::BAD_REQUEST)?;
                if bytes.len() > MAX_FILE_SIZE {
                    return Err(StatusCode::PAYLOAD_TOO_LARGE);
                }
                data = bytes.to_vec();
            }
            _ => {}
        }
    }

    let filename = filename.ok_or(StatusCode::BAD_REQUEST)?;
    if !is_safe_filename(&filename) {
        return Err(StatusCode::BAD_REQUEST);
    }

    let dest = attachments_dir.join(&filename);
    let tmp = attachments_dir.join(format!(".{filename}.tmp"));
    std::fs::write(&tmp, &data).map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?;
    std::fs::rename(&tmp, &dest).map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?;

    Ok(StatusCode::OK)
}

// GET /files/{filename}
pub async fn download(
    State(state): State<AppState>,
    Path(filename): Path<String>,
) -> Result<Response, StatusCode> {
    if !is_safe_filename(&filename) {
        return Err(StatusCode::BAD_REQUEST);
    }

    let path = state.store.storage_dir.join("attachments").join(&filename);
    if !path.exists() {
        return Err(StatusCode::NOT_FOUND);
    }

    let data = std::fs::read(&path).map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?;

    Ok(Response::builder()
        .header(header::CONTENT_TYPE, "application/octet-stream")
        .header(
            header::CONTENT_DISPOSITION,
            format!("attachment; filename=\"{}\"", filename),
        )
        .body(Body::from(data))
        .unwrap())
}

fn is_safe_filename(name: &str) -> bool {
    !name.is_empty()
        && !name.contains('/')
        && !name.contains("..")
        && name.chars().all(|c| c.is_alphanumeric() || "._-".contains(c))
}
