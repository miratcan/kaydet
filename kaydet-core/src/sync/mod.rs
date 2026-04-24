// sync/mod.rs — SyncBackend trait + transfer primitives (packet, crypto)

pub mod crypto;
pub mod packet;
//
// KaydetCore holds an optional SyncBackend. When core.sync() is called:
//   1. collect local changes (via sync_log callback)
//   2. push them to the backend
//   3. pull remote changes (entry IDs + metadata)
//   4. fetch each missing packet, apply to storage + index
//
// The trait is intentionally transport-agnostic: HTTP, stdin, P2P, noop —
// any implementation can be plugged in. If no backend is attached (e.g. C64
// build), sync() is a no-op.

use crate::Entry;

// ---------------------------------------------------------------------------
// Wire types
// ---------------------------------------------------------------------------

/// A remote entry change returned by pull().
pub struct RemoteChange {
    pub entry_id: String,
    pub deleted: bool,
    /// Full entry data if available inline (no separate packet fetch needed).
    pub entry: Option<Entry>,
}

/// Result of a sync() call.
#[derive(Debug, Default)]
pub struct SyncStats {
    pub pushed: usize,
    pub pulled: usize,
    pub packets_fetched: usize,
}

// ---------------------------------------------------------------------------
// SyncBackend trait
// ---------------------------------------------------------------------------

pub trait SyncBackend: Send + Sync {
    /// Push local entry changes to the remote, pull remote changes since
    /// `since` (unix timestamp). Returns (remote_changes, new_server_time).
    fn exchange(
        &self,
        since: i64,
        local_entries: &[Entry],
    ) -> Result<(Vec<RemoteChange>, i64), String>;

    /// Fetch a full entry + attachments as a KYDT packet.
    /// Returns raw packet bytes; caller deserializes.
    fn fetch_packet(&self, entry_id: &str) -> Result<Vec<u8>, String>;

    /// Upload a KYDT packet for a local entry.
    fn upload_packet(&self, entry_id: &str, packet: &[u8]) -> Result<(), String>;
}
