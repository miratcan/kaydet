// sync_log.rs — sync_log table operations

use rusqlite::Connection;

#[derive(Debug, serde::Serialize, serde::Deserialize, Clone)]
pub struct SyncChange {
    pub id: i64,
    pub entry_id: String,
    pub action: String,
    pub device_id: Option<String>,
    pub created_at: String,
}

pub fn log_action(
    conn: &Connection,
    entry_id: &str,
    action: &str,
    device_id: Option<&str>,
) -> rusqlite::Result<()> {
    conn.execute(
        "INSERT INTO sync_log (entry_id, action, device_id) VALUES (?1, ?2, ?3)",
        rusqlite::params![entry_id, action, device_id],
    )?;
    Ok(())
}

pub fn changes_since(
    conn: &Connection,
    since_ts: i64,
    exclude_device: Option<&str>,
    limit: usize,
) -> rusqlite::Result<(Vec<SyncChange>, bool)> {
    // since_ts is a unix timestamp (seconds). created_at is stored as
    // SQLite datetime string; we compare using strftime epoch conversion.
    let mut stmt = conn.prepare(
        "SELECT id, entry_id, action, device_id, created_at
         FROM sync_log
         WHERE CAST(strftime('%s', created_at) AS INTEGER) > ?1
           AND (?2 IS NULL OR device_id IS NULL OR device_id != ?2)
         ORDER BY created_at, id
         LIMIT ?3"
    )?;

    let fetch_limit = (limit + 1) as i64;
    let rows: Vec<SyncChange> = stmt.query_map(
        rusqlite::params![since_ts, exclude_device, fetch_limit],
        |row| Ok(SyncChange {
            id: row.get(0)?,
            entry_id: row.get(1)?,
            action: row.get(2)?,
            device_id: row.get(3)?,
            created_at: row.get(4)?,
        }),
    )?.filter_map(|r| r.ok()).collect();

    let has_more = rows.len() > limit;
    let rows = rows.into_iter().take(limit).collect();
    Ok((rows, has_more))
}

pub fn server_time() -> i64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs() as i64
}

pub fn updated_at_ts(conn: &Connection, entry_id: &str) -> rusqlite::Result<Option<i64>> {
    conn.query_row(
        "SELECT CAST(strftime('%s', MAX(created_at)) AS INTEGER) FROM sync_log WHERE entry_id = ?1",
        rusqlite::params![entry_id],
        |row| row.get(0),
    )
}
