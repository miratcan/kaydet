"""Central service layer for Kaydet."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from . import database
from .commands.add import EmptyEntryError, create_entry
from .commands.delete import delete_entry_command
from .commands.edit import update_entry_inline
from .commands.search import (
    build_search_query,
    load_matches,
    tokenize_query,
)
from .commands.stats import collect_month_counts
from .commands.todo import done_command
from .database import INDEX_FILENAME
from .indexing import rebuild_index_if_empty
from .parsers import parse_day_entries, resolve_entry_date
from .sync import sync_modified_day_files
from .utils import entry_id_sort_key, load_config

# Rust core — paralel olarak çalışır, zamanla Python'un yerini alacak
try:
    import kaydet_core_rs as _rust_core
    _RUST_AVAILABLE = True
except ImportError:
    _rust_core = None
    _RUST_AVAILABLE = False


@dataclass
class KaydetService:
    """Programmatic interface over Kaydet command logic."""

    config: Any
    config_dir: Path
    storage_dir: Path
    conn: Any
    _rust: Any = None  # kaydet_core_rs.KaydetCore instance

    @classmethod
    def initialize(cls) -> KaydetService:
        (
            config,
            _config_path,
            config_dir,
            storage_dir,
            index_dir,
        ) = load_config()
        rust = None
        if _RUST_AVAILABLE:
            try:
                rust = _rust_core.KaydetCore(str(storage_dir))
            except Exception:
                pass  # Rust core başlatılamazsa Python devam eder

        # SQLite: Rust varken sadece sync_log için lazım (sync_client/server).
        # Rust yoksa index cache olarak da kullanılıyor.
        db_path = index_dir / INDEX_FILENAME
        conn = database.get_db_connection(db_path)
        database.initialize_database(conn)

        return cls(
            config=config,
            config_dir=config_dir,
            storage_dir=storage_dir,
            conn=conn,
            _rust=rust,
        )

    def _ensure_index(self, now: datetime) -> None:
        sync_modified_day_files(
            self.conn, self.storage_dir, self.config, now, config_dir=self.config_dir
        )
        rebuild_index_if_empty(
            self.conn, self.storage_dir, self.config, now
        )

    def add_entry(
        self,
        *,
        text: str,
        metadata: dict[str, str] | None = None,
        tags: Iterable[str] | None = None,
        timestamp: str | None = None,
        secret: str | None = None,
        at: datetime | None = None,
        entry_id: str | None = None,
    ) -> dict[str, Any]:
        # TODO: at, secret henüz Rust'ta yok
        if secret:
            # secrets Python'da kalıyor şimdilik
            return self._add_entry_python(
                text=text, metadata=metadata, tags=tags,
                timestamp=timestamp, secret=secret, at=at,
                entry_id=entry_id,
            )

        if self._rust:
            try:
                entry = self._rust.add_entry(text)
                return {
                    "success": True,
                    "entry_id": entry.entry_id,
                    "timestamp": entry.timestamp,
                    "day_file": str(self.storage_dir / f"{entry.date}.txt"),
                    "attachments": [],
                }
            except Exception as error:
                return {"success": False, "error": str(error)}

        return self._add_entry_python(
            text=text, metadata=metadata, tags=tags,
            timestamp=timestamp, secret=secret, at=at,
            entry_id=entry_id,
        )

    def _add_entry_python(
        self,
        *,
        text: str,
        metadata: dict[str, str] | None = None,
        tags: Iterable[str] | None = None,
        timestamp: str | None = None,
        secret: str | None = None,
        at: datetime | None = None,
        entry_id: str | None = None,
    ) -> dict[str, Any]:
        now = at or datetime.now()
        metadata = metadata or {}
        tags = list(tags or [])
        if timestamp and not at:
            import re as _re
            if not _re.match(r"^\d{2}:\d{2}$", timestamp):
                return {
                    "success": False,
                    "error": f"Invalid timestamp format '{timestamp}'. Expected HH:MM.",
                }
            now = now.replace(
                hour=int(timestamp[:2]),
                minute=int(timestamp[3:]),
            )

        secret_password = None
        if secret:
            from .utils import get_secret_password
            secret_password = get_secret_password(self.config_dir)
            if not secret_password:
                return {
                    "success": False,
                    "error": (
                        "No secret password configured. "
                        "Run 'kaydet sync setup' or use --secret "
                        "from the CLI first."
                    ),
                }

        try:
            result = create_entry(
                raw_entry=text,
                metadata=metadata,
                explicit_tags=tags,
                config=self.config,
                config_dir=self.config_dir,
                storage_dir=self.storage_dir,
                now=now,
                conn=self.conn,
                secret_text=secret,
                secret_password=secret_password,
                entry_id=entry_id,
            )
        except EmptyEntryError as error:
            return {"success": False, "error": str(error)}
        return {"success": True, **result}

    def delete_entry(self, entry_id: str) -> dict[str, Any]:
        if self._rust:
            try:
                self._rust.delete_entry(entry_id)
                return {"success": True, "entry_id": entry_id}
            except Exception as error:
                return {"success": False, "error": str(error)}
        now = datetime.now()
        result = delete_entry_command(
            self.conn, self.storage_dir, self.config,
            entry_id, assume_yes=True, now=now,
        )
        if result is None:
            return {"success": False, "error": "Entry not deleted."}
        return {"success": True, **result}

    def update_entry(
        self,
        entry_id: str,
        *,
        text: str | None = None,
        metadata: dict[str, str] | None = None,
        tags: Iterable[str] | None = None,
        timestamp: str | None = None,
    ) -> dict[str, Any]:
        if self._rust and text is not None:
            try:
                self._rust.update_entry(entry_id, text)
                return {"success": True, "entry_id": entry_id}
            except Exception as error:
                return {"success": False, "error": str(error)}
        now = datetime.now()
        result = update_entry_inline(
            self.conn, self.storage_dir, self.config,
            entry_id, text=text, metadata=metadata,
            tags=tags, timestamp=timestamp, now=now,
        )
        if result is None:
            return {"success": False, "error": "Entry not updated."}
        return {"success": True, **result}

    def search_entries(
        self, query: str = "", *, limit: int = 0
    ) -> dict[str, Any]:
        if self._rust:
            entries = self._rust.search_entries(query, limit=limit)
            matches = [
                {
                    "entry_id": e.entry_id,
                    "date": e.date,
                    "timestamp": e.timestamp,
                    "text": e.text,
                    "tags": e.tags,
                    "metadata": e.metadata,
                }
                for e in entries
            ]
            return {"success": True, "query": query, "matches": matches, "total": len(matches)}
        now = datetime.now()
        self._ensure_index(now)
        (
            include_text, exclude_text,
            include_meta, exclude_meta,
            include_tags, exclude_tags,
        ) = tokenize_query(query) if query else ([], [], [], [], [], [])
        has_filters = any([include_text, exclude_text, include_meta, exclude_meta, include_tags, exclude_tags])
        if has_filters:
            sql_query, params = build_search_query(include_text, exclude_text, include_meta, exclude_meta, include_tags, exclude_tags)
        else:
            sql_query = "SELECT source_file, id FROM entries ORDER BY id DESC"
            params = []
        if limit > 0:
            sql_query += " LIMIT ?"
            params.append(limit)
        cursor = self.conn.cursor()
        try:
            cursor.execute(sql_query, params)
        except Exception as error:
            return {"success": False, "error": f"Database query failed: {error}"}
        locations = cursor.fetchall()
        if not locations:
            return {"success": True, "query": query, "matches": [], "total": 0}
        matches = load_matches(locations, self.storage_dir, self.config)
        matches.sort(key=lambda entry: entry_id_sort_key(entry.entry_id), reverse=True)
        payload = [match.to_dict() for match in matches]
        return {"success": True, "query": query, "matches": payload, "total": len(payload)}

    def get_entry(self, entry_id: str) -> dict[str, Any]:
        """Return a single entry by its identifier."""
        if self._rust:
            e = self._rust.get_entry(entry_id)
            if e is None:
                return {"success": False, "error": f"Entry {entry_id} not found."}
            entry_dict = {
                "entry_id": e.entry_id,
                "date": e.date,
                "timestamp": e.timestamp,
                "text": e.text,
                "tags": e.tags,
                "metadata": e.metadata,
            }
            # secrets hala Python'da
            from .secrets import decrypt_secret, get_secret
            from .utils import get_secret_password
            encrypted = get_secret(entry_id, self.storage_dir)
            if encrypted:
                password = get_secret_password(self.config_dir)
                if password:
                    try:
                        entry_dict["secret"] = decrypt_secret(encrypted, password)
                    except Exception:
                        entry_dict["secret"] = None
                        entry_dict["secret_error"] = "Decryption failed"
            return {"success": True, "entry": entry_dict}

        now = datetime.now()
        self._ensure_index(now)
        cursor = self.conn.cursor()
        cursor.execute("SELECT source_file FROM entries WHERE id = ?", (entry_id,))
        result = cursor.fetchone()
        if result is None:
            return {"success": False, "error": f"Entry {entry_id} not found."}
        locations = [(result[0], entry_id)]
        matches = load_matches(locations, self.storage_dir, self.config)
        if not matches:
            return {"success": False, "error": f"Entry {entry_id} not found."}
        entry_dict = matches[0].to_dict()
        from .secrets import decrypt_secret, get_secret
        from .utils import get_secret_password
        encrypted = get_secret(entry_id, self.storage_dir)
        if encrypted:
            password = get_secret_password(self.config_dir)
            if password:
                try:
                    entry_dict["secret"] = decrypt_secret(encrypted, password)
                except Exception:
                    entry_dict["secret"] = None
                    entry_dict["secret_error"] = "Decryption failed"
        return {"success": True, "entry": entry_dict}

    def list_tags(self) -> dict[str, Any]:
        if self._rust:
            from collections import Counter
            all_entries = self._rust.all_entries()
            counts = Counter(tag for e in all_entries for tag in e.tags)
            tags = [{"tag": t, "count": c} for t, c in sorted(counts.items())]
            return {"success": True, "tags": tags}
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT tag_name, COUNT(*) FROM tags GROUP BY tag_name ORDER BY tag_name"
        )
        rows = cursor.fetchall()
        tags = [{"tag": name, "count": count} for name, count in rows]
        return {"success": True, "tags": tags}

    @staticmethod
    def _normalize_directory_tag(name: str) -> str:
        """Normalize a directory name into a tag-friendly slug."""
        slug = re.sub(r"[^a-z0-9\-]+", "-", name.lower())
        return slug.strip("-")

    def suggest_tags(
        self, directory: Path | str | None = None
    ) -> dict[str, Any]:
        """Suggest tags based on the active project directory."""
        inspected_dir = (
            Path(directory).expanduser()
            if directory is not None
            else Path.cwd()
        )

        if not inspected_dir.exists():
            return {
                "success": False,
                "error": f"Directory does not exist: {inspected_dir}",
            }
        if not inspected_dir.is_dir():
            return {
                "success": False,
                "error": f"Not a directory: {inspected_dir}",
            }

        tags_file = inspected_dir / ".kaydet.tags"
        if tags_file.is_file():
            try:
                lines = tags_file.read_text(encoding="utf-8").splitlines()
            except OSError as error:  # pragma: no cover - filesystem edge case
                return {
                    "success": False,
                    "error": f"Failed to read {tags_file}: {error}",
                }
            tags = [
                line.strip()
                for line in lines
                if line.strip() and not line.strip().startswith("#")
            ]
            if tags:
                return {
                    "success": True,
                    "suggested_tags": tags,
                    "source": "tags_file",
                    "directory": str(inspected_dir),
                }

        normalized = self._normalize_directory_tag(inspected_dir.name)
        if not normalized:
            return {
                "success": False,
                "error": (
                    "Unable to derive tag suggestion from directory name. "
                    "Create a .kaydet.tags file to define tags explicitly."
                ),
            }
        return {
            "success": True,
            "suggested_tags": [normalized],
            "source": "directory_name",
            "directory": str(inspected_dir),
        }

    def get_stats(
        self, *, year: int | None = None, month: int | None = None
    ) -> dict[str, Any]:
        if self._rust:
            result = self._rust.get_stats(year, month)
            return {"success": True, **result}
        now = datetime.now()
        target_year = year or now.year
        target_month = month or now.month
        counts = collect_month_counts(
            self.storage_dir,
            self.config,
            target_year,
            target_month,
        )
        total = sum(counts.values())
        return {
            "success": True,
            "year": target_year,
            "month": target_month,
            "days": counts,
            "total_entries": total,
        }

    def create_todo(
        self, description: str, metadata: dict[str, str] | None = None
    ) -> dict[str, Any]:
        """Create a new todo entry with status:pending and #todo tag."""
        if self._rust:
            try:
                text = f"{description} #todo status:pending"
                entry = self._rust.add_entry(text)
                return {
                    "success": True,
                    "entry_id": entry.entry_id,
                    "timestamp": entry.timestamp,
                    "day_file": str(self.storage_dir / f"{entry.date}.txt"),
                }
            except Exception as error:
                return {"success": False, "error": str(error)}

        now = datetime.now()
        metadata = metadata or {}
        metadata["status"] = "pending"

        try:
            result = create_entry(
                raw_entry=description,
                metadata=metadata,
                explicit_tags=["todo"],
                config=self.config,
                config_dir=self.config_dir,
                storage_dir=self.storage_dir,
                now=now,
                conn=self.conn,
            )
        except EmptyEntryError as error:
            return {"success": False, "error": str(error)}
        return {"success": True, **result}

    def mark_todo_done(self, entry_id: str) -> dict[str, Any]:
        """Mark a todo entry as done by updating its status."""
        if self._rust:
            try:
                self._rust.mark_todo_done(entry_id)
                return {"success": True, "entry_id": entry_id, "message": f"Todo {entry_id} marked as done"}
            except Exception as error:
                return {"success": False, "error": str(error)}
        now = datetime.now()
        try:
            done_command(
                self.conn,
                self.storage_dir,
                self.config,
                entry_id,
                now,
            )
            return {
                "success": True,
                "entry_id": entry_id,
                "message": f"Todo {entry_id} marked as done",
            }
        except Exception as error:
            return {"success": False, "error": str(error)}

    def list_todos(
        self,
        *,
        status: str | None = "pending",
        filter_query: str | None = None,
    ) -> dict[str, Any]:
        """List todos, optionally filtered by status and/or search query.

        Args:
            status: Filter by status ('pending', 'done', or None for all).
            filter_query: Optional search query to further narrow results.
        """
        if self._rust:
            entries = self._rust.list_todos(status=status)
            if filter_query:
                q = filter_query.lower()
                entries = [e for e in entries if q in e.text.lower()]
            todos = [
                {
                    "id": e.entry_id,
                    "date": e.date,
                    "timestamp": e.timestamp,
                    "status": e.metadata.get("status", "pending"),
                    "completed_at": e.metadata.get("completed_at", ""),
                    "description": e.text.split("\n")[0] if e.text else "(no description)",
                }
                for e in entries
            ]
            return {"success": True, "todos": todos}
        # LEGACY — Rust yoksa Python devam eder
        now = datetime.now()
        self._ensure_index(now)

        if filter_query:
            combined_query = f"{filter_query} #todo"
            (
                include_text,
                exclude_text,
                include_meta,
                exclude_meta,
                include_tags,
                exclude_tags,
            ) = tokenize_query(combined_query)

            sql_query, params = build_search_query(
                include_text,
                exclude_text,
                include_meta,
                exclude_meta,
                include_tags,
                exclude_tags,
            )
            cursor = self.conn.cursor()
            cursor.execute(sql_query, params)
            results = cursor.fetchall()
        else:
            cursor = self.conn.cursor()
            if status == "pending":
                cursor.execute(
                    "SELECT DISTINCT e.id, e.source_file "
                    "FROM entries e "
                    "JOIN tags t ON e.id = t.entry_id "
                    "LEFT JOIN metadata m ON e.id = m.entry_id "
                    "AND m.meta_key = 'status' "
                    "WHERE t.tag_name = 'todo' "
                    "AND COALESCE(m.meta_value, 'pending') != 'done' "
                    "ORDER BY e.source_file, e.id"
                )
            elif status == "done":
                cursor.execute(
                    "SELECT DISTINCT e.id, e.source_file "
                    "FROM entries e "
                    "JOIN tags t ON e.id = t.entry_id "
                    "JOIN metadata m ON e.id = m.entry_id "
                    "AND m.meta_key = 'status' "
                    "WHERE t.tag_name = 'todo' "
                    "AND m.meta_value = 'done' "
                    "ORDER BY e.source_file, e.id"
                )
            else:
                cursor.execute(
                    "SELECT DISTINCT e.id, e.source_file "
                    "FROM entries e "
                    "JOIN tags t ON e.id = t.entry_id "
                    "WHERE t.tag_name = 'todo' "
                    "ORDER BY e.source_file, e.id"
                )
            results = cursor.fetchall()

        if not results:
            return {"success": True, "todos": []}

        todos = []
        for row in results:
            # build_search_query SELECT returns (source_file, id) — see
            # SELECT_MATCHES_TEMPLATE in commands/search.py.
            # Direct queries here use (id, source_file).
            # Unpack explicitly to avoid silent index errors on refactoring.
            if filter_query:
                source_file: str = row[0]
                entry_id: str = str(row[1])
            else:
                entry_id = str(row[0])
                source_file = row[1]
            day_file = self.storage_dir / source_file
            if not day_file.exists():
                continue

            day_file_pattern = self.config.get("DAY_FILE_PATTERN", "")
            entry_date = resolve_entry_date(day_file, day_file_pattern)
            entries = parse_day_entries(day_file, entry_date)

            for entry in entries:
                if entry.entry_id == str(entry_id):
                    entry_status = entry.metadata.get("status", "pending")
                    if status and filter_query and entry_status != status:
                        break
                    completed_at = entry.metadata.get("completed_at", "")
                    description = (
                        entry.lines[0] if entry.lines else "(no description)"
                    )

                    date_str = (
                        entry.day.isoformat() if entry.day else "unknown"
                    )
                    todos.append(
                        {
                            "id": entry_id,
                            "date": date_str,
                            "timestamp": entry.timestamp,
                            "status": entry_status,
                            "completed_at": completed_at,
                            "description": description,
                        }
                    )
                    break

        return {"success": True, "todos": todos}
