# Release Notes - Kaydet v0.28.0

## 🔧 CLI Architecture Overhaul

Kaydet’s CLI has been decomposed into a dedicated `kaydet.commands` package, giving each flow (add, search, stats, tags, reminder, doctor) its own focused module. The CLI entrypoint now simply routes to these command modules, dramatically reducing the size of `cli.py` and making future features much easier to add.

## ✨ Highlights

- Introduced `kaydet.commands` with purpose-built modules for `add`, `search`, `doctor`, `stats`, `reminder`, and `tags`.
- Added `kaydet.parsers`, `kaydet.utils`, and `kaydet.models` to house shared parsing helpers, reusable utilities, and the `DiaryEntry` dataclass.
- Centralised SQLite writes through `database.add_entry`, ensuring tags, metadata, and full-text words stay in sync regardless of how entries are created.
- Maintained full backwards compatibility—existing workflows, metadata syntax, and search capabilities continue to work unchanged.

## 🧰 Developer Experience

- `open_editor`, config helpers, and diary iteration now live in `kaydet.utils`, giving integrators a clean import surface.
- Tests updated to exercise the new module boundaries, keeping the CLI regression suite green.
- The new layout unlocks incremental enhancements (e.g. new subcommands or output formats) without touching the entire CLI.

## 🧪 Testing

- Full pytest suite passes (`tests/test_cli.py`), covering add/search/stats/doctor/reminder behaviours against the refactored modules.

---

**Full Changelog**: https://github.com/mirat/kaydet/compare/v0.27.0...v0.28.0
