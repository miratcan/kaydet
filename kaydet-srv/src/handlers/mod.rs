pub mod packets;
pub mod sync;

use axum::{Router, routing::{get, post}};
use crate::AppState;

pub fn routes() -> Router<AppState> {
    Router::new()
        .route("/sync", post(sync::handle_sync))
        .route("/v1/packets/:entry_id", post(packets::upload_chunk))
        .route("/v1/packets/:entry_id", get(packets::download_packet))
        .route("/v1/packets/:entry_id/status", get(packets::packet_status))
}
