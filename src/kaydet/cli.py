"Command-line interface for the kaydet diary application."

from __future__ import annotations

import argparse
import calendar
import json
import re
import shutil
import sqlite3
import subprocess
from collections import defaultdict
from configparser import ConfigParser, SectionProxy
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from os import environ as env
from os import fdopen, remove
from pathlib import Path
from tempfile import mkstemp
from textwrap import dedent
from typing import Dict, Iterable, List, Optional, Tuple
import fnmatch
import math
import shlex

import hashlib
import shortuuid
from startfile import startfile

from . import __description__, __version__
from . import database

CONFIG_SECTION = "SETTINGS"
DEFAULT_SETTINGS = {
    "DAY_FILE_PATTERN": "%Y-%m-%d.txt",
    "DAY_TITLE_PATTERN": "%Y/%m/%d/ - %A",
    "LOG_DIR": str(
        Path(env.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "kaydet"
    ),
    "EDITOR": env.get("EDITOR", "vim"),
}
LAST_ENTRY_FILENAME = "last_entry_timestamp"
REMINDER_THRESHOLD = timedelta(hours=2)
ENTRY_LINE_PATTERN = re.compile(r"^(?:([a-zA-Z0-9_-]{22}):)?(\d{2}:\d{2}): (.*)")
LEGACY_TAG_PATTERN = re.compile(r"^[\[(](?P<tags>[a-z-]+(?:,[a-z-]+)*)[\])]\s*")
HASHTAG_PATTERN = re.compile(r"#([a-z-]+)")
TAG_PATTERN = re.compile(r"^[a-z-]+$")
KEY_VALUE_PATTERN = re.compile(r"^(?P<key>[a-z][a-z0-9_-]*):(?P<value>.+)")
NUMERIC_PATTERN = re.compile(r"^[-+]?\d+(?:\.\d+)?$")
INDEX_FILENAME = "index.db"


def normalize_tag(tag: str) -> Optional[str]:
    """Normalize a tag token by stripping markers and lowercasing."""
    cleaned = tag.strip().lstrip("#").lower()
    return cleaned if cleaned else None


def parse_metadata_token(token: str) -> Optional[Tuple[str, str]]:
    """Return a (key, value) pair if the token is a metadata declaration."""
    match = KEY_VALUE_PATTERN.match(token)
    if not match:
        return None
    key = match.group("key").lower()
    value = match.group("value").strip()
    if not value or value.startswith("//"):
        return None
    return key, value


def parse_numeric_value(raw_value: str) -> Optional[float]:
    """Convert a metadata value to a numeric representation when possible."""
    value = raw_value.strip().lower()
    if value.endswith("h") and NUMERIC_PATTERN.match(value[:-1]):
        return float(value[:-1])
    if value.endswith("m") and NUMERIC_PATTERN.match(value[:-1]):
        return float(value[:-1]) / 60.0
    if NUMERIC_PATTERN.match(value):
        return float(value)
    return None


def build_numeric_metadata(metadata: Dict[str, str]) -> Dict[str, float]:
    """Return numeric representations for metadata values when available."""
    numeric: Dict[str, float] = {}
    for key, value in metadata.items():
        converted = parse_numeric_value(value)
        if converted is not None:
            numeric[key] = converted
    return numeric


def partition_entry_tokens(
    tokens: Iterable[str],
) -> Tuple[List[str], Dict[str, str], List[str]]:
    """Split CLI tokens into message text, metadata, and explicit tags."""
    message_tokens: List[str] = []
    metadata: Dict[str, str] = {}
    explicit_tags: List[str] = []
    for token in tokens:
        if token.startswith("#"):
            if tag := normalize_tag(token):
                explicit_tags.append(tag)
        elif parsed := parse_metadata_token(token):
            key, value = parsed
            metadata[key] = value
        else:
            message_tokens.append(token)
    return message_tokens, metadata, explicit_tags


def format_entry_header(
    timestamp: str,
    message: str,
    metadata: Dict[str, str],
    extra_tag_markers: Iterable[str],
) -> str:
    """Format the first line of a diary entry for storage."""
    base = f"{timestamp}: {message}" if message else f"{timestamp}:"
    segments = [base.rstrip()]
    if metadata:
        segments.append(" ".join(f"{k}:{v}" for k, v in metadata.items()))
    if extra_tag_markers:
        segments.append(" ".join(f"#{t}" for t in extra_tag_markers if t))
    return " | ".join(segments)


def parse_stored_entry_remainder(
    remainder: str,
) -> Tuple[str, Dict[str, str], List[str]]:
    """Parse the message, metadata, and explicit tags from a stored line."""
    metadata: Dict[str, str] = {}
    explicit_tags: List[str] = []
    if "|" not in remainder:
        return remainder.rstrip(), metadata, explicit_tags
    parts = [part.strip() for part in remainder.split("|")]
    message = parts[0] if parts else remainder.rstrip()
    for segment in parts[1:]:
        for token in segment.split():
            if token.startswith("#"):
                if tag := normalize_tag(token):
                    explicit_tags.append(tag)
            elif parsed := parse_metadata_token(token):
                key, value = parsed
                metadata[key] = value
            else:
                message = f"{message} {token}".strip()
    return message, metadata, explicit_tags


def tokenize_query(
    query: str,
) -> Tuple[List[str], List[Tuple[str, str]], List[str]]:
    """Split a search query into text terms, metadata filters, and tag filters."""
    try:
        tokens = shlex.split(query)
    except ValueError:
        tokens = query.split()
    text_terms: List[str] = []
    metadata_filters: List[Tuple[str, str]] = []
    tag_filters: List[str] = []
    for token in tokens:
        if not token:
            continue
        if token.startswith("#"):
            if tag := normalize_tag(token):
                tag_filters.append(tag)
        elif parsed := parse_metadata_token(token):
            metadata_filters.append(parsed)
        else:
            text_terms.append(token.lower())
    return text_terms, metadata_filters, tag_filters


def parse_range_expression(expression: str) -> Optional[Tuple[Optional[float], Optional[float]]]:
    """Parse a range expression like ``1..3`` into numeric bounds."""
    if ".." not in expression:
        return None
    lower_raw, upper_raw = expression.split("..", 1)
    lower = parse_numeric_value(lower_raw) if lower_raw.strip() else None
    upper = parse_numeric_value(upper_raw) if upper_raw.strip() else None
    if (lower_raw.strip() and lower is None) or (upper_raw.strip() and upper is None):
        return None
    return lower, upper


def parse_comparison_expression(expression: str) -> Optional[Tuple[str, float]]:
    """Parse comparison expressions like ``>=2`` or ``<5``."""
    for operator in (">=", "<=", ">", "<"):
        if expression.startswith(operator):
            remainder = expression[len(operator) :].strip()
            if (numeric := parse_numeric_value(remainder)) is not None:
                return operator, numeric
    return None


@dataclass(frozen=True)
class DiaryEntry:
    """Structured view of a diary entry loaded from disk."""
    uuid: str
    day: Optional[date]
    timestamp: str
    lines: Tuple[str, ...]
    tags: Tuple[str, ...]
    metadata: Dict[str, str]
    metadata_numbers: Dict[str, float]
    source: Path

    @property
    def text(self) -> str:
        return "\n".join(self.lines)

    def to_dict(self) -> dict:
        """Convert entry to dictionary for JSON serialization."""
        return {
            "uuid": self.uuid,
            "date": self.day.isoformat() if self.day else None,
            "timestamp": self.timestamp,
            "text": self.text,
            "tags": list(self.tags),
            "metadata": self.metadata,
            "source": str(self.source),
        }


def read_diary_lines(path: Path) -> List[str]:
    """Return diary file lines, tolerating non-UTF8 bytes by replacing them."""
    try:
        return path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace").splitlines()


def count_entries(day_file: Path) -> int:
    """Count timestamped diary entries inside a daily file."""
    lines = read_diary_lines(day_file)
    return sum(1 for line in lines if ENTRY_LINE_PATTERN.match(line))


def parse_day_entries(day_file: Path, day: Optional[date]) -> List[DiaryEntry]:
    """Parse structured entries from a diary file, supporting both UUID and legacy formats."""
    lines = read_diary_lines(day_file)
    entries: List[DiaryEntry] = []
    current_uuid: Optional[str] = None
    current_time: Optional[str] = None
    current_lines: List[str] = []
    current_legacy_tags: List[str] = []
    current_metadata: Dict[str, str] = {}
    current_explicit_tags: List[str] = []

    def finalize_entry():
        if current_time is None:
            return
        # Generate deterministic UUID for legacy entries
        if current_uuid:
            entry_uuid = current_uuid
        else:
            # Create deterministic UUID from file path, timestamp, and first line
            first_line = current_lines[0] if current_lines else ""
            seed = f"{day_file.name}:{current_time}:{first_line}"
            hash_digest = hashlib.sha256(seed.encode()).hexdigest()
            # Use first 22 chars of hash as deterministic UUID
            entry_uuid = hash_digest[:22]
        combined_tags = current_legacy_tags + current_explicit_tags
        tags = deduplicate_tags(combined_tags, current_lines)
        entries.append(
            DiaryEntry(
                uuid=entry_uuid,
                day=day,
                timestamp=current_time,
                lines=tuple(current_lines),
                tags=tags,
                metadata=dict(current_metadata),
                metadata_numbers=build_numeric_metadata(current_metadata),
                source=day_file,
            )
        )

    for line in lines:
        match = ENTRY_LINE_PATTERN.match(line)
        if match:
            finalize_entry()
            uuid_part, time_part, remainder = match.groups()
            current_uuid = uuid_part
            current_time = time_part.strip(":")
            
            legacy_match = LEGACY_TAG_PATTERN.match(remainder)
            if legacy_match:
                current_legacy_tags = legacy_match.group("tags").split(",")
                remainder = remainder[legacy_match.end() :]
            else:
                current_legacy_tags = []

            remainder = remainder.lstrip()
            message_line, parsed_metadata, explicit_tags = parse_stored_entry_remainder(remainder)
            current_lines = [message_line]
            current_metadata = parsed_metadata
            current_explicit_tags = explicit_tags
        elif current_time is not None:
            current_lines.append(line)
    finalize_entry()
    return entries


def deduplicate_tags(
    initial_tags: Iterable[str],
    lines: Iterable[str],
) -> Tuple[str, ...]:
    """Return unique lowercase tags."""
    seen: List[str] = []
    def register(tag: str):
        if (tag_lower := tag.lower()) and tag_lower not in seen:
            seen.append(tag_lower)
    for tag in initial_tags:
        register(tag)
    for line in lines:
        for tag in HASHTAG_PATTERN.findall(line):
            register(tag)
    return tuple(seen)


def extract_tags_from_text(entry_text: str) -> Tuple[str, ...]:
    """Return all unique hashtags present in the entry text."""
    if not entry_text:
        return ()
    return deduplicate_tags([], entry_text.splitlines() or [entry_text])


def iter_diary_entries(log_dir: Path, config: SectionProxy) -> Iterable[DiaryEntry]:
    """Yield entries from every diary file sorted by filename."""
    if not log_dir.exists():
        return
    day_file_pattern = config.get("DAY_FILE_PATTERN", DEFAULT_SETTINGS["DAY_FILE_PATTERN"])
    for candidate in sorted(log_dir.glob("*.txt")):
        if not candidate.is_file():
            continue
        entry_date = resolve_entry_date(candidate, day_file_pattern)
        yield from parse_day_entries(candidate, entry_date)


def resolve_entry_date(day_file: Path, pattern: str) -> Optional[date]:
    """Infer the date represented by a diary file using the configured pattern."""
    try:
        return datetime.strptime(day_file.name, pattern).date()
    except ValueError:
        return None


def get_config() -> Tuple[SectionProxy, Path, Path]:
    """Load configuration and ensure defaults exist."""
    config_root = Path(env.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    config_dir = config_root / "kaydet"
    config_dir.mkdir(parents=True, exist_ok=True)
    parser = ConfigParser(interpolation=None)
    config_path = config_dir / "config.ini"
    if config_path.exists():
        parser.read(config_path, encoding="utf-8")
    if CONFIG_SECTION not in parser:
        parser[CONFIG_SECTION] = {}
    section = parser[CONFIG_SECTION]
    updated = False
    for key, value in DEFAULT_SETTINGS.items():
        if not section.get(key):
            section[key] = value
            updated = True
    if updated:
        with config_path.open("w", encoding="utf-8") as config_file:
            parser.write(config_file)
    return section, config_path, config_dir


def get_entry(
    args: argparse.Namespace,
    config: SectionProxy,
) -> Tuple[str, Dict[str, str], Tuple[str, ...]]:
    """Resolve entry content, metadata, and tags from CLI arguments or an editor."""
    tokens = list(args.entry or [])
    message_tokens, metadata, explicit_tags = partition_entry_tokens(tokens)
    message_text = " ".join(message_tokens)
    if args.use_editor or not (message_text or metadata or explicit_tags):
        editor_text = open_editor(message_text, config["EDITOR"])
        # Editor text is returned as-is; metadata and tags can be embedded with # and key:value
        return editor_text, {}, ()
    return message_text, metadata, tuple(explicit_tags)


def open_editor(initial_text: str, editor_command: str) -> str:
    """Open a temporary file with the configured editor and return its contents."""
    fd, tmp_path = mkstemp()
    try:
        with fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(initial_text)
        subprocess.call(shlex.split(editor_command) + [str(tmp_path)])
        return Path(tmp_path).read_text(encoding="utf-8")
    finally:
        try:
            remove(tmp_path)
        except OSError:
            pass


def save_last_entry_timestamp(config_dir: Path, moment: datetime) -> None:
    """Persist the provided timestamp for subsequent reminder checks."""
    (config_dir / LAST_ENTRY_FILENAME).write_text(moment.isoformat(), encoding="utf-8")


def load_last_entry_timestamp(
    config_dir: Path, log_dir: Path
) -> Optional[datetime]:
    """Return the timestamp of the most recent saved entry, if any."""
    record_path = config_dir / LAST_ENTRY_FILENAME
    try:
        raw_value = record_path.read_text(encoding="utf-8").strip()
        if raw_value:
            return datetime.fromisoformat(raw_value)
    except (FileNotFoundError, ValueError):
        pass

    latest_mtime: Optional[float] = None
    if log_dir.exists():
        for candidate in log_dir.iterdir():
            if candidate.is_file() and candidate.suffix == ".txt":
                mtime = candidate.stat().st_mtime
                if latest_mtime is None or mtime > latest_mtime:
                    latest_mtime = mtime
    if latest_mtime is None:
        return None
    return datetime.fromtimestamp(latest_mtime)


def maybe_show_reminder(
    config_dir: Path, log_dir: Path, now: datetime
) -> None:
    """Emit a reminder if no entry has been written recently."""
    last_entry = load_last_entry_timestamp(config_dir, log_dir)
    if last_entry is None:
        print(
            "You haven't written any Kaydet entries yet. "
            "Capture your first note with `kaydet --editor`."
        )
        return

    if now - last_entry >= REMINDER_THRESHOLD:
        print(
            "It's been over two hours since your last Kaydet entry. "
            "Capture what you've been up to with `kaydet --editor`."
        )


def append_entry(
    day_file: Path,
    uuid: str,
    timestamp: str,
    entry_text: str,
    metadata: Dict[str, str],
    explicit_tags: Iterable[str],
) -> Tuple[str, ...]:
    """Append a timestamped entry with a UUID and return all tags."""
    message_lines = entry_text.splitlines() or [entry_text]
    first_line = message_lines[0] if message_lines else ""
    extra_lines = tuple(message_lines[1:])
    embedded_tags = extract_tags_from_text(entry_text)
    unique_explicit = sorted(list(set(t.lower() for t in explicit_tags if t)))
    extra_tag_markers = [t for t in unique_explicit if t not in set(embedded_tags)]
    all_tags = deduplicate_tags(unique_explicit, message_lines)
    
    formatted_header = format_entry_header(timestamp, first_line, metadata, extra_tag_markers)
    header_line = f"{uuid}:{formatted_header}"

    with day_file.open("a", encoding="utf-8") as handle:
        handle.write(f"{header_line}\n")
        for line in extra_lines:
            handle.write(f"{line}\n")
    return all_tags


def run_search(
    db: sqlite3.Connection,
    log_dir: Path,
    config: SectionProxy,
    query: str,
    output_format: str = "text",
) -> None:
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
            run_doctor(db, log_dir, config)
            print()  # Add spacing after doctor output

    text_terms, metadata_filters, tag_filters = tokenize_query(query)
    if not any([text_terms, metadata_filters, tag_filters]):
        print("Search query is empty.")
        return

    params: List[str | float] = []
    from_clauses = ["entries e"]
    where_clauses: List[str] = []

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

    matches: List[DiaryEntry] = []
    day_file_pattern = config.get("DAY_FILE_PATTERN", DEFAULT_SETTINGS["DAY_FILE_PATTERN"])
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


def list_tags(db: sqlite3.Connection, output_format: str = "text") -> None:
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


def run_doctor(db: sqlite3.Connection, log_dir: Path, config: SectionProxy) -> None:
    """Rebuild the SQLite index from all existing diary files."""
    print("Rebuilding search index from diary files... This may take a moment.")
    for table in ["entries", "tags", "words", "metadata"]:
        db.execute(f"DELETE FROM {table}")
    db.commit()

    total_entries = 0
    for entry in iter_diary_entries(log_dir, config):
        words = extract_words_from_text(entry.text)
        full_metadata = {
            key: (value, num_value)
            for key, num_value in entry.metadata_numbers.items()
            if (value := entry.metadata.get(key)) is not None
        }
        database.add_entry(
            db=db,
            entry_uuid=entry.uuid,
            source_file=entry.source.name,
            timestamp=entry.timestamp,
            tags=entry.tags,
            words=words,
            metadata=full_metadata,
        )
        total_entries += 1

    if log_dir.exists():
        for child in log_dir.iterdir():
            if child.is_dir() and TAG_PATTERN.fullmatch(child.name):
                shutil.rmtree(child)

    print(f"Rebuilt search index for {total_entries} {'entry' if total_entries == 1 else 'entries'}.")

    # Print tag statistics
    cursor = db.cursor()
    cursor.execute("""
        SELECT tag_name, COUNT(*) as count
        FROM tags
        GROUP BY tag_name
        ORDER BY tag_name
    """)
    tag_stats = cursor.fetchall()
    if tag_stats:
        tag_list = ", ".join(f"#{tag}: {count}" for tag, count in tag_stats)
        print(f"Tags: {tag_list}")


def extract_words_from_text(text: str) -> List[str]:
    """Extracts and normalizes words from a string for full-text indexing."""
    return re.sub(r"[^\w\s]", "", text).lower().split()


def collect_month_counts(
    log_dir: Path, config: SectionProxy, year: int, month: int
) -> Dict[int, int]:
    """Return a mapping of day number to entry count for the given month."""
    counts: Dict[int, int] = defaultdict(int)
    day_file_pattern = config.get(
        "DAY_FILE_PATTERN", DEFAULT_SETTINGS["DAY_FILE_PATTERN"]
    )

    for candidate in sorted(log_dir.iterdir()):
        if not candidate.is_file():
            continue

        entry_date = resolve_entry_date(candidate, day_file_pattern)
        if entry_date is None:
            entry_date = datetime.fromtimestamp(
                candidate.stat().st_mtime
            ).date()

        if entry_date.year != year or entry_date.month != month:
            continue

        counts[entry_date.day] += count_entries(candidate)

    return dict(counts)


def show_calendar_stats(
    log_dir: Path,
    config: SectionProxy,
    now: datetime,
    output_format: str = "text",
) -> None:
    """Render a calendar for the current month with entry counts per day."""
    if not log_dir.exists():
        if output_format == "json":
            print(json.dumps({"error": "No diary entries found yet."}))
        else:
            print("No diary entries found yet.")
        return

    year = now.year
    month = now.month

    counts = collect_month_counts(log_dir, config, year, month)

    if output_format == "json":
        result = {
            "year": year,
            "month": month,
            "month_name": now.strftime("%B %Y"),
            "days": counts,
            "total_entries": sum(counts.values()),
        }
        print(json.dumps(result, indent=2))
    else:
        title = now.strftime("%B %Y")
        print(title)
        print("Mo Tu We Th Fr Sa Su")

        month_calendar = calendar.Calendar().monthdayscalendar(year, month)
        for week in month_calendar:
            cells = []
            for day in week:
                if day == 0:
                    cells.append("      ")
                    continue
                count = counts.get(day, 0)
                if count == 0:
                    cells.append(f"{day:2d}[  ]")
                elif count < 100:
                    cells.append(f"{day:2d}[{count:2d}]")
                else:
                    cells.append(f"{day:2d}[**]")
            print(" ".join(cells))

        total_entries = sum(counts.values())
        if total_entries == 0:
            print("\nNo entries recorded for this month yet.")
        else:
            print(f"\nTotal entries this month: {total_entries}")


def ensure_day_file(log_dir: Path, now: datetime, config: SectionProxy) -> Path:
    """Ensure the daily file exists and return its path."""
    log_dir.mkdir(parents=True, exist_ok=True)
    file_name = now.strftime(config["DAY_FILE_PATTERN"])
    day_file = log_dir / file_name
    if not day_file.exists():
        title = now.strftime(config["DAY_TITLE_PATTERN"])
        with day_file.open("w", encoding="utf-8") as handle:
            handle.write(f"{title}\n")
            handle.write("-" * (len(title) - 1))
            handle.write("\n")
    return day_file

def main() -> None:
    """Application entry point for the kaydet CLI."""
    config, config_path, config_dir = get_config()
    parser = argparse.ArgumentParser(
        prog="kaydet",
        description=__description__,
        epilog=dedent(
            f"""You can configure this by editing: {config_path}\n\n"""
            "  $ kaydet 'I am feeling grateful now.'\n"
            "  $ kaydet \"Fixed issue\" status:done time:45m #work\n"
            "  $ kaydet --editor"""
        ),
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("entry", type=str, nargs="*", metavar="Entry", help="Entry content.")
    parser.add_argument("--editor", "-e", dest="use_editor", action="store_true", help="Force opening editor.")
    parser.add_argument("--folder", "-f", dest="open_folder", nargs="?", const="", metavar="TAG", help="Open log directory.")
    parser.add_argument("--reminder", dest="reminder", action="store_true", help="Show reminder.")
    parser.add_argument("--stats", dest="stats", action="store_true", help="Show calendar stats.")
    parser.add_argument("--tags", dest="list_tags", action="store_true", help="List all tags.")
    parser.add_argument("--search", dest="search", metavar="TEXT", help="Search entries.")
    parser.add_argument("--doctor", dest="doctor", action="store_true", help="Rebuild search index.")
    parser.add_argument("--format", dest="output_format", choices=["text", "json"], default="text", help="Output format.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}", help="Show version.")
    args = parser.parse_args()

    log_dir = Path(config["LOG_DIR"]).expanduser()
    now = datetime.now()

    if args.reminder:
        maybe_show_reminder(config_dir, log_dir, now)
        return
    elif args.stats:
        show_calendar_stats(log_dir, config, now, args.output_format)
        return
    elif args.list_tags:
        log_dir.mkdir(parents=True, exist_ok=True)
        db_path = log_dir / INDEX_FILENAME
        db = database.get_db_connection(db_path)
        database.initialize_database(db)
        list_tags(db, args.output_format)
    elif args.search:
        log_dir.mkdir(parents=True, exist_ok=True)
        db_path = log_dir / INDEX_FILENAME
        db = database.get_db_connection(db_path)
        database.initialize_database(db)
        run_search(db, log_dir, config, args.search, args.output_format)
    elif args.doctor:
        log_dir.mkdir(parents=True, exist_ok=True)
        db_path = log_dir / INDEX_FILENAME
        db = database.get_db_connection(db_path)
        database.initialize_database(db)
        run_doctor(db, log_dir, config)
    elif args.open_folder is not None:
        if args.open_folder == "":
            startfile(str(log_dir))
        else:
            tag_name = args.open_folder.lstrip("#")
            print(
                "Tag folders are no longer maintained. "
                f"Search for '#{tag_name}' instead."
            )
        return
    else:
        log_dir.mkdir(parents=True, exist_ok=True)
        db_path = log_dir / INDEX_FILENAME
        db = database.get_db_connection(db_path)
        database.initialize_database(db)

        day_file = ensure_day_file(log_dir, now, config)
        raw_entry, metadata, explicit_tags = get_entry(args, config)
        entry_body = raw_entry.strip()
        if not entry_body and not metadata and not explicit_tags:
            print("Nothing to save.")
            return

        entry_uuid = shortuuid.uuid()
        timestamp = now.strftime("%H:%M")

        tags = append_entry(
            day_file=day_file,
            uuid=entry_uuid,
            timestamp=timestamp,
            entry_text=entry_body,
            metadata=metadata,
            explicit_tags=explicit_tags,
        )
        save_last_entry_timestamp(config_dir, now)
        
        words = extract_words_from_text(entry_body)
        full_metadata = {k: (v, parse_numeric_value(v)) for k, v in metadata.items()}
        
        database.add_entry(
            db=db,
            entry_uuid=entry_uuid,
            source_file=day_file.name,
            timestamp=timestamp,
            tags=tags,
            words=words,
            metadata=full_metadata,
        )
        print("Entry added to:", day_file)