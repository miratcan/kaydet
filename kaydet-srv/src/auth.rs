// auth.rs — Bearer token middleware

use axum::{
    extract::State,
    http::StatusCode,
    middleware::Next,
    response::Response,
};
use axum::extract::Request;

use crate::AppState;

pub async fn auth_middleware(
    State(state): State<AppState>,
    req: Request,
    next: Next,
) -> Result<Response, StatusCode> {
    let token = req
        .headers()
        .get("Authorization")
        .and_then(|v| v.to_str().ok())
        .and_then(|v| v.strip_prefix("Bearer "))
        .map(|t| t.to_string());

    let Some(token) = token else {
        return Err(StatusCode::UNAUTHORIZED);
    };

    let valid = {
        let db = state.store.db.lock().unwrap();
        let count: i64 = db.query_row(
            "SELECT COUNT(*) FROM sync_keys WHERE key = ?1",
            rusqlite::params![token],
            |row| row.get(0),
        ).unwrap_or(0);
        count > 0
    };

    if !valid {
        return Err(StatusCode::UNAUTHORIZED);
    }

    {
        let db = state.store.db.lock().unwrap();
        let _ = db.execute(
            "UPDATE sync_keys SET last_used_at = datetime('now') WHERE key = ?1",
            rusqlite::params![token],
        );
    }

    Ok(next.run(req).await)
}
