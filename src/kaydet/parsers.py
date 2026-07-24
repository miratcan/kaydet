"""Parsing utilities for diary entries, tags, and metadata."""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from .models import Entry

# Regex patterns
ENTRY_LINE_PATTERN = re.compile(
    r"^(?:[a-zA-Z0-9_-]{22}:)?"  # Optional legacy UUID prefix
    r"(\d{2}:\d{2})"  # Timestamp (HH:MM)
    r"(?:\s+\[\s*(\d+)\s*\])?"  # Optional ID like `[123]` or `[  123  ]`
    r":\s*(.*)"  # Remainder of the header line
)
LEGACY_TAG_PATTERN = re.compile(
    r"^[\[(](?P<tags>[a-z-]+(?:,[a-z-]+)*)[\])]\s*"
)
HASHTAG_PATTERN = re.compile(r"(?<!\\)#([a-z][a-z0-9_-]*)")
REAL_HASHTAG_TOKEN_PATTERN = re.compile(r"(?<!\\)#[a-z][a-z0-9_-]*")
TAG_PATTERN = re.compile(r"^[a-z-]+$")
KEY_VALUE_PATTERN = re.compile(r"^(?P<key>[a-z][a-z0-9_-]*):(?P<value>.+)")
NUMERIC_PATTERN = re.compile(r"^[-+]?\d+(?:\.\d+)?$")


def tokenize_query_terms(text: str) -> list[str]:
    """Split raw query text into shell-like tokens respecting quotes."""
    if not text:
        return []
    return shlex.split(text)


@dataclass
class Token:
    """A token parsed from a search query."""

    type: str
    value: str | tuple[str, str]


def _parse_base_token(word: str) -> Token:
    """Parses a word into a single non-exclusion token."""
    if "://" in word:
        return Token("WORD", word)

    if word.startswith("#"):
        return Token("TAG", word[1:])

    # Key: lowercase letter, then letters/numbers/_/-.
    if re.match(r"^[a-z][a-z0-9_-]*:", word):
        parts = word.split(":", 1)
        if len(parts) == 2 and parts[0] and parts[1]:
            return Token("METADATA", (parts[0], parts[1]))

    return Token("WORD", word)


def tokenize(text: str) -> list[Token]:
    """Converts a search query string into a list of tokens."""
    tokens = []
    for word in tokenize_query_terms(text):
        if word.startswith("-") and len(word) > 1:
            base = _parse_base_token(word[1:])
            tokens.append(Token(f"EXCLUDE_{base.type}", base.value))
            continue
        tokens.append(_parse_base_token(word))
    return tokens


def normalize_tag(tag: str) -> Optional[str]:
    """Normalize a tag token by stripping markers and lowercasing."""
    cleaned = tag.strip().lstrip("#").lower()
    match = re.match(r"^([a-z][a-z0-9_-]*)", cleaned)
    return match.group(1) if match else None


def parse_metadata_token(token: str) -> Optional[Tuple[str, str]]:
    """Return a ``(key, value)`` pair when the token encodes metadata."""
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
    if not value:
        return None

    if value.endswith("saat") and NUMERIC_PATTERN.match(value[:-4]):
        return float(value[:-4])
    if value.endswith("dk") and NUMERIC_PATTERN.match(value[:-2]):
        return float(value[:-2]) / 60.0
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
    """Extract message text, metadata, and tags from CLI tokens."""
    full_text = " ".join(tokens)
    tags = list(extract_tags_from_text(full_text))

    # Remove hashtags and unescape backslashes
    text_clean = REAL_HASHTAG_TOKEN_PATTERN.sub("", full_text).replace(
        "\\#", "#"
    )

    metadata: Dict[str, str] = {}
    message_parts: List[str] = []

    for word in text_clean.split():
        if parsed := parse_metadata_token(word):
            key, value = parsed
            metadata[key] = value
            continue
        message_parts.append(word)

    message_text = " ".join(message_parts).strip()
    return ([message_text] if message_text else []), metadata, tags


def format_entry_header(
    timestamp: str,
    message: str,
    metadata: Dict[str, str],
    extra_tag_markers: Iterable[str],
    *,
    entry_id: str | None = None,
    attachments: Iterable[str] = (),
) -> str:
    """Format the first line of a diary entry for storage."""
    time_block = f"{timestamp} [{entry_id}]" if entry_id else timestamp
    header = f"{time_block}: {message}" if message else f"{time_block}:"

    parts = [header.rstrip()]
    if metadata:
        parts.append(" ".join(f"{k}:{v}" for k, v in metadata.items()))
    if attachments:
        parts.append(" ".join(f"attachment:{a}" for a in attachments if a))
    if extra_tag_markers:
        parts.append(" ".join(f"#{t}" for t in extra_tag_markers if t))

    return " ".join(parts)


def parse_stored_entry_remainder(
    remainder: str,
) -> Tuple[str, Dict[str, str], List[str], List[str]]:
    """Parse the message, metadata, explicit tags, and attachments."""
    metadata: Dict[str, str] = {}
    explicit_tags: List[str] = []
    attachments: List[str] = []
    message_tokens: List[str] = []

    for token in remainder.split():
        if token.startswith("#"):
            if tag := normalize_tag(token):
                explicit_tags.append(tag)
            message_tokens.append(token)
            continue

        if token.startswith("attachment:"):
            attachments.append(token.split(":", 1)[1])
            continue

        if parsed := parse_metadata_token(token):
            key, value = parsed
            metadata[key] = value
            continue

        message_tokens.append(token)

    return (
        " ".join(message_tokens).rstrip(),
        metadata,
        explicit_tags,
        attachments,
    )


def tokenize_query(
    query: str,
) -> Tuple[
    List[str],
    List[str],
    List[Tuple[str, str]],
    List[Tuple[str, str]],
    List[str],
    List[str],
]:
    """Split a query into text, metadata, and tag filters."""
    text, ex_text, meta, ex_meta, tags, ex_tags = [], [], [], [], [], []

    for token in tokenize(query):
        if token.type == "WORD":
            text.append(token.value.lower())
        elif token.type == "TAG":
            tags.append(token.value)
        elif token.type == "METADATA":
            meta.append(token.value)
        elif token.type == "EXCLUDE_WORD":
            ex_text.append(token.value.lower())
        elif token.type == "EXCLUDE_TAG":
            ex_tags.append(token.value)
        elif token.type == "EXCLUDE_METADATA":
            ex_meta.append(token.value)

    return text, ex_text, meta, ex_meta, tags, ex_tags


def parse_range_expression(
    expression: str,
) -> Optional[Tuple[Optional[float], Optional[float]]]:
    """Parse a range expression like ``1..3`` into numeric bounds."""
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
    """Parse comparison expressions like ``>=2`` or ``<5``."""
    for op in (">=", "<=", ">", "<"):
        if not expression.startswith(op):
            continue
        val_str = expression[len(op) :].strip()
        if (val := parse_numeric_value(val_str)) is not None:
            return op, val
    return None


def read_diary_lines(path: Path) -> List[str]:
    """Return diary file lines, tolerating non-UTF8 bytes."""
    try:
        return path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace").splitlines()


def count_entries(day_file: Path) -> int:
    """Count timestamped diary entries inside a daily file."""
    lines = read_diary_lines(day_file)
    return sum(1 for line in lines if ENTRY_LINE_PATTERN.match(line))


@dataclass
class _ParserState:
    """Internal state for the day entries parser."""

    day: Optional[date]
    source: Path
    time: Optional[str] = None
    entry_id: Optional[str] = None
    lines: List[str] = None
    legacy_tags: List[str] = None
    metadata: Dict[str, str] = None
    explicit_tags: List[str] = None
    attachments: List[str] = None

    def __post_init__(self):
        self.lines = []
        self.legacy_tags = []
        self.metadata = {}
        self.explicit_tags = []
        self.attachments = []

    def finalize(self, entries: List[Entry]):
        if self.time is None:
            return
        combined = self.legacy_tags + self.explicit_tags
        tags = deduplicate_tags(combined, self.lines)
        entries.append(
            Entry(
                entry_id=self.entry_id,
                day=self.day,
                timestamp=self.time,
                lines=tuple(self.lines),
                tags=tags,
                metadata=dict(self.metadata),
                metadata_numbers=build_numeric_metadata(self.metadata),
                source=self.source,
                attachments=tuple(self.attachments),
            )
        )
        self.entry_id = None
        self.time = None
        self.attachments = []


def parse_day_entries(day_file: Path, day: Optional[date]) -> List[Entry]:
    """Parse diary entries, supporting both UUID and legacy formats."""
    lines = read_diary_lines(day_file)
    entries: List[Entry] = []
    state = _ParserState(day, day_file)

    for line in lines:
        match = ENTRY_LINE_PATTERN.match(line)
        if not match:
            if state.time is not None:
                state.lines.append(line)
            continue

        state.finalize(entries)
        time_part, id_part, remainder = match.groups()
        state.time = time_part.strip(":")
        state.entry_id = id_part.strip() if id_part else None

        legacy_match = LEGACY_TAG_PATTERN.match(remainder)
        if legacy_match:
            state.legacy_tags = legacy_match.group("tags").split(",")
            remainder = remainder[legacy_match.end() :]
        else:
            state.legacy_tags = []

        msg, meta, tags, attachments = parse_stored_entry_remainder(
            remainder.lstrip()
        )
        state.lines = [msg]
        state.metadata = meta
        state.explicit_tags = tags
        state.attachments = attachments

    state.finalize(entries)
    return entries


def deduplicate_tags(
    initial_tags: Iterable[str],
    lines: Iterable[str],
) -> Tuple[str, ...]:
    """Return unique lowercase tags from explicit and inline markers."""
    seen: List[str] = []

    def register(tag: str):
        if (tag_low := tag.lower()) and tag_low not in seen:
            seen.append(tag_low)

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
    """Extract and normalize words from a string."""
    return re.sub(r"[^\w\s]", "", text).lower().split()


def resolve_entry_date(day_file: Path, pattern: str) -> Optional[date]:
    """Infer a diary date from the file name and pattern."""
    try:
        return datetime.strptime(day_file.name, pattern).date()
    except ValueError:
        return None
