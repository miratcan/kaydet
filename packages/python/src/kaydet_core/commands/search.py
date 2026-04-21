"Search and tags commands."

import sqlite3
from collections import defaultdict
from configparser import SectionProxy
from datetime import date, datetime
from pathlib import Path

from ..indexing import rebuild_index_if_empty
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
        # Wrap in double-quotes so FTS5 treats the term as a literal phrase.
        # Internal double-quotes are escaped by doubling them.
        clean_term = term.replace('"', '""')
        fts_query_parts.append(f'"{clean_term}"')
    for term in exclude_text:
        clean_term = term.replace('"', '""')
        fts_query_parts.append(f'NOT "{clean_term}"')
    # Note: wrapping every term in double-quotes neutralises all FTS5
    # special operators (AND, OR, NOT, *, ?, NEAR, etc.) inside terms,
    # which is the desired behaviour for user-supplied text tokens.

    if fts_query_parts:
        from_clauses.append("JOIN entries_fts fts ON e.id = fts.entry_id")
        where_clauses.append("fts.body MATCH ?")
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
    storage_dir: Path,
    config: SectionProxy,
):
    """Resolve stored entry identifiers into entries."""
    file_map = defaultdict(list)
    for source_file, entry_id in locations:
        file_map[source_file].append(str(entry_id))

    matches = []
    day_file_pattern = config.get("DAY_FILE_PATTERN", "")
    for source_file, entry_ids in file_map.items():
        full_path = storage_dir / source_file
        if not full_path.exists():
            continue
        entry_date = resolve_entry_date(full_path, day_file_pattern)
        entries_in_file = parse_day_entries(full_path, entry_date)
        entry_map = {
            entry.entry_id: entry
            for entry in entries_in_file
            if entry.entry_id
        }
        for entry_id in entry_ids:
            if entry_id in entry_map:
                matches.append(entry_map[entry_id])

    matches.sort(key=lambda entry: (entry.day or date.min, entry.timestamp))
    return matches


def search_command(
    conn: sqlite3.Connection,
    storage_dir: Path,
    config: SectionProxy,
    query: str,
    allow_empty: bool = False,
) -> dict:
    """Search entries using the SQLite index and return matches."""
    rebuild_index_if_empty(conn, storage_dir, config)

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
        return {"success": False, "error": "Search query is empty."}

    sql_query, params = build_search_query(
        include_text,
        exclude_text,
        include_meta,
        exclude_meta,
        include_tags,
        exclude_tags,
    )

    locations = fetch_entry_locations(conn, sql_query, params)
    matches = load_matches(locations, storage_dir, config)

    return {
        "success": True,
        "query": query,
        "matches": matches,
        "metadata_filters": original_metadata_filters,
    }


def tags_command(conn: sqlite3.Connection) -> dict:
    """Return the unique set of tags recorded in the database."""
    cursor = conn.cursor()
    cursor.execute(SELECT_TAG_COUNTS_SQL)
    rows = cursor.fetchall()
    tags = [{"name": name, "count": count} for name, count in rows]
    return {"success": True, "tags": tags}
