# Release Notes - Kaydet v0.27.0

## 🎉 Major Feature: SQLite Index & Advanced Search

This release introduces a powerful SQLite-based indexing system that dramatically improves search capabilities and enables advanced filtering.

## ✨ New Features

### SQLite Database Index
- **Full-text search** with word-level indexing
- **Metadata filtering** with range and wildcard support (e.g., `time:2..4h`, `status:done`)
- **Tag-based search** with automatic indexing
- **Deterministic UUIDs** for legacy entries (stable across index rebuilds)

### Enhanced Search
- 🔍 **Auto-indexing**: Automatically rebuilds index when searching empty database
- 📊 **Metadata display**: Search results show metadata and tags inline
- 🏷️ **Tag statistics**: `--doctor` command shows tag counts
- 🔗 **Legacy format support**: Works with old diary files without UUIDs

### Database Schema
```
entries   → Core entry metadata (UUID, file, timestamp)
tags      → Tag associations with entries
words     → Full-text search index
metadata  → Key-value pairs with numeric indexing
```

## 🚀 Usage Examples

### Search with Metadata Filtering
```bash
# Find work entries that took 2-4 hours
kaydet --search "#work time:2..4h"

# Find entries with specific status
kaydet --search "status:done"

# Wildcard metadata search
kaydet --search "branch:feature/*"
```

### Rebuild Index
```bash
# Rebuild index from all diary files
kaydet --doctor
# Output: Rebuilt search index for 145 entries.
#         Tags: #work: 89, #personal: 34, #health: 22
```

### Search Results with Metadata
```
2025-10-24 14:30 Fixed authentication bug | commit:38edf60 status:done time:2h | #work #urgent
```

## 🐛 Bug Fixes

- Fixed word extraction regex for proper full-text indexing
- Fixed f-string formatting in search results and doctor output
- Fixed empty editor content handling
- Fixed reminder to only check .txt diary files
- Fixed stats command when log directory doesn't exist
- Added missing imports (json, sqlite3, hashlib)

## 🔄 Breaking Changes

**None!** Fully backward compatible with existing diary files.

- Old entries without UUIDs get deterministic UUIDs automatically
- Both `(tag)` and `[tag]` legacy formats supported
- Existing workflows continue to work unchanged

## 📈 Performance Improvements

- Search queries use indexed SQL lookups (instant results)
- Reduced CLI file size: 840 lines (from 1264, -33%)
- Efficient word indexing with deduplication

## 🧪 Testing

- **100% test coverage**: All 33 tests passing
- Comprehensive search, metadata, and legacy format tests
- Auto-indexing and multiline entry tests

## 📦 Technical Details

### File Changes
- `src/kaydet/cli.py`: Refactored search and indexing logic
- `src/kaydet/database.py`: New module for SQLite operations
- `requirements.txt`: Updated dependencies

### Deterministic UUIDs
Legacy entries generate consistent UUIDs using:
```python
SHA256(filename + timestamp + first_line)[:22]
```

## 🔮 What's Next

Future improvements planned:
- CLI refactoring: Split large cli.py into smaller modules
- Enhanced metadata types (dates, priorities)
- Export functionality (JSON, Markdown)

## 🙏 Contributors

This release was developed with the assistance of Claude (Anthropic).

---

**Full Changelog**: https://github.com/mirat/kaydet/compare/v0.26.3...v0.27.0
