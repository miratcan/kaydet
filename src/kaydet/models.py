"""Data models for kaydet diary entries."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict, Optional, Tuple


@dataclass(frozen=True)
class Entry:
    """Structured view of a diary entry loaded from disk."""

    entry_id: Optional[str]
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
            "id": self.entry_id,
            "date": self.day.isoformat() if self.day else None,
            "timestamp": self.timestamp,
            "text": self.text,
            "tags": list(self.tags),
            "metadata": self.metadata,
            "source": str(self.source),
        }
