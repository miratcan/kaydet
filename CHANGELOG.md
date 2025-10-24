# Changelog

All notable changes to this project will be documented in this file.

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
