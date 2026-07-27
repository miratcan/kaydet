"Search and tags commands."

import re
import sqlite3
from collections import defaultdict
from configparser import SectionProxy
from datetime import date, datetime
from pathlib import Path
from typing import List, Optional, Tuple

from rich import print
from rich.console import Console

from ..formatters import (
    SearchResult,
    format_search_results,
)
from ..indexing import rebuild_index_if_empty
from ..json_output import print_json_ok
from ..parsers import (
    parse_comparison_expression,
    parse_day_entries,
    parse_range_expression,
    resolve_entry_date,
    tokenize_query,
)

SELECT_MATCHES_TEMPLATE = (
    "SELECT DISTINCT e.source_file, e.id "
    "FROM {from_clause} "
    "WHERE {where_clause} "
    "ORDER BY e.source_file, e.id"
)

SELECT_TAG_COUNTS_SQL = (
    "SELECT tag_name, COUNT(*) FROM tags GROUP BY tag_name ORDER BY tag_name"
)


def build_search_query(
    include_text,
    exclude_text,
    include_meta,
    exclude_meta,
    include_tags,
    exclude_tags,
) -> tuple[str, list]:
    """Compose the SQL query and parameters for a search request."""
    params = []
    from_clauses = ["entries e"]
    where_clauses = []

    # FTS text search (Inclusion and Exclusion combined)
    fts_query_parts = []
    for term in include_text:
        # Simple escaping for FTS: wrap in quotes
        clean_term = term.replace('"', '""')
        fts_query_parts.append(f'"{clean_term}"')
    for term in exclude_text:
        clean_term = term.replace('"', '""')
        fts_query_parts.append(f'NOT "{clean_term}"')

    if fts_query_parts:
        from_clauses.append("JOIN entries_fts fts ON e.id = fts.rowid")
        where_clauses.append("entries_fts MATCH ?")
        params.append(" ".join(fts_query_parts))

    # Tags inclusion
    for i, tag in enumerate(include_tags):
        from_clauses.append(f"JOIN tags t{i} ON e.id = t{i}.entry_id")
        where_clauses.append(f"t{i}.tag_name = ?")
        params.append(tag)

    # Metadata inclusion
    for i, (key, expression) in enumerate(include_meta):
        # Special handling for date filters
        if key in ("since", "until"):
            op = ">=" if key == "since" else "<="
            if expression not in ("0", "all"):
                where_clauses.append(f"e.source_file {op} ?")
                params.append(expression)
            continue

        from_clauses.append(f"JOIN metadata m{i} ON e.id = m{i}.entry_id")
        where_clauses.append(f"m{i}.meta_key = ?")
        params.append(key)
        if comp := parse_comparison_expression(expression):
            op, val = comp
            where_clauses.append(f"m{i}.numeric_value {op} ?")
            params.append(val)
        elif rng := parse_range_expression(expression):
            lower, upper = rng
            if lower is not None:
                where_clauses.append(f"m{i}.numeric_value >= ?")
                params.append(lower)
            if upper is not None:
                where_clauses.append(f"m{i}.numeric_value <= ?")
                params.append(upper)
        elif any(c in expression for c in "*?[]"):
            where_clauses.append(f"m{i}.meta_value GLOB ?")
            params.append(expression)
        else:
            where_clauses.append(f"m{i}.meta_value = ?")
            params.append(expression)

    # Exclusion clauses for tags and metadata (FTS exclusion handled above)
    for i, tag in enumerate(exclude_tags):
        where_clauses.append(
            f"NOT EXISTS (SELECT 1 FROM tags t_ex{i} "
            f"WHERE t_ex{i}.entry_id = e.id "
            f"AND t_ex{i}.tag_name = ?)"
        )
        params.append(tag)
    for i, (key, value) in enumerate(exclude_meta):
        where_clauses.append(
            f"NOT EXISTS (SELECT 1 FROM metadata m_ex{i} "
            f"WHERE m_ex{i}.entry_id = e.id "
            f"AND m_ex{i}.meta_key = ? "
            f"AND m_ex{i}.meta_value = ?)"
        )
        params.extend([key, value])

    from_clause = " ".join(
        list(dict.fromkeys(from_clauses))
    )  # Remove duplicate JOINs
    where_clause = " AND ".join(where_clauses) if where_clauses else "1=1"
    sql_query = SELECT_MATCHES_TEMPLATE.format(
        from_clause=from_clause,
        where_clause=where_clause,
    )
    return sql_query, params


def fetch_entry_locations(
    conn: sqlite3.Connection, sql_query: str, params: list
):
    cursor = conn.cursor()
    cursor.execute(sql_query, params)
    return cursor.fetchall()


def load_matches(
    locations,
    log_dir: Path,
    config: SectionProxy,
):
    """Resolve stored entry identifiers into diary entries."""
    file_map = defaultdict(list)
    for source_file, entry_id in locations:
        file_map[source_file].append(str(entry_id))

    matches = []
    day_file_pattern = config.get("DAY_FILE_PATTERN", "")
    for source_file, entry_ids in file_map.items():
        full_path = log_dir / source_file
        if not full_path.exists():
            continue
        entry_date = resolve_entry_date(full_path, day_file_pattern)
        entries_in_file = parse_day_entries(full_path, entry_date)
        entry_map = {
            entry.entry_id: entry
            for entry in entries_in_file
            if entry.entry_id and entry.entry_id.isdigit()
        }
        for entry_id in entry_ids:
            if entry_id in entry_map:
                matches.append(entry_map[entry_id])

    matches.sort(key=lambda entry: (entry.day or date.min, entry.timestamp))
    return matches


def _date_window_from_filters(
    metadata_filters: Optional[List[Tuple[str, str]]],
    default_since_hint: Optional[str] = None,
) -> tuple[Optional[str], Optional[str], bool]:
    """Return (since, until, is_default_month_window)."""
    since_value = None
    until_value = None
    if metadata_filters:
        for key, value in metadata_filters:
            if key == "since":
                since_value = value
            elif key == "until":
                until_value = value
    is_default = bool(default_since_hint) and (
        since_value is None or since_value == default_since_hint
    )
    if is_default and since_value is None:
        since_value = default_since_hint
    return since_value, until_value, is_default


def _display_query(query: str) -> str:
    """Strip since:/until: tokens for human-facing query display."""
    display = re.sub(r"\bsince:\S+\s*", "", query).strip()
    display = re.sub(r"\buntil:\S+\s*", "", display).strip()
    return display


def _date_window_phrase(
    since_value: Optional[str],
    until_value: Optional[str],
    is_default: bool,
) -> Optional[str]:
    """Human-readable date window fragment, or None if unrestricted."""
    has_since = since_value and since_value not in ("0", "all")
    has_until = until_value and until_value not in ("0", "all")
    if has_since and has_until:
        return f"{since_value} to {until_value}"
    if has_since:
        if is_default:
            return f"since {since_value} · this month by default"
        return f"since {since_value}"
    if has_until:
        return f"until {until_value}"
    return None


def print_no_matches(
    query: str,
    metadata_filters: Optional[List[Tuple[str, str]]] = None,
    default_since_hint: Optional[str] = None,
) -> None:
    """Print empty search result with date-window context when relevant."""
    display_query = _display_query(query)
    since_value, until_value, is_default = _date_window_from_filters(
        metadata_filters, default_since_hint
    )
    window = _date_window_phrase(since_value, until_value, is_default)

    if display_query:
        msg = f"\U0001f50d No entries matched '{display_query}'"
    else:
        msg = "\U0001f50d No entries found"

    if window:
        msg += f" ({window})"
    print(msg)

    restricted = bool(window)
    if restricted:
        print(
            "\U0001f4a1 Showing a date window — use since:0 for all history."
        )
    else:
        print(
            "\U0001f4a1 Tip: add since:YYYY-MM-DD or since:0 to widen search."
        )


def print_matches(
    matches,
    query: str,
    output_format: str,
    config: SectionProxy,
    console: Optional[Console] = None,
    metadata_filters: Optional[List[Tuple[str, str]]] = None,
    default_since_hint: Optional[str] = None,
    total: Optional[int] = None,
    limit: Optional[int] = None,
) -> None:
    """Render matches either as JSON or a terminal-friendly listing."""
    result_total = total if total is not None else len(matches)
    truncated = result_total > len(matches)
    if output_format == "json":
        print_json_ok(
            {
                "query": query,
                "matches": [match.to_dict() for match in matches],
                "total": result_total,
                "shown": len(matches),
                "limit": limit,
                "truncated": truncated,
            }
        )
        return

    if not matches:
        print_no_matches(query, metadata_filters, default_since_hint)
        return

    # Single width authority: Rich console (avoids double-wrap vs shutil)
    if console is None:
        console = Console()
    terminal_width = console.width or 80

    # Convert matches to SearchResult objects for formatting
    search_results = [
        SearchResult(
            entry_id=match.entry_id,
            day=match.day,
            timestamp=match.timestamp,
            lines=match.lines,
            metadata=match.metadata,
            tags=match.tags,
            attachments=list(match.attachments),
        )
        for match in matches
    ]

    # Use the formatter to display results
    format_search_results(search_results, terminal_width, config, console)

    since_value, until_value, is_default = _date_window_from_filters(
        metadata_filters, default_since_hint
    )
    display_query = _display_query(query)
    window = _date_window_phrase(since_value, until_value, is_default)

    entry_label = "entry" if len(matches) == 1 else "entries"
    if display_query:
        status_msg = (
            f"\n\U0001f50d {len(matches)} {entry_label}"
            f" containing {display_query}"
        )
    else:
        status_msg = f"\n\U0001f50d {len(matches)} {entry_label}"

    if truncated:
        status_msg += f" (showing latest {len(matches)} of {result_total})"
    if window:
        status_msg += f" ({window})"

    print(status_msg)

    if truncated:
        print(
            "\U0001f4a1 Results truncated — raise --limit or use --limit 0 "
            "for all."
        )
    if window:
        print(
            "\U0001f4a1 Showing a date window — use since:0 for all history."
        )


def apply_match_limit(matches: list, limit: Optional[int]) -> tuple[list, int]:
    """Keep the most recent ``limit`` matches (chronological order preserved).

    Returns ``(sliced_matches, total_before_limit)``.
    ``limit`` of None or <= 0 means no limit.
    """
    total = len(matches)
    if limit is None or limit <= 0 or total <= limit:
        return matches, total
    # matches are sorted oldest→newest; keep the tail (most recent)
    return matches[-limit:], total


def search_command(
    conn: sqlite3.Connection,
    log_dir: Path,
    config: SectionProxy,
    query: str,
    allow_empty: bool = False,
    limit: Optional[int] = None,
) -> dict:
    """Search diary entries using the SQLite index and return matches."""
    rebuild_index_if_empty(conn, log_dir, config)

    # Tokenize the query into inclusion and exclusion lists
    (
        include_text,
        exclude_text,
        include_meta,
        exclude_meta,
        include_tags,
        exclude_tags,
    ) = tokenize_query(query)

    # Keep original metadata for display purposes
    original_metadata_filters = list(include_meta)

    # Normalize date-based filenames for since/until filters
    day_file_pattern = config.get("DAY_FILE_PATTERN", "%Y-%m-%d.txt")
    normalized_meta_filters = []
    for key, value in include_meta:
        if key in ("since", "until") and value not in ("0", "all"):
            try:
                date_obj = datetime.strptime(value, "%Y-%m-%d")
                filename = date_obj.strftime(day_file_pattern)
                normalized_meta_filters.append((key, filename))
            except ValueError:
                normalized_meta_filters.append((key, value))
        else:
            normalized_meta_filters.append((key, value))
    include_meta = normalized_meta_filters

    if (
        not any(
            [
                include_text,
                exclude_text,
                include_meta,
                exclude_meta,
                include_tags,
                exclude_tags,
            ]
        )
        and not allow_empty
    ):
        return {"success": False, "error": "\U0001f50d Search query is empty"}

    sql_query, params = build_search_query(
        include_text,
        exclude_text,
        include_meta,
        exclude_meta,
        include_tags,
        exclude_tags,
    )

    locations = fetch_entry_locations(conn, sql_query, params)
    matches = load_matches(locations, log_dir, config)
    matches, total = apply_match_limit(matches, limit)

    return {
        "success": True,
        "query": query,
        "matches": matches,
        "total": total,
        "limit": limit,
        "truncated": total > len(matches),
        "metadata_filters": original_metadata_filters,
    }


def tags_command(conn: sqlite3.Connection) -> dict:
    """Return the unique set of tags recorded in the database."""
    cursor = conn.cursor()
    cursor.execute(SELECT_TAG_COUNTS_SQL)
    rows = cursor.fetchall()
    tags = [{"name": name, "count": count} for name, count in rows]
    return {"success": True, "tags": tags}
