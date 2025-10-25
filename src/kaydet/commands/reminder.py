"""Reminder command."""

from datetime import datetime
from pathlib import Path

from ..utils import load_last_entry_timestamp, REMINDER_THRESHOLD


def reminder_command(config_dir: Path, log_dir: Path, now: datetime):
    """Show reminder if no entry has been written recently."""
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
