pub mod files;
pub mod sync;

use axum::{Router, routing::{get, post}};
use crate::AppState;

pub fn routes() -> Router<AppState> {
    Router::new()
        .route("/sync", post(sync::handle_sync))
        .route("/files/upload", post(files::upload))
        .route("/files/{filename}", get(files::download))
}
