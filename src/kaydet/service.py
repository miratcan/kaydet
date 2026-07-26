"""Central service layer for Kaydet diary application."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterable

from . import database
from .commands.add import EmptyEntryError, add_entry_command, create_entry
from .commands.delete import delete_entry_command
from .commands.doctor import doctor_command
from .commands.edit import edit_entry_command, update_entry_inline
from .commands.git_sync import git_init, git_status, git_sync
from .commands.search import (
    build_search_query,
    load_matches,
    search_command,
    tags_command,
    tokenize_query,
)
from .commands.stats import collect_month_counts, stats_command
from .commands.todo import done_command, todo_command
from .indexing import rebuild_index_if_empty
from .parsers import parse_day_entries, resolve_entry_date
from .sums import format_sums_payload
from .sync import sync_modified_diary_files
from .utils import load_config


@dataclass
class KaydetService:
    """Programmatic interface over Kaydet command logic.

    CLI and MCP both route through this layer so behaviour stays aligned.
    """

    config: Any
    config_path: Path
    config_dir: Path
    log_dir: Path
    index_dir: Path
    conn: Any

    @classmethod
    def initialize(cls) -> KaydetService:
        (
            config,
            config_path,
            config_dir,
            storage_dir,
            index_dir,
        ) = load_config()
        db_path = index_dir / database.INDEX_FILENAME
        conn = database.get_db_connection(db_path)
        database.initialize_database(conn)
        return cls(
            config=config,
            config_path=config_path,
            config_dir=config_dir,
            log_dir=storage_dir,
            index_dir=index_dir,
            conn=conn,
        )

    def _ensure_index(self, now: datetime | None = None) -> datetime:
        moment = now or datetime.now()
        sync_modified_diary_files(
            self.conn, self.log_dir, self.config, moment
        )
        rebuild_index_if_empty(
            self.conn, self.log_dir, self.config, moment
        )
        return moment

    # --- Doctor / git -------------------------------------------------

    def doctor(self, now: datetime | None = None) -> dict[str, Any]:
        moment = now or datetime.now()
        return doctor_command(
            self.conn, self.log_dir, self.config, moment
        )

    def git_init(
        self, remote_url: str | None = None
    ) -> dict[str, Any]:
        return git_init(self.log_dir, remote_url=remote_url)

    def git_sync(self) -> dict[str, Any]:
        return git_sync(self.log_dir)

    def git_status(self) -> dict[str, Any]:
        return git_status(self.log_dir)

    # --- Entries ------------------------------------------------------

    def add_entry(
        self,
        *,
        text: str,
        metadata: dict[str, str] | None = None,
        tags: Iterable[str] | None = None,
        timestamp: str | None = None,
    ) -> dict[str, Any]:
        now = datetime.now()
        metadata = metadata or {}
        tags = list(tags or [])
        if timestamp:
            now = now.replace(
                hour=int(timestamp[:2]),
                minute=int(timestamp[3:]),
            )

        try:
            result = create_entry(
                raw_entry=text,
                metadata=metadata,
                explicit_tags=tags,
                config=self.config,
                config_dir=self.config_dir,
                log_dir=self.log_dir,
                now=now,
                conn=self.conn,
            )
        except EmptyEntryError as error:
            return {"success": False, "error": str(error)}
        return {"success": True, **result}

    def add_from_cli(
        self, args: Any, now: datetime | None = None
    ) -> dict[str, Any]:
        """Add an entry from argparse Namespace (attach/editor/--at)."""
        moment = now or datetime.now()
        return add_entry_command(
            args,
            self.config,
            self.config_dir,
            self.log_dir,
            moment,
            self.conn,
        )

    def delete_entry(
        self, entry_id: int, *, assume_yes: bool = True
    ) -> dict[str, Any]:
        now = datetime.now()
        try:
            result = delete_entry_command(
                self.conn,
                self.log_dir,
                self.config,
                entry_id,
                assume_yes=assume_yes,
                now=now,
            )
        except (ValueError, FileNotFoundError) as error:
            return {
                "success": False,
                "error": str(error),
                "message": str(error),
            }
        if result is None:
            return {"success": False, "error": "Entry not deleted."}
        if "success" in result:
            return result
        return {"success": True, **result}

    def update_entry(
        self,
        entry_id: int,
        *,
        text: str | None = None,
        metadata: dict[str, str] | None = None,
        tags: Iterable[str] | None = None,
        timestamp: str | None = None,
    ) -> dict[str, Any]:
        now = datetime.now()
        result = update_entry_inline(
            self.conn,
            self.log_dir,
            self.config,
            entry_id,
            text=text,
            metadata=metadata,
            tags=tags,
            timestamp=timestamp,
            now=now,
        )
        if result is None:
            return {"success": False, "error": "Entry not updated."}
        return {"success": True, **result}

    def edit_in_editor(
        self, entry_id: int, now: datetime | None = None
    ) -> None:
        """Open the configured editor for an entry (prints status)."""
        moment = now or datetime.now()
        edit_entry_command(
            self.conn, self.log_dir, self.config, entry_id, moment
        )

    def query(
        self,
        query: str,
        *,
        allow_empty: bool = False,
        limit: int | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Search returning Entry objects (for CLI rendering)."""
        self._ensure_index(now)
        return search_command(
            self.conn,
            self.log_dir,
            self.config,
            query,
            allow_empty=allow_empty,
            limit=limit,
        )

    def search_entries(
        self, query: str, *, limit: int | None = 50
    ) -> dict[str, Any]:
        """Search entries as dicts. Default limit=50 for MCP/token budgets.

        Pass ``limit=0`` or ``limit=None`` for unlimited results.
        """
        result = self.query(query, limit=limit)
        if not result.get("success"):
            return result

        matches = result["matches"]
        matches = sorted(
            matches,
            key=lambda entry: int(entry.entry_id or 0),
            reverse=True,
        )
        payload = [match.to_dict() for match in matches]
        total = result.get("total", len(payload))
        return {
            "success": True,
            "query": query,
            "matches": payload,
            "total": total,
            "shown": len(payload),
            "limit": result.get("limit"),
            "truncated": result.get("truncated", False),
        }

    def summarize_entries(self, query: str) -> dict[str, Any]:
        """Search entries and return summed numeric metadata."""
        result = self.query(query)
        if not result.get("success"):
            return result

        matches = result["matches"]
        if not matches:
            return {
                "success": True,
                "query": query,
                "sums": {},
                "sums_display": {},
                "total": 0,
            }

        payload = format_sums_payload(matches)
        return {
            "success": True,
            "query": query,
            "sums": payload["sums"],
            "sums_display": payload["sums_display"],
            "total": payload["total_entries"],
            "samples": [
                {
                    "id": int(m.entry_id) if m.entry_id else None,
                    "date": m.day.isoformat() if m.day else None,
                    "text": m.text[:200],
                    "metadata": dict(m.metadata_numbers),
                    "tags": list(m.tags),
                }
                for m in matches[:5]
            ],
        }

    def load_entry(self, entry_id: int) -> dict[str, Any]:
        """Load a single entry as Entry objects for CLI rendering."""
        self._ensure_index()
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT source_file FROM entries WHERE id = ?", (entry_id,)
        )
        row = cursor.fetchone()
        if row is None:
            return {
                "success": False,
                "error": f"Entry {entry_id} not found.",
            }
        matches = load_matches(
            [(row[0], entry_id)], self.log_dir, self.config
        )
        if not matches:
            return {
                "success": False,
                "error": f"Entry {entry_id} not found.",
            }
        return {"success": True, "matches": matches}

    def get_entry(self, entry_id: int) -> dict[str, Any]:
        """Return a single entry by its numeric identifier (dict)."""
        result = self.load_entry(entry_id)
        if not result.get("success"):
            return result
        return {"success": True, "entry": result["matches"][0].to_dict()}

    def list_tags(self) -> dict[str, Any]:
        """Tag list for MCP (keys: tag, count)."""
        cursor = self.conn.cursor()
        cursor.execute(
            (
                "SELECT tag_name, COUNT(*) "
                "FROM tags "
                "GROUP BY tag_name "
                "ORDER BY tag_name"
            )
        )
        rows = cursor.fetchall()
        tags = [{"tag": name, "count": count} for name, count in rows]
        return {"success": True, "tags": tags}

    def tags(self) -> dict[str, Any]:
        """Tag list for CLI printers (keys: name, count)."""
        self._ensure_index()
        return tags_command(self.conn)

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
            except OSError as error:  # pragma: no cover
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
        now = datetime.now()
        target_year = year or now.year
        target_month = month or now.month
        counts = collect_month_counts(
            self.log_dir,
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

    def monthly_stats(
        self, now: datetime | None = None
    ) -> dict[str, Any]:
        """Calendar stats for the CLI --stats command."""
        moment = now or datetime.now()
        return stats_command(self.log_dir, self.config, moment)

    def list_recent_entries(self, limit: int = 10) -> dict[str, Any]:
        now = datetime.now()
        self._ensure_index(now)
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT source_file, id FROM entries ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        locations = cursor.fetchall()
        if not locations:
            return {"success": True, "entries": []}
        matches = load_matches(locations, self.log_dir, self.config)
        matches.sort(
            key=lambda entry: int(entry.entry_id or 0),
            reverse=True,
        )
        payload = [match.to_dict() for match in matches]
        return {"success": True, "entries": payload}

    def entries_by_tag(self, tag: str, limit: int = 10) -> dict[str, Any]:
        now = datetime.now()
        self._ensure_index(now)
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT e.source_file, e.id
            FROM entries e
            JOIN tags t ON e.id = t.entry_id
            WHERE t.tag_name = ?
            ORDER BY e.id DESC
            LIMIT ?
            """,
            (tag, limit),
        )
        locations = cursor.fetchall()
        if not locations:
            return {"success": True, "entries": []}
        matches = load_matches(locations, self.log_dir, self.config)
        payload = [match.to_dict() for match in matches]
        return {"success": True, "entries": payload}

    # --- Todos --------------------------------------------------------

    def create_todo(
        self, description: str, metadata: dict[str, str] | None = None
    ) -> dict[str, Any]:
        """Create a new todo entry with status:pending and #todo tag."""
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
                log_dir=self.log_dir,
                now=now,
                conn=self.conn,
            )
        except EmptyEntryError as error:
            return {"success": False, "error": str(error)}
        return {"success": True, **result}

    def create_todo_from_cli(
        self,
        tokens: list[str],
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Create a todo from CLI token list (supports inline metadata)."""
        moment = now or datetime.now()
        args = SimpleNamespace(todo=tokens)
        return todo_command(
            args,
            self.config,
            self.config_dir,
            self.log_dir,
            moment,
            self.conn,
        )

    def mark_todo_done(self, entry_id: int) -> dict[str, Any]:
        """Mark a todo entry as done by updating its status."""
        now = datetime.now()
        try:
            return done_command(
                self.conn,
                self.log_dir,
                self.config,
                entry_id,
                now,
            )
        except Exception as error:
            return {
                "success": False,
                "error": str(error),
                "message": str(error),
            }

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
            # build_search_query returns (source_file, id),
            # direct queries return (id, source_file)
            if filter_query:
                source_file, entry_id = row
            else:
                entry_id, source_file = row
            day_file = self.log_dir / source_file
            if not day_file.exists():
                continue

            day_file_pattern = self.config.get("DAY_FILE_PATTERN", "")
            entry_date = resolve_entry_date(day_file, day_file_pattern)
            entries = parse_day_entries(day_file, entry_date)

            for entry in entries:
                if entry.entry_id == str(entry_id):
                    entry_status = entry.metadata.get("status", "pending")
                    if status and filter_query and entry_status != status:
                        continue
                    completed_at = entry.metadata.get("completed_at", "")
                    description = (
                        entry.lines[0]
                        if entry.lines
                        else "(no description)"
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
