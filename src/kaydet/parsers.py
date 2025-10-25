"""Parsing utilities for diary entries, tags, and metadata."""

from __future__ import annotations

import hashlib
import re
import shlex
from datetime import date, datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from .models import Entry

# Regex patterns
ENTRY_LINE_PATTERN = re.compile(
    r"^(?:([a-zA-Z0-9_-]{22}):)?"  # Optional legacy UUID prefix
    r"(\d{2}:\d{2})"  # Timestamp (HH:MM)
    r"(?:\s+\[(.+?)\])?"  # Optional identifier like `[123]`
    r":\s*(.*)"  # Remainder of the header line
)
LEGACY_TAG_PATTERN = re.compile(
    r"^[\[(](?P<tags>[a-z-]+(?:,[a-z-]+)*)[\])]\s*"
)
HASHTAG_PATTERN = re.compile(r"#([a-z-]+)")
TAG_PATTERN = re.compile(r"^[a-z-]+$")
KEY_VALUE_PATTERN = re.compile(r"^(?P<key>[a-z][a-z0-9_-]*):(?P<value>.+)")
NUMERIC_PATTERN = re.compile(r"^[-+]?\d+(?:\.\d+)?$")


def normalize_tag(tag: str) -> Optional[str]:
    """Normalize a tag token by stripping markers and lowercasing.

    Example:
        >>> normalize_tag("#Work")
        'work'
    """
    cleaned = tag.strip().lstrip("#").lower()
    return cleaned if cleaned else None


def parse_metadata_token(token: str) -> Optional[Tuple[str, str]]:
    """Return a ``(key, value)`` pair when the token encodes metadata.

    Example:
        >>> parse_metadata_token("time:2h")
        ('time', '2h')
    """
    match = KEY_VALUE_PATTERN.match(token)
    if not match:
        return None
    key = match.group("key").lower()
    value = match.group("value").strip()
    if not value or value.startswith("//"):
        return None
    return key, value


def parse_numeric_value(raw_value: str) -> Optional[float]:
    """Convert a metadata value to a numeric representation when possible.

    Example:
        >>> parse_numeric_value("90m")
        1.5
    """
    value = raw_value.strip().lower()
    if value.endswith("h") and NUMERIC_PATTERN.match(value[:-1]):
        return float(value[:-1])
    if value.endswith("m") and NUMERIC_PATTERN.match(value[:-1]):
        return float(value[:-1]) / 60.0
    if NUMERIC_PATTERN.match(value):
        return float(value)
    return None


def build_numeric_metadata(metadata: Dict[str, str]) -> Dict[str, float]:
    """Return numeric representations for metadata values when available.

    Example:
        >>> build_numeric_metadata({"time": "2h", "status": "done"})
        {'time': 2.0}
    """
    numeric: Dict[str, float] = {}
    for key, value in metadata.items():
        converted = parse_numeric_value(value)
        if converted is not None:
            numeric[key] = converted
    return numeric


def partition_entry_tokens(
    tokens: Iterable[str],
) -> Tuple[List[str], Dict[str, str], List[str]]:
    """Split CLI tokens into message text, metadata, and explicit tags.

    Example:
        >>> partition_entry_tokens(["Fix", "bug", "time:1h", "#work"])
        (['Fix', 'bug'], {'time': '1h'}, ['work'])
    """
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
    """Format the first line of a diary entry for storage.

    Example:
        >>> format_entry_header("10:00", "Shipped release",
        ...                    {"status": "done"}, ["work"])
        '10:00: Shipped release | status:done | #work'
    """
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
    """Parse the message, metadata, and explicit tags from a stored line.

    Example:
        >>> parse_stored_entry_remainder(
        ...     "Start | status:done | #work #release"
        ... )
        ('Start', {'status': 'done'}, ['work', 'release'])
    """
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
    """Split a query into text terms, metadata filters, and tag filters.

    Example:
        >>> tokenize_query("#work status:done focus")
        (['focus'], [('status', 'done')], ['work'])
    """
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


def parse_range_expression(
    expression: str,
) -> Optional[Tuple[Optional[float], Optional[float]]]:
    """Parse a range expression like ``1..3`` into numeric bounds.

    Example:
        >>> parse_range_expression("1..3")
        (1.0, 3.0)
    """
    if ".." not in expression:
        return None
    lower_raw, upper_raw = expression.split("..", 1)
    lower = parse_numeric_value(lower_raw) if lower_raw.strip() else None
    upper = parse_numeric_value(upper_raw) if upper_raw.strip() else None
    if (lower_raw.strip() and lower is None) or (
        upper_raw.strip() and upper is None
    ):
        return None
    return lower, upper


def parse_comparison_expression(
    expression: str,
) -> Optional[Tuple[str, float]]:
    """Parse comparison expressions like ``>=2`` or ``<5``.

    Example:
        >>> parse_comparison_expression("<=3")
        ('<=', 3.0)
    """
    for operator in (">=", "<=", ">", "<"):
        if expression.startswith(operator):
            remainder = expression[len(operator) :].strip()
            if (numeric := parse_numeric_value(remainder)) is not None:
                return operator, numeric
    return None


def read_diary_lines(path: Path) -> List[str]:
    """Return diary file lines, tolerating non-UTF8 bytes by replacing them.

    Example:
        >>> tmp = Path("example.txt")
        >>> _ = tmp.write_text("hello\\n", encoding="utf-8")
        >>> read_diary_lines(tmp)
        ['hello']
        >>> tmp.unlink()
    """
    try:
        return path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace").splitlines()


def count_entries(day_file: Path) -> int:
    """Count timestamped diary entries inside a daily file.

    Example:
        >>> tmp = Path("count.txt")
        >>> _ = tmp.write_text("10:00: note\\n")
        >>> count_entries(tmp)
        1
        >>> tmp.unlink()
    """
    lines = read_diary_lines(day_file)
    return sum(1 for line in lines if ENTRY_LINE_PATTERN.match(line))


def parse_day_entries(day_file: Path, day: Optional[date]) -> List[Entry]:
    """Parse diary entries, supporting both UUID and legacy formats.

    Example:
        >>> tmp = Path("entry.txt")
        >>> _ = tmp.write_text("10:00: Hello world\\n")
        >>> entries = parse_day_entries(tmp, date(2025, 1, 1))
        >>> len(entries), entries[0].lines[0]
        (1, 'Hello world')
        >>> tmp.unlink()
    """
    lines = read_diary_lines(day_file)
    entries: List[Entry] = []
    current_uuid: Optional[str] = None
    current_time: Optional[str] = None
    current_entry_id: Optional[str] = None
    current_lines: List[str] = []
    current_legacy_tags: List[str] = []
    current_metadata: Dict[str, str] = {}
    current_explicit_tags: List[str] = []

    def finalize_entry():
        nonlocal current_entry_id
        if current_time is None:
            return
        # Prefer numeric identifiers when available, otherwise fall back to
        # stored UUIDs or deterministic hashes.
        if current_entry_id and current_entry_id.isdigit():
            entry_uuid = f"{day_file.name}:{current_entry_id}"
        elif current_uuid:
            entry_uuid = current_uuid
        else:
            # Build a deterministic UUID from path, timestamp, and first line.
            first_line = current_lines[0] if current_lines else ""
            seed = f"{day_file.name}:{current_time}:{first_line}"
            hash_digest = hashlib.sha256(seed.encode()).hexdigest()
            # Use first 22 chars of hash as deterministic UUID
            entry_uuid = hash_digest[:22]
        combined_tags = current_legacy_tags + current_explicit_tags
        tags = deduplicate_tags(combined_tags, current_lines)
        entries.append(
            Entry(
                uuid=entry_uuid,
                entry_id=current_entry_id,
                day=day,
                timestamp=current_time,
                lines=tuple(current_lines),
                tags=tags,
                metadata=dict(current_metadata),
                metadata_numbers=build_numeric_metadata(current_metadata),
                source=day_file,
            )
        )
        current_entry_id = None

    for line in lines:
        match = ENTRY_LINE_PATTERN.match(line)
        if match:
            finalize_entry()
            uuid_part, time_part, identifier_part, remainder = match.groups()
            current_uuid = uuid_part
            current_time = time_part.strip(":")
            current_entry_id = identifier_part.strip() if identifier_part else None

            legacy_match = LEGACY_TAG_PATTERN.match(remainder)
            if legacy_match:
                current_legacy_tags = legacy_match.group("tags").split(",")
                remainder = remainder[legacy_match.end() :]
            else:
                current_legacy_tags = []

            remainder = remainder.lstrip()
            message_line, parsed_metadata, explicit_tags = (
                parse_stored_entry_remainder(remainder)
            )
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
    """Return unique lowercase tags from explicit and inline markers.

    Example:
        >>> deduplicate_tags(['Work'], ['Note about #Work and #focus'])
        ('work', 'focus')
    """
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
    """Return all unique hashtags present in the entry text.

    Example:
        >>> extract_tags_from_text("Meeting notes #work #sync")
        ('work', 'sync')
    """
    if not entry_text:
        return ()
    return deduplicate_tags([], entry_text.splitlines() or [entry_text])


def extract_words_from_text(text: str) -> List[str]:
    """Extract and normalize words from a string for full-text indexing.

    Example:
        >>> extract_words_from_text("Ship MVP!")
        ['ship', 'mvp']
    """
    return re.sub(r"[^\w\s]", "", text).lower().split()


def resolve_entry_date(day_file: Path, pattern: str) -> Optional[date]:
    """Infer a diary date from the file name and configured pattern.

    Example:
        >>> resolve_entry_date(Path("2025-01-01.txt"), "%Y-%m-%d.txt")
        datetime.date(2025, 1, 1)
    """
    try:
        return datetime.strptime(day_file.name, pattern).date()
    except ValueError:
        return None
