"Search and tags commands."

import json
import re
import shutil
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
    "SELECT tag_name, COUNT(*) FROM tags "
    "GROUP BY tag_name ORDER BY tag_name"
)


def build_search_query(
    text_terms, metadata_filters, tag_filters
) -> tuple[str, list]:
    """Compose the SQL query and parameters for a search request.

    TODO: Consider replacing this manual string builder with a small
    query DSL or ORM abstraction once the schema stabilizes further.

    Example:
        >>> sql, params = build_search_query(["focus"], [], [])
        >>> sql.startswith("SELECT DISTINCT")
        True
        >>> params
        ['%focus%']
    """
    params = []
    from_clauses = ["entries e"]
    where_clauses = []

    for i, term in enumerate(text_terms):
        from_clauses.append(f"JOIN words w{i} ON e.id = w{i}.entry_id")
        where_clauses.append(f"w{i}.word LIKE ?")
        params.append(f"%{term}%")
    for i, tag in enumerate(tag_filters):
        from_clauses.append(f"JOIN tags t{i} ON e.id = t{i}.entry_id")
        where_clauses.append(f"t{i}.tag_name = ?")
        params.append(tag)
    for i, (key, expression) in enumerate(metadata_filters):
        # Special handling for 'since:' filter - filter by source_file (date-based filename)
        if key == "since":
            # since:0 or since:all means no date filter
            if expression in ("0", "all"):
                continue
            # Expression is now a pre-formatted filename (handled in search_command)
            where_clauses.append(f"e.source_file >= ?")
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

    from_clause = " ".join(from_clauses)
    where_clause = " AND ".join(where_clauses) if where_clauses else "1=1"
    sql_query = SELECT_MATCHES_TEMPLATE.format(
        from_clause=from_clause,
        where_clause=where_clause,
    )
    return sql_query, params


def fetch_entry_locations(
    db: sqlite3.Connection, sql_query: str, params: list
):
    """Execute the search query and return matching entry identifiers."""
    cursor = db.cursor()
    try:
        cursor.execute(sql_query, params)
    except sqlite3.OperationalError as error:
        print(f"Database query failed: {error}")
        return None
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


def print_matches(matches, query: str, output_format: str, config: SectionProxy, console: Optional[Console] = None, metadata_filters: Optional[List[Tuple[str, str]]] = None) -> None:
    """Render matches either as JSON or a terminal-friendly listing."""
    if output_format == "json":
        print(
            json.dumps(
                {
                    "query": query,
                    "matches": [match.to_dict() for match in matches],
                    "total": len(matches),
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return

    if not matches:
        return

    try:
        terminal_width = shutil.get_terminal_size().columns
    except OSError:
        terminal_width = 80

    # Convert matches to SearchResult objects for formatting
    search_results = [
        SearchResult(
            entry_id=match.entry_id,
            day=match.day,
            timestamp=match.timestamp,
            lines=match.lines,
            metadata=match.metadata,
            tags=match.tags,
        )
        for match in matches
    ]

    # Use the formatter to display results
    format_search_results(search_results, terminal_width, config, console)

    # Extract since filter info if present
    since_value = None
    if metadata_filters:
        for key, value in metadata_filters:
            if key == "since":
                since_value = value
                break

    # Build status message at the bottom (terminal scrolls up)
    entry_label = "entry" if len(matches) == 1 else "entries"

    # Clean query: remove since: filter from display (it's shown separately)
    display_query = query
    if "since:" in query:
        # Remove since:VALUE from query string for cleaner display
        display_query = re.sub(r'\bsince:\S+\s*', '', query).strip()

    if display_query:
        status_msg = f"\nListed {len(matches)} {entry_label} containing '{display_query}'"
    else:
        status_msg = f"\nListed {len(matches)} {entry_label}"

    # Add since filter info if applied and not since:0
    if since_value and since_value not in ("0", "all"):
        current_month_start = date.today().replace(day=1).isoformat()
        if since_value == current_month_start:
            status_msg += f" (since {since_value}, current month)"
        else:
            status_msg += f" (since {since_value})"

    print(status_msg + ".")

    # Show hint for seeing all entries if filter is applied
    if since_value and since_value not in ("0", "all"):
        if display_query:
            print(f"Use '{display_query} since:0' to see all entries.")
        else:
            print("Use 'since:0' to see all entries.")


def search_command(
    db: sqlite3.Connection,
    log_dir: Path,
    config: SectionProxy,
    query: str,
    output_format: str = "text",
    console: Optional[Console] = None,
    allow_empty: bool = False,
):
    """Search diary entries using the SQLite index and print any matches."""
    rebuild_index_if_empty(db, log_dir, config)

    # Add default since: filter for current month if not specified
    text_terms, metadata_filters, tag_filters = tokenize_query(query)

    # Check if since: filter is already present
    has_since_filter = any(key == "since" for key, _ in metadata_filters)

    # Add default since: for current month if not specified
    if not has_since_filter:
        current_month_start = date.today().replace(day=1).isoformat()
        metadata_filters.append(("since", current_month_start))

    # Convert since: date expressions to actual filenames using DAY_FILE_PATTERN
    # This ensures the filter works regardless of user's file extension (.txt, .md, etc.)
    # Keep original dates for display purposes
    day_file_pattern = config.get("DAY_FILE_PATTERN", "%Y-%m-%d.txt")
    original_metadata_filters = list(metadata_filters)  # Keep for display

    normalized_filters = []
    for key, value in metadata_filters:
        if key == "since" and value not in ("0", "all"):
            # Parse date and format according to DAY_FILE_PATTERN
            try:
                # Handle both YYYY-MM-DD and YYYY-MM formats
                if len(value) == 7:  # YYYY-MM format
                    date_obj = datetime.strptime(f"{value}-01", "%Y-%m-%d")
                else:  # YYYY-MM-DD format
                    date_obj = datetime.strptime(value, "%Y-%m-%d")
                # Format using configured pattern
                filename = date_obj.strftime(day_file_pattern)
                normalized_filters.append((key, filename))
            except ValueError:
                # Invalid date format, keep original (will likely fail gracefully)
                normalized_filters.append((key, value))
        else:
            normalized_filters.append((key, value))

    metadata_filters = normalized_filters

    if not any([text_terms, metadata_filters, tag_filters]) and not allow_empty:
        print("Search query is empty.")
        return
    sql_query, params = build_search_query(
        text_terms, metadata_filters, tag_filters
    )
    locations = fetch_entry_locations(db, sql_query, params)
    if locations is None:
        return
    if not locations:
        print(f"No entries matched '{query}'.")
        return
    matches = load_matches(locations, log_dir, config)
    print_matches(matches, query, output_format, config, console, original_metadata_filters)


def tags_command(db: sqlite3.Connection, output_format: str = "text"):
    """Print the unique set of tags recorded in the database."""
    cursor = db.cursor()
    cursor.execute(SELECT_TAG_COUNTS_SQL)
    rows = cursor.fetchall()
    if not rows:
        if output_format == "json":
            print(json.dumps({"tags": []}))
        else:
            print("No tags have been recorded yet.")
        return
    if output_format == "json":
        tags = [{"name": name, "count": count} for name, count in rows]
        print(json.dumps({"tags": tags}, indent=2))
    else:
        for name, count in rows:
            label = f"#{name}"
            suffix = "entry" if count == 1 else "entries"
            print(f"{label:<20} {count} {suffix}")
