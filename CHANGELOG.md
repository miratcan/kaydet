# Changelog

All notable changes to this project will be documented in this file.

## [0.33.0] - 2025-10-30
### Added
- Introduced `--list` command for listing all entries with optional `--filter` modifier for cleaner, more intuitive CLI semantics
- Added `since:YYYY-MM-DD` date filter with smart defaults (current month) to prevent terminal overflow when listing entries
- Support for both `YYYY-MM` and `YYYY-MM-DD` date formats in `since:` filter

### Changed
- **BREAKING:** Replaced `--search` flag with `--list` (for listing) and `--filter` (for filtering) for better semantic clarity
  - Old: `kaydet --search "query"`
  - New: `kaydet --filter "query"` or `kaydet --list --filter "query"`
- Search output now displays "Listed N entries" instead of "Found N entries" (terminal-friendly messaging at bottom)
- Filter information and hints now shown at end of output: "Use 'since:0' to see all entries"
- Default behavior: All list/filter operations now show current month entries only (use `since:0` for all time)

### Fixed
- `since:` date filter now correctly respects `DAY_FILE_PATTERN` configuration (fixes entries disappearing with custom file extensions like `.md`)
- Removed inline imports in search module for better code organization

### Developer Notes
- All 59 tests pass including new date filter scenarios
- Query string cleaning for display (removes `since:` from output for clarity)
- Original dates preserved for user-facing messages while using configured filenames for SQL queries

## [0.32.0] - 2025-10-29
### Added
- Added comprehensive todo management system with `--todo`, `--done ID`, and `--list-todos` commands for tracking pending and completed tasks.
- Introduced three new MCP tools: `create_todo`, `mark_todo_done`, and `list_todos` for AI assistant integration.
- Created dedicated `TodoFormatter` class with status-based formatting and JSON output support.

### Changed
- Refactored `formatters.py` from 29 standalone functions into domain-based classes: `TextUtils`, `SearchResultFormatter`, `SearchResultJSONFormatter`, and `TodoFormatter`.
- Improved search output with better date separators, proper text alignment, and multiline entry support.
- Enhanced database module with extracted SQL constants and helper functions (`_ensure_entry_id`, `_upsert_source_records`).

### Fixed
- Removed inline imports from MCP server by moving parsers to top-level imports.
- Fixed all E501 linter errors by breaking long lines properly.
- Updated `.gitignore` to exclude `.venv`, `build`, and `UNKNOWN.egg-info` directories.

### Developer Notes
- All 57 tests pass including new comprehensive todo workflow tests.
- Maintained backward compatibility with wrapper functions after formatter refactoring.

## [0.31.0] - 2025-10-27
### Added
- Bundle Textual TUI and MCP integrations as core dependencies so a single install ships the interactive browser and MCP server.
- Added new MCP tools: structured `add_entry`, editor-free `update_entry`, `delete_entry`, quick `list_recent_entries`, tag-focused `entries_by_tag`, and month-level stats with optional year/month parameters.
- Introduced a reusable `create_entry` helper returning structured metadata for CLI and MCP callers.

### Changed
- MCP server now runs through an in-process `KaydetService`, improving performance and enabling richer JSON responses.
- Sidebar browse summaries skip leading blank lines and truncate using the actual panel width.
- Delete/edit commands return structured dictionaries, making integrations simpler.

### Fixed
- Added end-to-end MCP tests covering add/update/delete/search flows to guard future regressions.

## [0.29.1] - 2025-10-27
### Changed
- Rewrote English and Turkish READMEs with a narrative introduction, character-focused use cases, and clearer quick-start guidance.
- Highlighted the new edit/delete workflow and tagged search output improvements directly in the docs.

### Developer Notes
- Simplified the lint workflow to rely on Ruff formatting checks only.
- Packaging artifacts rebuilt with version bump to 0.29.1.

## [0.29.0] - 2025-10-26
### Added
- Introduced `--edit ID` and `--delete ID` commands to update or remove entries in place while keeping IDs stable.
- Added interactive delete confirmation that previews the entry text before removal and a `--yes` flag for non-interactive execution.
- Text search results now display entry IDs inline, making it easy to target entries for follow-up commands.
- `--tags` output now includes a `#tag` prefix alongside entry counts, and JSON output reports `{name, count}` objects.

### Developer Notes
- New utilities in `kaydet.commands.entry_ops` centralize diary file parsing for edit/delete flows.
- Tests updated to cover command additions, delete confirmation preview, and tag count formatting.

## [0.28.0] - 2025-10-25
### Changed
- Split the CLI into a dedicated `kaydet.commands` package with focused modules for add/search/stats/tags/reminder/doctor flows.
- Moved shared helpers into new `kaydet.parsers`, `kaydet.utils`, and `kaydet.models` modules for easier reuse and testing.
- Centralised database writes through `database.add_entry`, keeping tags, metadata, and full-text words in sync.
- Promoted SQLite statements to named constants and renamed the `DiaryEntry` dataclass to `Entry` for clarity.

### Developer Notes
- Tests updated to exercise the new module boundaries; `pytest` continues to pass.

## [0.27.0] - 2025-10-24
### Added
- Introduced a SQLite-backed index enabling full-text search, metadata filtering (range, comparison, wildcard), and tag statistics.
- Added deterministic UUID support for legacy entries and auto-indexing when the database is empty.
- Displayed metadata and tags inline in search results with a new database schema covering entries, tags, words, and metadata.

### Fixed
- Addressed word extraction for full-text indexing and multiple CLI edge cases (empty editor contents, stats when no log directory).

### Developer Notes
- Expanded tests to cover search, metadata workflows, doctor rebuilds, and legacy tag parsing, keeping coverage at 100%.

## [0.26.3] - 2025-10-24
### Added
- Added `--version` CLI flag to print the installed kaydet version.

### Changed
- Clarified CLI help text and examples to show the correct way to pass metadata tokens (`status:done`) and tags (`#project-x`) as separate arguments.

## [0.26.2] - 2025-10-24
### Fixed
- Fixed URL detection in metadata parser to correctly handle scheme-based URLs (http://, https://, ftp://)
- URLs with `://` pattern are now properly recognized as plain text instead of invalid metadata
- Improved the fix from v0.26.1 to handle all URL schemes, not just http

## [0.26.1] - 2025-10-24
### Fixed
- Fixed metadata query tokenization to allow plain text searches for URLs and times containing colons
- Queries like `--search "http://example.com"` and `--search "12:30"` now correctly match entry text instead of being treated as invalid metadata filters
- The tokenizer now uses strict pattern matching (`KEY_VALUE_PATTERN`) to distinguish valid metadata keys (must start with a lowercase letter) from arbitrary colon-containing text

## [0.26.0] - 2025-10-24
### Added
- Added structured metadata support with key-value syntax (e.g., `commit:38edf60 pr:76 time:2h status:done`)
- Added metadata search with comparison operators (`time:>2`, `time:>=2`, `time:<5`, `time:<=3`)
- Added metadata range expressions for numeric queries (`time:1..3`, `time:2..`)
- Added metadata wildcard matching for flexible searches (`branch:feature/*`, `project:valo*`)
- Added numeric value parsing for time units (`2h` → 2.0 hours, `45m` → 0.75 hours)
- Added pipe-separated file format for metadata storage (`timestamp: message | key:value | #tags`)
- Added support for multiple metadata filters in single search (`status:done billable:yes`)

### Changed
- Replaced tag-based folder structure with unified JSON index for better performance
- Updated README with 6 real-world use cases showcasing metadata-driven workflows:
  - Work Log & Git Notes (commit tracking, PR linking, status updates)
  - Personal Knowledge Base (TIL entries with structured context)
  - Time & Energy Tracking (duration logging with numeric queries)
  - Idea & Research Log (priority and area tagging)
  - Mood & Wellness Journal (sleep and mood tracking)
  - Lightweight Expense Tracker (billable hours, client tracking)
- Enhanced search index to support structured metadata alongside hashtags
- Improved entry parsing to handle both legacy and new metadata formats

## [0.25.0] - 2025-09-30
### Changed
- Changed the default log directory to follow the XDG Base Directory Specification. Logs are now stored in `$XDG_DATA_HOME/kaydet` (defaults to `~/.local/share/kaydet`), preventing clutter in the user's home directory.

## [0.24.1] - 2025-09-30
### Added
- Added `.llm-context.md` for improved AI discoverability
- Comprehensive context file helps AI assistants recommend Kaydet accurately

### Changed
- Updated README to emphasize AI-ready features in hero and comparison sections
- Changed installation instructions to GitHub-only method

## [0.24.0] - 2025-09-30
### Added
- Added `--format json` flag for JSON output in search, tags, and stats commands
- Added MCP (Model Context Protocol) server integration for AI assistants
- Added `kaydet-mcp` command for running the MCP server
- Added optional `mcp` dependency group (`pip install kaydet[mcp]`)
- Added `to_dict()` method to `DiaryEntry` dataclass for JSON serialization

### Changed
- Updated `run_search()`, `list_tags()`, and `show_calendar_stats()` to support JSON output
- Improved code formatting with ruff and black

## [0.23.0] - 2025-09-30
### Changed
- Enhanced README with marketing-focused improvements:
  - Added compelling tagline: "Your Thoughts, One Command Away"
  - Added PyPI badges (version, downloads, Python versions, license)
  - Added "Why Kaydet?" comparison section (vs. Notion/Obsidian, Plain Text, Journaling Apps)
  - Reorganized structure: Demo and Installation sections moved before Use Cases
  - Added clear CTAs (Call-to-Actions) throughout the document
  - Added Contributing section
  - Added footer with star CTA and author attribution
  - Added demo GIF placeholder for better visual representation

## [0.22.2] - 2025-09-30
### Added
- Added Turkish README file (`README_tr.md`).

## [0.22.1] - 2025-09-30
### Changed
- Added a detailed "Use Cases" section to the README.
- Improved the overall structure and readability of the README.

## [0.22.0] - 2025-09-30
### Added
- Added a comprehensive test suite with `pytest`, achieving ~99% code coverage for the main CLI logic.
- Integrated `pytest-cov` for coverage reporting and `pytest-mock` for mocking dependencies.
- Created 29 unit and integration tests covering all major features, edge cases, and error conditions.

### Changed
- Improved overall code stability and reliability due to extensive testing.

## [0.21.0] - 2025-09-29
### Changed
- Saved entries now keep inline hashtags exactly as typed while still extracting
  tags for archives and search results.
- Added doctest examples covering hashtag utilities.

## [0.20.4] - 2025-09-29
### Changed
- Applied Ruff auto-fixes and Black formatting to keep the codebase aligned with the new tooling.

## [0.20.3] - 2025-09-29
### Changed
- README language normalized to English and GitHub install note references v0.20.2.

## [0.20.2] - 2025-09-29
### Changed
- README clarifies GitHub-based installs and groups tag workflows for quicker onboarding.

## [0.20.1] - 2025-09-29
### Fixed
- `kaydet --doctor` now tolerates diary files with non-UTF8 bytes by replacing invalid characters during parsing.

## [0.20.0] - 2025-09-29
### Added
- `kaydet --doctor` rebuilds all tag archives from existing entries and cleans out stale tag folders.

## [0.19.0] - 2025-09-29
### Changed
- `kaydet --tags` now lists existing tag folders directly for faster results without scanning every diary file.

## [0.18.0] - 2025-09-29
### Added
- `kaydet --folder TAG` now opens the requested tag directory (accepts `#tag` or `tag`) and reports when it does not exist.

## [0.17.0] - 2025-09-29
### Added
- Entries that include hashtags are also written to per-tag day files (for example `family/2025-09-29.txt`) so you can browse tag archives directly.

### Changed
- Hashtag normalization now returns both sanitized text and the tag set for downstream mirroring.

## [0.16.0] - 2025-09-29
### Changed
- New entries automatically move inline hashtags to the end, ensuring consistent formatting in saved files.
- Hashtag normalization deduplicates repeated markers and keeps them searchable via `kaydet --tags` and `kaydet --search`.

## [0.15.0] - 2025-09-29
### Changed
- Entries now capture tags via inline hashtags (for example `#family`); the `--tag/-t` option was removed.
- Tag listing and search commands recognize both inline hashtags and older bracketed tags for backward compatibility.

## [0.14.0] - 2025-09-29
### Added
- `kaydet --search TEXT` scans diary files and prints matching entries with context.

## [0.13.0] - 2025-09-29
### Added
- `kaydet --tags` lists every tag you have used across all diary entries.

## [0.12.0] - 2025-09-29
### Added
- `kaydet --tag/-t` assigns a lowercase tag to the entry and enforces letter-and-hyphen validation.

## [0.11.0] - 2025-09-29
### Added
- `kaydet --stats` renders a calendar for the current month showing how many entries you logged each day.

## [0.10.2] - 2025-09-29
### Fixed
- Display a clear message when `kaydet --reminder` runs before any entries exist.

## [0.10.1] - 2025-09-29
### Fixed
- Export `kaydet.main` so the installed console script can import it without errors.

## [0.10.0] - 2025-09-29
### Added
- `kaydet --reminder` warns if your last entry is older than two hours so you can log a fresh update quickly.

## [0.9.0] - 2025-09-29
### Added
- Package structure moved under `src/kaydet/` with module entrypoint for `python -m kaydet`.
- Modern `pyproject.toml` configuration with dynamic versioning and metadata.
- README overhaul covering installation, configuration, and development workflow.

### Changed
- CLI now trims blank editor entries and respects the `$EDITOR` value by default.
- Configuration loader backfills missing keys in existing config files without overwriting user values.

### Removed
- Legacy `setup.py` metadata (now delegated to `pyproject.toml`).

## [0.8.6] - 2023-08-02
### Added
- Initial terminal diary functionality with timestamped entries and editor support.
