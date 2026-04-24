// FileSystem trait — platform adapter
//
// Core accepts this trait in its constructor — any implementation works.
// NativeFs: real disk I/O
// MemoryFs: in-memory, no disk (used in tests)

use std::collections::HashMap;

#[derive(Debug)]
pub enum FsError {
    NotFound(String),
    PermissionDenied(String),
    IoError(String),
}

impl std::fmt::Display for FsError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            FsError::NotFound(s) => write!(f, "not found: {}", s),
            FsError::PermissionDenied(s) => write!(f, "permission denied: {}", s),
            FsError::IoError(s) => write!(f, "io error: {}", s),
        }
    }
}

pub type FsResult<T> = Result<T, FsError>;

pub trait FileSystem: Send + Sync {
    // --- day files ---
    fn read_day(&self, date: &str) -> FsResult<String>;
    fn write_day(&self, date: &str, content: &str) -> FsResult<()>;
    fn list_days(&self) -> FsResult<Vec<String>>;

    // --- attachments ---
    fn read_attachment(&self, filename: &str) -> FsResult<Vec<u8>>;
    fn write_attachment(&self, filename: &str, data: &[u8]) -> FsResult<()>;
    fn list_attachments(&self) -> FsResult<Vec<String>>;
    fn attachment_exists(&self, filename: &str) -> bool;
}

// ---------------------------------------------------------------------------
// MemoryFs — in-memory, no real disk (for tests)
// ---------------------------------------------------------------------------

pub struct MemoryFs {
    days: Mutex<HashMap<String, String>>,
    attachments: Mutex<HashMap<String, Vec<u8>>>,
}

use std::sync::Mutex;

impl MemoryFs {
    pub fn new() -> MemoryFs {
        MemoryFs {
            days: Mutex::new(HashMap::new()),
            attachments: Mutex::new(HashMap::new()),
        }
    }
}

impl FileSystem for MemoryFs {
    fn read_day(&self, date: &str) -> FsResult<String> {
        self.days
            .lock()
            .unwrap()
            .get(date)
            .cloned()
            .ok_or_else(|| FsError::NotFound(date.to_string()))
    }

    fn write_day(&self, date: &str, content: &str) -> FsResult<()> {
        self.days
            .lock()
            .unwrap()
            .insert(date.to_string(), content.to_string());
        Ok(())
    }

    fn list_days(&self) -> FsResult<Vec<String>> {
        let mut days: Vec<String> = self.days.lock().unwrap().keys().cloned().collect();
        days.sort();
        Ok(days)
    }

    fn read_attachment(&self, filename: &str) -> FsResult<Vec<u8>> {
        self.attachments
            .lock()
            .unwrap()
            .get(filename)
            .cloned()
            .ok_or_else(|| FsError::NotFound(filename.to_string()))
    }

    fn write_attachment(&self, filename: &str, data: &[u8]) -> FsResult<()> {
        self.attachments
            .lock()
            .unwrap()
            .insert(filename.to_string(), data.to_vec());
        Ok(())
    }

    fn list_attachments(&self) -> FsResult<Vec<String>> {
        let mut names: Vec<String> = self.attachments.lock().unwrap().keys().cloned().collect();
        names.sort();
        Ok(names)
    }

    fn attachment_exists(&self, filename: &str) -> bool {
        self.attachments.lock().unwrap().contains_key(filename)
    }
}

// ---------------------------------------------------------------------------
// NativeFs — real disk I/O
// ---------------------------------------------------------------------------

pub struct NativeFs {
    storage_dir: std::path::PathBuf,
}

impl NativeFs {
    pub fn new(storage_dir: &str) -> NativeFs {
        NativeFs {
            storage_dir: std::path::PathBuf::from(storage_dir),
        }
    }

    fn attachments_dir(&self) -> std::path::PathBuf {
        self.storage_dir.join("attachments")
    }
}

impl FileSystem for NativeFs {
    fn read_day(&self, date: &str) -> FsResult<String> {
        let path = self.storage_dir.join(format!("{}.txt", date));
        std::fs::read_to_string(&path)
            .map_err(|e| FsError::IoError(e.to_string()))
    }

    fn write_day(&self, date: &str, content: &str) -> FsResult<()> {
        let path = self.storage_dir.join(format!("{}.txt", date));
        let tmp_path = self.storage_dir.join(format!(".{}.tmp", date));
        std::fs::write(&tmp_path, content)
            .map_err(|e| FsError::IoError(e.to_string()))?;
        std::fs::rename(&tmp_path, &path)
            .map_err(|e| FsError::IoError(e.to_string()))
    }

    fn list_days(&self) -> FsResult<Vec<String>> {
        let mut days = Vec::new();
        let entries = std::fs::read_dir(&self.storage_dir)
            .map_err(|e| FsError::IoError(e.to_string()))?;

        for entry in entries.flatten() {
            let name = entry.file_name().to_string_lossy().to_string();
            if name.ends_with(".txt") && name.len() == 14 {
                // "2026-04-19.txt" = 14 chars
                days.push(name[..10].to_string());
            }
        }
        days.sort();
        Ok(days)
    }

    fn read_attachment(&self, filename: &str) -> FsResult<Vec<u8>> {
        let path = self.attachments_dir().join(filename);
        std::fs::read(&path)
            .map_err(|e| FsError::IoError(e.to_string()))
    }

    fn write_attachment(&self, filename: &str, data: &[u8]) -> FsResult<()> {
        let dir = self.attachments_dir();
        std::fs::create_dir_all(&dir)
            .map_err(|e| FsError::IoError(e.to_string()))?;
        std::fs::write(dir.join(filename), data)
            .map_err(|e| FsError::IoError(e.to_string()))
    }

    fn list_attachments(&self) -> FsResult<Vec<String>> {
        let dir = self.attachments_dir();
        if !dir.exists() {
            return Ok(Vec::new());
        }
        let mut names = Vec::new();
        for entry in std::fs::read_dir(&dir).map_err(|e| FsError::IoError(e.to_string()))?.flatten() {
            names.push(entry.file_name().to_string_lossy().to_string());
        }
        names.sort();
        Ok(names)
    }

    fn attachment_exists(&self, filename: &str) -> bool {
        self.attachments_dir().join(filename).exists()
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_memory_fs_day_roundtrip() {
        let fs = MemoryFs::new();
        fs.write_day("2026-04-19", "14:25 [d1]: test #mirat").unwrap();
        let content = fs.read_day("2026-04-19").unwrap();
        assert_eq!(content, "14:25 [d1]: test #mirat");
    }

    #[test]
    fn test_memory_fs_not_found() {
        let fs = MemoryFs::new();
        assert!(fs.read_day("2026-01-01").is_err());
    }

    #[test]
    fn test_memory_fs_attachment_roundtrip() {
        let fs = MemoryFs::new();
        let data = b"fake image bytes";
        fs.write_attachment("d1_photo.jpg", data).unwrap();
        assert!(fs.attachment_exists("d1_photo.jpg"));
        assert_eq!(fs.read_attachment("d1_photo.jpg").unwrap(), data);
    }

    #[test]
    fn test_memory_fs_list_days_sorted() {
        let fs = MemoryFs::new();
        fs.write_day("2026-04-20", "entry").unwrap();
        fs.write_day("2026-04-18", "entry").unwrap();
        fs.write_day("2026-04-19", "entry").unwrap();
        let days = fs.list_days().unwrap();
        assert_eq!(days, vec!["2026-04-18", "2026-04-19", "2026-04-20"]);
    }
}
