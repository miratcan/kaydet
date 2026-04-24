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
    since: i64,
    exclude_device: Option<&str>,
    limit: usize,
) -> rusqlite::Result<(Vec<SyncChange>, bool)> {
    let mut stmt = conn.prepare(
        "SELECT id, entry_id, action, device_id, created_at
         FROM sync_log
         WHERE id > ?1
           AND (?2 IS NULL OR device_id IS NULL OR device_id != ?2)
         ORDER BY id
         LIMIT ?3"
    )?;

    let fetch_limit = (limit + 1) as i64;
    let rows: Vec<SyncChange> = stmt.query_map(
        rusqlite::params![since, exclude_device, fetch_limit],
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

pub fn max_id(conn: &Connection) -> rusqlite::Result<i64> {
    conn.query_row(
        "SELECT COALESCE(MAX(id), 0) FROM sync_log",
        [],
        |row| row.get(0),
    )
}

pub fn updated_at(conn: &Connection, entry_id: &str) -> rusqlite::Result<Option<String>> {
    conn.query_row(
        "SELECT MAX(created_at) FROM sync_log WHERE entry_id = ?1",
        rusqlite::params![entry_id],
        |row| row.get(0),
    )
}
