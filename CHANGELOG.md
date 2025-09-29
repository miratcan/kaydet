# Changelog

All notable changes to this project will be documented in this file.

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
