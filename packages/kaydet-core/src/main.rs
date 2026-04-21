use clap::{Parser, Subcommand};
use kaydet_core_rs::{KaydetCore, MemoryIndex, Storage, EventListener};
use kaydet_core_rs::filesystem::NativeFs;
use chrono::Local;
use std::path::PathBuf;

// ---------------------------------------------------------------------------
// CLI tanımı
// ---------------------------------------------------------------------------

#[derive(Parser)]
#[command(name = "kaydet", about = "personal journal — ZEN-DOOM edition")]
struct Cli {
    #[command(subcommand)]
    command: Command,

    /// Storage dizini (varsayılan: ~/.local/share/kaydet)
    #[arg(long, global = true)]
    storage: Option<PathBuf>,
}

#[derive(Subcommand)]
enum Command {
    /// Yeni kayıt ekle
    Add {
        /// Kayıt metni
        text: Vec<String>,
    },
    /// Kayıt ara
    Search {
        /// Arama sorgusu (#tag veya metin)
        query: String,
        /// Maksimum sonuç sayısı
        #[arg(short, long, default_value = "20")]
        limit: usize,
    },
    /// Son kayıtları listele
    List {
        #[arg(short, long, default_value = "10")]
        limit: usize,
    },
    /// Tüm tag'leri göster
    Tags,
    /// Storage istatistikleri
    Stats,
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

fn main() {
    let cli = Cli::parse();
    let storage_dir = resolve_storage_dir(cli.storage);

    // storage dizini yoksa oluştur
    std::fs::create_dir_all(&storage_dir).expect("storage dizini oluşturulamadı");

    let device_id = hostname();
    let fs = NativeFs::new(storage_dir.to_str().unwrap());
    let storage = std::sync::Arc::new(Storage::new(Box::new(fs)));
    let index = std::sync::Arc::new(MemoryIndex::new());

    // index'i storage'dan yükle
    load_index(&storage, &index, &device_id);

    let mut core = KaydetCore::new(&device_id);
    core.add_listener(Box::new(ArcListener(std::sync::Arc::clone(&storage))));
    core.add_listener(Box::new(ArcListener(std::sync::Arc::clone(&index))));

    match cli.command {
        Command::Add { text } => {
            let text = text.join(" ");
            if text.trim().is_empty() {
                eprintln!("hata: boş kayıt eklenemez");
                std::process::exit(1);
            }
            let mut entry = core.add_entry(&text);
            entry.timestamp = Local::now().format("%H:%M").to_string();
            println!("✓ kayıt eklendi [{}] {}", entry.entry_id, entry.timestamp);
            for tag in &entry.tags {
                println!("  #{}", tag);
            }
        }

        Command::Search { query, limit } => {
            let results: Vec<_> = if let Some(tag) = query.strip_prefix('#') {
                index.by_tag(tag)
            } else {
                index.all()
                    .into_iter()
                    .filter(|e| e.text.to_lowercase().contains(&query.to_lowercase()))
                    .collect()
            };

            let results: Vec<_> = results.into_iter().take(limit).collect();

            if results.is_empty() {
                println!("sonuç bulunamadı: {}", query);
                return;
            }

            println!("{} sonuç:", results.len());
            for entry in results {
                println!("  [{}] {} — {}", entry.entry_id, entry.timestamp, entry.text);
            }
        }

        Command::List { limit } => {
            let mut all = index.all();
            all.sort_by(|a, b| b.timestamp.cmp(&a.timestamp));
            let all: Vec<_> = all.into_iter().take(limit).collect();

            if all.is_empty() {
                println!("henüz kayıt yok.");
                return;
            }

            for entry in all {
                println!("[{}] {} — {}", entry.entry_id, entry.timestamp, entry.text);
            }
        }

        Command::Tags => {
            let mut tags: std::collections::HashMap<String, usize> = std::collections::HashMap::new();
            for entry in index.all() {
                for tag in entry.tags {
                    *tags.entry(tag).or_insert(0) += 1;
                }
            }
            let mut tags: Vec<_> = tags.into_iter().collect();
            tags.sort_by(|a, b| b.1.cmp(&a.1));

            if tags.is_empty() {
                println!("henüz tag yok.");
                return;
            }

            for (tag, count) in tags {
                println!("  #{} ({})", tag, count);
            }
        }

        Command::Stats => {
            let all = index.all();
            println!("toplam kayıt: {}", all.len());
            println!("storage:      {}", storage_dir.display());
            println!("cihaz:        {}", device_id);

            // tag sayısı
            let tag_count: std::collections::HashSet<String> = all
                .iter()
                .flat_map(|e| e.tags.iter().cloned())
                .collect();
            println!("benzersiz tag: {}", tag_count.len());
        }
    }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

fn resolve_storage_dir(override_path: Option<PathBuf>) -> PathBuf {
    if let Some(p) = override_path {
        return p;
    }
    // ~/.local/share/kaydet
    dirs::data_local_dir()
        .unwrap_or_else(|| PathBuf::from("."))
        .join("kaydet")
}

fn hostname() -> String {
    std::fs::read_to_string("/etc/hostname")
        .unwrap_or_default()
        .trim()
        .to_string()
        .or_else(|| {
            std::env::var("HOSTNAME").ok()
        })
        .unwrap_or_else(|| "local".to_string())
}

fn load_index(storage: &Storage, index: &MemoryIndex, device_id: &str) {
    use kaydet_core_rs::filesystem::FileSystem;
    if let Ok(days) = storage.list_days() {
        for day in days {
            if let Ok(content) = storage.read_day(&day) {
                let parsed = Storage::parse_day_full(&content);
                for (entry_id, (timestamp, text)) in parsed {
                    let mut entry = kaydet_core_rs::Entry::from_text(&text, device_id);
                    entry.entry_id = entry_id;
                    entry.timestamp = timestamp;
                    index.on_entry_created(&entry);
                }
            }
        }
    }
}

// Arc<T> için EventListener wrapper — lib.rs'teki ile aynı
struct ArcListener<T: kaydet_core_rs::EventListener>(std::sync::Arc<T>);

impl<T: kaydet_core_rs::EventListener + Send + Sync> kaydet_core_rs::EventListener for ArcListener<T> {
    fn on_entry_created(&self, entry: &kaydet_core_rs::Entry) { self.0.on_entry_created(entry); }
    fn on_entry_updated(&self, entry: &kaydet_core_rs::Entry) { self.0.on_entry_updated(entry); }
    fn on_entry_deleted(&self, entry_id: &str) { self.0.on_entry_deleted(entry_id); }
}

trait OrElseStr {
    fn or_else(self, f: impl FnOnce() -> Option<String>) -> Option<String>;
    fn unwrap_or_else(self, f: impl FnOnce() -> String) -> String;
}

impl OrElseStr for String {
    fn or_else(self, f: impl FnOnce() -> Option<String>) -> Option<String> {
        if self.is_empty() { f() } else { Some(self) }
    }
    fn unwrap_or_else(self, f: impl FnOnce() -> String) -> String {
        if self.is_empty() { f() } else { self }
    }
}
