use std::collections::HashMap;

pub struct Entry {
    pub entry_id: String,
    pub timestamp: String,
    pub text: String,
    pub tags: Vec<String>,
    pub metadata: HashMap<String, String>,
}

pub trait EventListener {
    fn on_entry_created(&self, entry: &Entry);
    fn on_entry_updated(&self, entry: &Entry);
    fn on_entry_deleted(&self, entry_id: &str);
}

pub struct KaydetCore {
    listeners: Vec<Box<dyn EventListener>>,
}

impl KaydetCore {
    pub fn new() -> KaydetCore {
        KaydetCore {
            listeners: Vec::new(),
        }
    }

    pub fn add_listener(&mut self, listener: Box<dyn EventListener>) {
        self.listeners.push(listener);
    }

    pub fn add_entry(&self, text: &str) -> Entry {
        let entry = Entry::from_text(text);
        for listener in &self.listeners {
            listener.on_entry_created(&entry);
        }
        entry
    }
}

impl Entry {
    pub fn from_text(text: &str) -> Entry {
        let tags = text
            .split_whitespace()
            .filter(|w| w.starts_with('#'))
            .map(|w| w[1..].to_string())
            .collect();

        Entry {
            entry_id: String::new(),
            timestamp: String::new(),
            text: text.to_string(),
            tags,
            metadata: HashMap::new(),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_create_entry() {
        let entry = Entry::from_text("bugün güzel bir gündü #mirat");
        assert_eq!(entry.text, "bugün güzel bir gündü #mirat");
        assert_eq!(entry.tags.len(), 1);
    }

    #[test]
    fn test_parse_tags_from_text() {
        let entry = Entry::from_text("bugün güzel bir gündü #mirat");
        assert_eq!(entry.tags, vec!["mirat"]);
        assert_eq!(entry.text, "bugün güzel bir gündü #mirat");
    }
}
