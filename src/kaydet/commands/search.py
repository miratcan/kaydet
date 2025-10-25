"""Search and tags commands."""

import json
import sqlite3
from collections import defaultdict
from configparser import SectionProxy
from datetime import date
from pathlib import Path

from ..parsers import (
    parse_comparison_expression,
    parse_day_entries,
    parse_range_expression,
    resolve_entry_date,
    tokenize_query,
)
from .doctor import doctor_command


def search_command(
    db: sqlite3.Connection,
    log_dir: Path,
    config: SectionProxy,
    query: str,
    output_format: str = "text",
):
    """Search diary entries using the SQLite index and print any matches."""
    # Check if database is empty and auto-rebuild if needed
    cursor = db.cursor()
    cursor.execute("SELECT COUNT(*) FROM entries")
    entry_count = cursor.fetchone()[0]

    if entry_count == 0 and log_dir.exists():
        # Check if there are any .txt files to index
        txt_files = list(log_dir.glob("*.txt"))
        if txt_files:
            print("Search index is empty. Rebuilding from existing files...")
            doctor_command(db, log_dir, config)
            print()  # Add spacing after doctor output

    text_terms, metadata_filters, tag_filters = tokenize_query(query)
    if not any([text_terms, metadata_filters, tag_filters]):
        print("Search query is empty.")
        return

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
        elif any(c in expression for c in "*?["):
            where_clauses.append(f"m{i}.meta_value GLOB ?")
            params.append(expression)
        else:
            where_clauses.append(f"m{i}.meta_value = ?")
            params.append(expression)

    sql_query = f'SELECT DISTINCT e.source_file, e.entry_uuid FROM {" ".join(from_clauses)} WHERE {" AND ".join(where_clauses)} ORDER BY e.source_file, e.id'

    cursor = db.cursor()
    try:
        cursor.execute(sql_query, params)
        locations = cursor.fetchall()
    except sqlite3.OperationalError as e:
        print(f"Database query failed: {e}")
        return

    if not locations:
        print(f"No entries matched '{query}'.")
        return

    file_map = defaultdict(list)
    for source_file, uuid in locations:
        file_map[source_file].append(uuid)

    matches = []
    day_file_pattern = config.get("DAY_FILE_PATTERN", "")
    for source_file, uuids in file_map.items():
        full_path = log_dir / source_file
        if not full_path.exists():
            continue
        entry_date = resolve_entry_date(full_path, day_file_pattern)
        entries_in_file = parse_day_entries(full_path, entry_date)
        entry_map = {entry.uuid: entry for entry in entries_in_file}
        for uuid in uuids:
            if uuid in entry_map:
                matches.append(entry_map[uuid])

    matches.sort(key=lambda e: (e.day or date.min, e.timestamp))

    if output_format == "json":
        print(json.dumps({"query": query, "matches": [m.to_dict() for m in matches], "total": len(matches)}, indent=2, ensure_ascii=False))
    else:
        for match in matches:
            day_label = match.day.isoformat() if match.day else match.source.name
            first_line, *rest = list(match.lines) or [""]

            # Build header with metadata and tags
            parts = [f"{day_label} {match.timestamp} {first_line}".rstrip()]
            if match.metadata:
                metadata_str = " ".join(f"{k}:{v}" for k, v in match.metadata.items())
                parts.append(metadata_str)
            if match.tags:
                tags_str = " ".join(f"#{tag}" for tag in match.tags)
                parts.append(tags_str)

            header = " | ".join(parts) if len(parts) > 1 else parts[0]
            print(header)
            for extra in rest:
                print(f"    {extra}")
            print()
        print(f"\nFound {len(matches)} {'entry' if len(matches) == 1 else 'entries'} containing '{query}'.")


def tags_command(db: sqlite3.Connection, output_format: str = "text"):
    """Print the unique set of tags recorded in the database."""
    cursor = db.cursor()
    cursor.execute("SELECT DISTINCT tag_name FROM tags ORDER BY tag_name")
    tags = [row[0] for row in cursor.fetchall()]
    if not tags:
        if output_format == "json":
            print(json.dumps({"tags": []}))
        else:
            print("No tags have been recorded yet.")
        return
    if output_format == "json":
        print(json.dumps({"tags": tags}, indent=2))
    else:
        print("\n".join(tags))
