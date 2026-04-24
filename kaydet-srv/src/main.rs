// kaydet-srv — sync server binary
//
// Usage:
//   kaydet-srv serve [--storage <dir>] [--port <port>]
//   kaydet-srv keygen <name> [--storage <dir>]
//   kaydet-srv keys [--storage <dir>]
//   kaydet-srv revoke <name> [--storage <dir>]

mod auth;
mod handlers;
mod store;
mod sync_log;

use std::net::SocketAddr;
use std::path::PathBuf;
use std::sync::Arc;

use axum::{Router, middleware};
use tracing_subscriber::{EnvFilter, fmt};

use crate::store::ServerStore;

#[derive(Clone)]
pub struct AppState {
    pub store: Arc<ServerStore>,
}

fn default_storage_dir() -> PathBuf {
    home::home_dir()
        .unwrap_or_else(|| PathBuf::from("."))
        .join(".kaydet")
        .join("storage")
}

fn arg_value(args: &[String], flag: &str) -> Option<String> {
    args.windows(2)
        .find(|w| w[0] == flag)
        .map(|w| w[1].clone())
}

fn arg_flag(args: &[String], flag: &str) -> bool {
    args.iter().any(|a| a == flag)
}

#[tokio::main]
async fn main() {
    let args: Vec<String> = std::env::args().collect();
    let subcommand = args.get(1).map(|s| s.as_str()).unwrap_or("serve");

    match subcommand {
        "serve" => cmd_serve(&args).await,
        "keygen" => cmd_keygen(&args),
        "keys" => cmd_keys(&args),
        "revoke" => cmd_revoke(&args),
        "--help" | "-h" | "help" => print_help(),
        _ => {
            eprintln!("Unknown command: {subcommand}");
            eprintln!("Run 'kaydet-srv help' for usage.");
            std::process::exit(1);
        }
    }
}

// ---------------------------------------------------------------------------
// serve
// ---------------------------------------------------------------------------

async fn cmd_serve(args: &[String]) {
    fmt()
        .with_env_filter(
            EnvFilter::from_default_env()
                .add_directive("kaydet_srv=info".parse().unwrap()),
        )
        .init();

    let storage_dir = arg_value(args, "--storage")
        .map(PathBuf::from)
        .unwrap_or_else(default_storage_dir);
    let port: u16 = arg_value(args, "--port")
        .and_then(|p| p.parse().ok())
        .unwrap_or(8765);

    std::fs::create_dir_all(&storage_dir).expect("failed to create storage dir");

    let store = Arc::new(
        ServerStore::open(storage_dir.clone()).expect("failed to open store"),
    );

    let state = AppState { store };

    let app = Router::new()
        .merge(handlers::routes())
        .route_layer(middleware::from_fn_with_state(
            state.clone(),
            auth::auth_middleware,
        ))
        .with_state(state);

    let addr = SocketAddr::from(([0, 0, 0, 0], port));
    tracing::info!("kaydet-srv listening on {} (storage: {})", addr, storage_dir.display());

    let listener = tokio::net::TcpListener::bind(addr).await.unwrap();
    axum::serve(listener, app).await.unwrap();
}

// ---------------------------------------------------------------------------
// keygen
// ---------------------------------------------------------------------------

fn cmd_keygen(args: &[String]) {
    let name = args.get(2).cloned().unwrap_or_else(|| {
        eprintln!("Usage: kaydet-srv keygen <name> [--storage <dir>]");
        std::process::exit(1);
    });

    let storage_dir = arg_value(args, "--storage")
        .map(PathBuf::from)
        .unwrap_or_else(default_storage_dir);

    std::fs::create_dir_all(&storage_dir).expect("failed to create storage dir");
    let store = ServerStore::open(storage_dir).expect("failed to open store");

    let key = generate_api_key(&store, &name);
    println!("{key}");
}

// ---------------------------------------------------------------------------
// keys
// ---------------------------------------------------------------------------

fn cmd_keys(args: &[String]) {
    let storage_dir = arg_value(args, "--storage")
        .map(PathBuf::from)
        .unwrap_or_else(default_storage_dir);

    let store = ServerStore::open(storage_dir).expect("failed to open store");
    let db = store.db.lock().unwrap();

    let mut stmt = db.prepare(
        "SELECT key, name, created_at, last_used_at FROM sync_keys ORDER BY created_at"
    ).unwrap();

    let rows: Vec<(String, String, String, Option<String>)> = stmt
        .query_map([], |row| {
            Ok((row.get(0)?, row.get(1)?, row.get(2)?, row.get(3)?))
        })
        .unwrap()
        .filter_map(|r| r.ok())
        .collect();

    if rows.is_empty() {
        println!("No API keys found. Use 'kaydet-srv keygen <name>' to create one.");
        return;
    }

    println!("{:<20} {:<16} {:<20} {}", "NAME", "KEY PREFIX", "CREATED", "LAST USED");
    println!("{}", "-".repeat(72));
    for (key, name, created_at, last_used) in rows {
        let prefix = format!("{}...", &key[..key.len().min(12)]);
        let last = last_used.as_deref().unwrap_or("never");
        println!("{:<20} {:<16} {:<20} {}", name, prefix, &created_at[..19], last);
    }
}

// ---------------------------------------------------------------------------
// revoke
// ---------------------------------------------------------------------------

fn cmd_revoke(args: &[String]) {
    let name = args.get(2).cloned().unwrap_or_else(|| {
        eprintln!("Usage: kaydet-srv revoke <name> [--storage <dir>]");
        std::process::exit(1);
    });

    let storage_dir = arg_value(args, "--storage")
        .map(PathBuf::from)
        .unwrap_or_else(default_storage_dir);

    let store = ServerStore::open(storage_dir).expect("failed to open store");
    let db = store.db.lock().unwrap();

    let deleted = db
        .execute("DELETE FROM sync_keys WHERE name = ?1", rusqlite::params![name])
        .unwrap_or(0);

    if deleted > 0 {
        println!("Revoked key for '{name}'.");
    } else {
        eprintln!("No key found with name '{name}'.");
        std::process::exit(1);
    }
}

// ---------------------------------------------------------------------------
// help
// ---------------------------------------------------------------------------

fn print_help() {
    println!("kaydet-srv — Kaydet sync server\n");
    println!("USAGE:");
    println!("  kaydet-srv serve [--storage <dir>] [--port <port>]");
    println!("  kaydet-srv keygen <name> [--storage <dir>]");
    println!("  kaydet-srv keys [--storage <dir>]");
    println!("  kaydet-srv revoke <name> [--storage <dir>]");
    println!("\nDEFAULTS:");
    println!("  --storage   ~/.kaydet/storage");
    println!("  --port      8765");
}

// ---------------------------------------------------------------------------
// Key management
// ---------------------------------------------------------------------------

fn generate_api_key(store: &ServerStore, name: &str) -> String {
    use std::fmt::Write;

    // 24 random bytes → 48 hex chars
    let mut bytes = [0u8; 24];
    bytes.iter_mut().for_each(|b| *b = rand::random());
    let mut hex = String::with_capacity(48);
    for b in bytes { write!(hex, "{:02x}", b).unwrap(); }
    let key = format!("kyd_{hex}");

    let db = store.db.lock().unwrap();
    db.execute(
        "INSERT OR REPLACE INTO sync_keys (key, name, created_at) VALUES (?1, ?2, datetime('now'))",
        rusqlite::params![key, name],
    ).expect("failed to insert key");

    key
}
