# Changelog

All notable changes to this project will be documented in this file.

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
