"""Parsing utilities for diary entries, tags, and metadata."""

from __future__ import annotations

import hashlib
import re
import shlex
from datetime import date, datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from .models import DiaryEntry

# Regex patterns
ENTRY_LINE_PATTERN = re.compile(r"^(?:([a-zA-Z0-9_-]{22}):)?(\d{2}:\d{2}): (.*)")
LEGACY_TAG_PATTERN = re.compile(r"^[\[(](?P<tags>[a-z-]+(?:,[a-z-]+)*)[\])]\s*")
HASHTAG_PATTERN = re.compile(r"#([a-z-]+)")
TAG_PATTERN = re.compile(r"^[a-z-]+$")
KEY_VALUE_PATTERN = re.compile(r"^(?P<key>[a-z][a-z0-9_-]*):(?P<value>.+)")
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


def extract_words_from_text(text: str) -> List[str]:
    """Extracts and normalizes words from a string for full-text indexing."""
    return re.sub(r"[^\w\s]", "", text).lower().split()


def resolve_entry_date(day_file: Path, pattern: str) -> Optional[date]:
    """Infer the date represented by a diary file using the configured pattern."""
    try:
        return datetime.strptime(day_file.name, pattern).date()
    except ValueError:
        return None
