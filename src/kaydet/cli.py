"""Command-line interface for the kaydet diary application."""

from __future__ import annotations

import argparse
import calendar
import json
import re
import shutil
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

from startfile import startfile

from . import __description__

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
ENTRY_LINE_PATTERN = re.compile(r"^\d{2}:\d{2}: ")
LEGACY_TAG_PATTERN = re.compile(r"^\[(?P<tags>[a-z-]+(?:,[a-z-]+)*)\]\s*")
HASHTAG_PATTERN = re.compile(r"#([a-z-]+)")
TAG_PATTERN = re.compile(r"^[a-z-]+$")
KEY_VALUE_PATTERN = re.compile(r"^(?P<key>[a-z][a-z0-9_-]*):(?P<value>.+)$")
NUMERIC_PATTERN = re.compile(r"^[-+]?\d+(?:\.\d+)?$")


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
    if not value:
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
        tag = None
        if token.startswith("#"):
            tag = normalize_tag(token)
        if tag:
            explicit_tags.append(tag)
            continue

        parsed = parse_metadata_token(token)
        if parsed:
            key, value = parsed
            metadata[key] = value
            continue

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
        metadata_text = " ".join(f"{key}:{value}" for key, value in metadata.items())
        segments.append(metadata_text)

    tag_markers = [f"#{tag}" for tag in extra_tag_markers if tag]
    if tag_markers:
        segments.append(" ".join(tag_markers))

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
        if not segment:
            continue
        for token in segment.split():
            tag = None
            if token.startswith("#"):
                tag = normalize_tag(token)
            if tag:
                explicit_tags.append(tag)
                continue

            parsed = parse_metadata_token(token)
            if parsed:
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
            tag = normalize_tag(token)
            if tag:
                tag_filters.append(tag)
            continue

        if ":" in token:
            key, value = token.split(":", 1)
            key = key.strip().lower()
            if key and value:
                metadata_filters.append((key, value.strip()))
                continue

        text_terms.append(token.lower())

    return text_terms, metadata_filters, tag_filters


def parse_range_expression(expression: str) -> Optional[Tuple[Optional[float], Optional[float]]]:
    """Parse a range expression like ``1..3`` into numeric bounds."""

    if ".." not in expression:
        return None

    lower_raw, upper_raw = expression.split("..", 1)
    lower = parse_numeric_value(lower_raw) if lower_raw.strip() else None
    upper = parse_numeric_value(upper_raw) if upper_raw.strip() else None

    if lower_raw.strip() and lower is None:
        return None
    if upper_raw.strip() and upper is None:
        return None

    return lower, upper


def parse_comparison_expression(expression: str) -> Optional[Tuple[str, float]]:
    """Parse comparison expressions like ``>=2`` or ``<5``."""

    for operator in (">=", "<=", ">", "<"):
        if expression.startswith(operator):
            remainder = expression[len(operator) :].strip()
            numeric = parse_numeric_value(remainder)
            if numeric is None:
                return None
            return operator, numeric
    return None


def metadata_filter_matches(
    entry: DiaryEntry, key: str, expression: str
) -> bool:
    """Evaluate whether the entry satisfies the metadata expression."""

    value = entry.metadata.get(key)
    if value is None:
        return False

    value_lower = value.lower()
    expression_lower = expression.lower()

    comparison = parse_comparison_expression(expression_lower)
    if comparison:
        numeric_value = entry.metadata_numbers.get(key)
        if numeric_value is None:
            return False
        operator, operand = comparison
        if operator == ">=":
            return numeric_value >= operand
        if operator == ">":
            return numeric_value > operand
        if operator == "<=":
            return numeric_value <= operand
        if operator == "<":
            return numeric_value < operand

    range_bounds = parse_range_expression(expression_lower)
    if range_bounds:
        numeric_value = entry.metadata_numbers.get(key)
        if numeric_value is None:
            return False
        lower, upper = range_bounds
        if lower is not None and numeric_value < lower:
            return False
        if upper is not None and numeric_value > upper:
            return False
        return True

    if any(char in expression_lower for char in "*?["):
        return fnmatch.fnmatch(value_lower, expression_lower)

    numeric_expression = parse_numeric_value(expression_lower)
    if numeric_expression is not None:
        numeric_value = entry.metadata_numbers.get(key)
        if numeric_value is None:
            return False
        return math.isclose(numeric_value, numeric_expression, rel_tol=1e-9)

    return value_lower == expression_lower


def entry_matches(
    entry: DiaryEntry,
    query_norm: str,
    text_terms: List[str],
    metadata_filters: List[Tuple[str, str]],
    tag_filters: List[str],
    use_advanced: bool,
) -> bool:
    """Determine whether the entry matches the provided query filters."""

    haystack = entry.text.lower()
    tag_text = " ".join(entry.tags).lower()
    metadata_text = " ".join(
        f"{key}:{value}" for key, value in entry.metadata.items()
    ).lower()

    if use_advanced:
        for key, expression in metadata_filters:
            if not metadata_filter_matches(entry, key, expression):
                return False

        for pattern in tag_filters:
            if not any(fnmatch.fnmatch(tag, pattern) for tag in entry.tags):
                return False

        for term in text_terms:
            if not (
                term in haystack
                or term in tag_text
                or term in metadata_text
            ):
                return False

        return True

    if query_norm in haystack:
        return True
    if tag_text and query_norm in tag_text:
        return True
    if metadata_text and query_norm in metadata_text:
        return True

    return False


def read_diary_lines(path: Path) -> List[str]:
    """Return diary file lines, tolerating non-UTF8 bytes by replacing them."""
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        text = path.read_text(encoding="utf-8", errors="replace")
    return text.splitlines()


@dataclass(frozen=True)
class DiaryEntry:
    """Structured view of a diary entry loaded from disk."""

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
            "date": self.day.isoformat() if self.day else None,
            "timestamp": self.timestamp,
            "text": self.text,
            "tags": list(self.tags),
            "metadata": self.metadata,
            "source": str(self.source),
        }


def parse_args(config_path: Path) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        prog="kaydet",
        description=__description__,
        epilog=dedent(
            f"""
            You can configure this by editing: {config_path}

              $ kaydet 'I am feeling grateful now.'
              $ kaydet \"When I'm typing this I felt that I need an editor\" --editor
            """
        ).strip(),
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "entry",
        type=str,
        nargs="*",
        metavar="Entry",
        help=(
            "Your entry to be saved. If not given, the configured editor will be "
            "opened for a longer note."
        ),
    )
    parser.add_argument(
        "--editor",
        "-e",
        dest="use_editor",
        action="store_true",
        help="Force opening the configured editor, even when an entry is provided.",
    )
    parser.add_argument(
        "--folder",
        "-f",
        dest="open_folder",
        nargs="?",
        const="",
        metavar="TAG",
        help="Open the main log directory or, if TAG is given, the tag folder.",
    )
    parser.add_argument(
        "--reminder",
        dest="reminder",
        action="store_true",
        help="Print a reminder if it has been more than two hours since the last entry.",
    )
    parser.add_argument(
        "--stats",
        dest="stats",
        action="store_true",
        help="Show a calendar for the current month with daily entry counts.",
    )
    parser.add_argument(
        "--tags",
        dest="list_tags",
        action="store_true",
        help="List every tag you have used so far and exit.",
    )
    parser.add_argument(
        "--search",
        dest="search",
        metavar="TEXT",
        help="Search diary entries for the given text and exit.",
    )
    parser.add_argument(
        "--doctor",
        dest="doctor",
        action="store_true",
        help="Rebuild tag archives from existing entries and exit.",
    )
    parser.add_argument(
        "--format",
        dest="output_format",
        choices=["text", "json"],
        default="text",
        help="Output format for search, tags, and stats commands (default: text).",
    )
    return parser.parse_args()


def get_entry(
    args: argparse.Namespace, config: SectionProxy
) -> Tuple[str, Dict[str, str], Tuple[str, ...]]:
    """Resolve entry content, metadata, and tags from CLI arguments or an editor."""

    tokens = list(args.entry or [])
    message_tokens, metadata, explicit_tags = partition_entry_tokens(tokens)

    message_text = " ".join(message_tokens)
    should_open_editor = args.use_editor or (
        not message_text and not metadata and not explicit_tags
    )

    if should_open_editor:
        entry_text = open_editor(message_text, config["EDITOR"])
    else:
        entry_text = message_text

    return entry_text, metadata, tuple(explicit_tags)


def open_editor(initial_text: str, editor_command: str) -> str:
    """Open a temporary file with the configured editor and return its contents."""
    fd, tmp_path = mkstemp()
    temp_file = Path(tmp_path)
    try:
        with fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(initial_text)
        subprocess.call([editor_command, str(temp_file)])
        return temp_file.read_text(encoding="utf-8")
    finally:
        try:
            remove(temp_file)
        except OSError:
            pass


def get_config() -> Tuple[SectionProxy, Path, Path]:
    """Load configuration and ensure defaults exist."""
    config_root = Path(env.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    config_dir = config_root / "kaydet"
    config_dir.mkdir(parents=True, exist_ok=True)

    parser = ConfigParser(interpolation=None)
    config_path = config_dir / "config.ini"

    if config_path.exists():
        parser.read(config_path, encoding="utf-8")

    updated = False
    if CONFIG_SECTION not in parser:
        parser[CONFIG_SECTION] = DEFAULT_SETTINGS.copy()
        updated = True

    section = parser[CONFIG_SECTION]
    for key, value in DEFAULT_SETTINGS.items():
        current = section.get(key)
        if current is None or current.strip() == "":
            section[key] = value
            updated = True

    if updated:
        with config_path.open("w", encoding="utf-8") as config_file:
            parser.write(config_file)

    return section, config_path, config_dir


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
            if candidate.is_file():
                mtime = candidate.stat().st_mtime
                if latest_mtime is None or mtime > latest_mtime:
                    latest_mtime = mtime
    if latest_mtime is None:
        return None
    return datetime.fromtimestamp(latest_mtime)


def save_last_entry_timestamp(config_dir: Path, moment: datetime) -> None:
    """Persist the provided timestamp for subsequent reminder checks."""
    record_path = config_dir / LAST_ENTRY_FILENAME
    record_path.write_text(moment.isoformat(), encoding="utf-8")


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


def ensure_day_file(
    log_dir: Path, now: datetime, config: SectionProxy
) -> Path:
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


def append_entry(
    day_file: Path,
    timestamp: str,
    entry_text: str,
    metadata: Dict[str, str],
    explicit_tags: Iterable[str],
) -> Tuple[str, Tuple[str, ...], Tuple[str, ...]]:
    """Append a timestamped entry and return stored lines and tags."""

    message_lines = entry_text.splitlines() or [entry_text]
    first_line = message_lines[0] if message_lines else ""
    extra_lines = tuple(message_lines[1:])

    embedded_tags = extract_tags_from_text(entry_text)
    embedded_set = set(embedded_tags)

    unique_explicit: List[str] = []
    for tag in explicit_tags:
        normalized = tag.lower()
        if normalized and normalized not in unique_explicit:
            unique_explicit.append(normalized)

    extra_tag_markers = [tag for tag in unique_explicit if tag not in embedded_set]
    all_tags = deduplicate_tags(unique_explicit, message_lines)

    header_line = format_entry_header(timestamp, first_line, metadata, extra_tag_markers)

    with day_file.open("a", encoding="utf-8") as handle:
        handle.write(f"{header_line}\n")
        for line in extra_lines:
            handle.write(f"{line}\n")

    return header_line, extra_lines, all_tags


def mirror_entry_to_tag_files(
    log_dir: Path,
    config: SectionProxy,
    now: datetime,
    header_line: str,
    extra_lines: Tuple[str, ...],
    tags: Tuple[str, ...],
) -> None:
    """Write the entry to per-tag daily files so tag archives stay in sync."""
    for tag in tags:
        tag_dir = log_dir / tag
        tag_day_file = ensure_day_file(tag_dir, now, config)
        with tag_day_file.open("a", encoding="utf-8") as handle:
            handle.write(f"{header_line}\n")
            for line in extra_lines:
                handle.write(f"{line}\n")


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


def resolve_entry_date(day_file: Path, pattern: str) -> Optional[date]:
    """Infer the date represented by a diary file using the configured pattern."""
    try:
        return datetime.strptime(day_file.name, pattern).date()
    except ValueError:
        return None


def count_entries(day_file: Path) -> int:
    """Count timestamped diary entries inside a daily file."""
    lines = read_diary_lines(day_file)
    return sum(1 for line in lines if ENTRY_LINE_PATTERN.match(line))


def parse_day_entries(day_file: Path, day: Optional[date]) -> List[DiaryEntry]:
    """Parse structured entries from a diary file."""
    lines = read_diary_lines(day_file)

    entries: List[DiaryEntry] = []
    current_time: Optional[str] = None
    current_lines: List[str] = []
    current_legacy_tags: List[str] = []
    current_metadata: Dict[str, str] = {}
    current_explicit_tags: List[str] = []

    for line in lines:
        if ENTRY_LINE_PATTERN.match(line):
            if current_time is not None:
                combined_initial_tags = current_legacy_tags + current_explicit_tags
                tags = deduplicate_tags(combined_initial_tags, current_lines)
                entries.append(
                    DiaryEntry(
                        day=day,
                        timestamp=current_time,
                        lines=tuple(current_lines),
                        tags=tags,
                        metadata=dict(current_metadata),
                        metadata_numbers=build_numeric_metadata(current_metadata),
                        source=day_file,
                    )
                )

            timestamp, remainder = line.split(": ", 1)
            legacy_tags: List[str] = []
            match = LEGACY_TAG_PATTERN.match(remainder)
            if match:
                legacy_tags.extend(match.group("tags").split(","))
                remainder = remainder[match.end() :]

            remainder = remainder.lstrip()
            message_line, parsed_metadata, explicit_tags = parse_stored_entry_remainder(
                remainder
            )

            current_time = timestamp
            current_lines = [message_line]
            current_legacy_tags = legacy_tags
            current_metadata = parsed_metadata
            current_explicit_tags = explicit_tags
        elif current_time is not None:
            current_lines.append(line)

    if current_time is not None:
        combined_initial_tags = current_legacy_tags + current_explicit_tags
        tags = deduplicate_tags(combined_initial_tags, current_lines)
        entries.append(
            DiaryEntry(
                day=day,
                timestamp=current_time,
                lines=tuple(current_lines),
                tags=tags,
                metadata=dict(current_metadata),
                metadata_numbers=build_numeric_metadata(current_metadata),
                source=day_file,
            )
        )

    return entries


def deduplicate_tags(
    initial_tags: Iterable[str], lines: Iterable[str]
) -> Tuple[str, ...]:
    """Return unique lowercase tags extracted from legacy markers and hashtags.

    >>> deduplicate_tags(['Work'], ['Focus #Idea', 'Next steps #work'])
    ('work', 'idea')
    >>> deduplicate_tags([], ['No tags here'])
    ()
    """
    seen: List[str] = []

    def register(tag: str) -> None:
        tag_lower = tag.lower()
        if tag_lower and tag_lower not in seen:
            seen.append(tag_lower)

    for tag in initial_tags:
        register(tag)

    for line in lines:
        for tag in HASHTAG_PATTERN.findall(line):
            register(tag)

    return tuple(seen)


def extract_tags_from_text(entry_text: str) -> Tuple[str, ...]:
    """Return all unique hashtags present in the entry text.

    >>> extract_tags_from_text("Dinner out #family #friends")
    ('family', 'friends')
    >>> extract_tags_from_text("Planning #projects\nNotes #ideas #projects")
    ('projects', 'ideas')
    >>> extract_tags_from_text("Just text")
    ()
    """

    if not entry_text:
        return ()

    lines = entry_text.splitlines() or [entry_text]
    return deduplicate_tags([], lines)


def iter_diary_entries(
    log_dir: Path, config: SectionProxy
) -> Iterable[DiaryEntry]:
    """Yield entries from every diary file sorted by filename."""
    if not log_dir.exists():
        return ()

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

        for entry in parse_day_entries(candidate, entry_date):
            yield entry


def run_search(
    log_dir: Path,
    config: SectionProxy,
    query: str,
    output_format: str = "text",
) -> None:
    """Search diary entries for the query and print any matches."""
    if not log_dir.exists():
        if output_format == "json":
            print(json.dumps({"error": "No diary entries found yet."}))
        else:
            print("No diary entries found yet.")
        return

    query_norm = query.lower()
    text_terms, metadata_filters, tag_filters = tokenize_query(query)
    use_advanced = bool(metadata_filters or tag_filters)
    matches: List[DiaryEntry] = []

    for entry in iter_diary_entries(log_dir, config):
        if entry_matches(
            entry,
            query_norm,
            text_terms,
            metadata_filters,
            tag_filters,
            use_advanced,
        ):
            matches.append(entry)

    if not matches:
        if output_format == "json":
            print(json.dumps({"query": query, "matches": [], "total": 0}))
        else:
            print(f"No entries matched '{query}'.")
        return

    if output_format == "json":
        result = {
            "query": query,
            "matches": [match.to_dict() for match in matches],
            "total": len(matches),
        }
        print(json.dumps(result, indent=2))
    else:
        for match in matches:
            day_label = (
                match.day.isoformat() if match.day else match.source.name
            )
            first_line, *rest = list(match.lines) or [""]

            followup_text = " ".join(match.lines[1:])
            extra_tags = []
            for tag in match.tags:
                marker = f"#{tag}"
                if marker not in first_line and marker not in followup_text:
                    extra_tags.append(marker)

            segments = [f"{day_label} {match.timestamp} {first_line}".rstrip()]

            if match.metadata:
                metadata_text = " ".join(
                    f"{key}:{value}" for key, value in match.metadata.items()
                )
                segments.append(metadata_text)

            if extra_tags:
                segments.append(" ".join(extra_tags))

            print(" | ".join(segment for segment in segments if segment))
            for extra in rest:
                print(f"    {extra}")
            print()

        total = len(matches)
        suffix = "entry" if total == 1 else "entries"
        print(f"Found {total} {suffix} containing '{query}'.")


def list_tags(
    log_dir: Path, config: SectionProxy, output_format: str = "text"
) -> None:
    """Print the unique set of tags recorded across all diary entries."""
    if not log_dir.exists():
        if output_format == "json":
            print(json.dumps({"error": "No diary entries found yet."}))
        else:
            print("No diary entries found yet.")
        return

    folders = sorted(
        child.name
        for child in log_dir.iterdir()
        if child.is_dir() and TAG_PATTERN.fullmatch(child.name)
    )
    if not folders:
        if output_format == "json":
            print(json.dumps({"tags": []}))
        else:
            print("No tags have been recorded yet.")
        return

    if output_format == "json":
        print(json.dumps({"tags": folders}, indent=2))
    else:
        for folder in folders:
            print(folder)


def run_doctor(log_dir: Path, config: SectionProxy) -> None:
    """Rebuild tag archives from existing diary entries."""
    if not log_dir.exists():
        print("Log directory does not exist yet; nothing to rebuild.")
        return

    entries = list(iter_diary_entries(log_dir, config))
    if not entries:
        print("No entries found; nothing to rebuild.")
        return

    # Remove existing tag directories so we can rebuild from scratch.
    removed = 0
    for child in log_dir.iterdir():
        if child.is_dir() and TAG_PATTERN.fullmatch(child.name):
            shutil.rmtree(child)
            removed += 1

    rebuilt_counts: Dict[str, int] = defaultdict(int)

    for entry in entries:
        if not entry.tags:
            continue

        entry_day = entry.day
        if entry_day is None:
            entry_day = datetime.fromtimestamp(
                entry.source.stat().st_mtime
            ).date()

        day_reference = datetime.combine(
            entry_day, datetime.strptime(entry.timestamp, "%H:%M").time()
        )

        message_lines = list(entry.lines)
        first_line = message_lines[0] if message_lines else ""
        extra_lines = message_lines[1:]
        embedded_tags = set(extract_tags_from_text("\n".join(message_lines)))
        extra_tag_markers = [tag for tag in entry.tags if tag not in embedded_tags]
        header_line = format_entry_header(
            entry.timestamp, first_line, entry.metadata, extra_tag_markers
        )

        for tag in entry.tags:
            tag_dir = log_dir / tag
            tag_day_file = ensure_day_file(tag_dir, day_reference, config)
            with tag_day_file.open("a", encoding="utf-8") as handle:
                handle.write(f"{header_line}\n")
                for line in extra_lines:
                    handle.write(f"{line}\n")
            rebuilt_counts[tag] += 1

    if not rebuilt_counts:
        if removed:
            print(
                "Removed existing tag folders but found no tagged entries to rebuild."
            )
        else:
            print("No tagged entries discovered; nothing to rebuild.")
        return

    summary = ", ".join(
        f"#{tag}: {count}" for tag, count in sorted(rebuilt_counts.items())
    )
    print(f"Rebuilt tag archives for {len(rebuilt_counts)} tags. {summary}")


def main() -> None:
    """Application entry point for the kaydet CLI."""
    config, config_path, config_dir = get_config()

    args = parse_args(config_path)

    log_dir = Path(config["LOG_DIR"]).expanduser()

    now = datetime.now()

    if args.reminder:
        maybe_show_reminder(config_dir, log_dir, now)
        return

    if args.stats:
        show_calendar_stats(log_dir, config, now, args.output_format)
        return

    if args.list_tags:
        list_tags(log_dir, config, args.output_format)
        return

    if args.search:
        run_search(log_dir, config, args.search, args.output_format)
        return

    if args.doctor:
        run_doctor(log_dir, config)
        return

    log_dir.mkdir(parents=True, exist_ok=True)

    if args.open_folder is not None:
        if args.open_folder == "":
            startfile(str(log_dir))
        else:
            tag_name = args.open_folder.lstrip("#")
            tag_dir = log_dir / tag_name
            if tag_dir.exists() and tag_dir.is_dir():
                startfile(str(tag_dir))
            else:
                print(f"No tag folder found for '#{tag_name}'.")
        return

    day_file = ensure_day_file(log_dir, now, config)

    raw_entry, metadata, explicit_tags = get_entry(args, config)
    entry_body = raw_entry.strip()

    if not entry_body and not metadata and not explicit_tags:
        print("Nothing to save.")
        return

    timestamp = now.strftime("%H:%M")
    header_line, extra_lines, tags = append_entry(
        day_file, timestamp, entry_body, metadata, explicit_tags
    )
    save_last_entry_timestamp(config_dir, now)

    if tags:
        mirror_entry_to_tag_files(
            log_dir, config, now, header_line, extra_lines, tags
        )

    print("Entry added to:", day_file)
