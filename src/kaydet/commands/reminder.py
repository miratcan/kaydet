"""Reminder command."""

from datetime import datetime
from pathlib import Path

from ..utils import REMINDER_THRESHOLD, load_last_entry_timestamp


def reminder_command(config_dir: Path, log_dir: Path, now: datetime):
    """Show reminder if no entry has been written recently."""
    last_entry = load_last_entry_timestamp(config_dir, log_dir)
    if last_entry is None:
        print(
            "\U0001f4ad No entries yet \u2014 "
            "capture your first note with `kaydet --editor`."
        )
        return

    if now - last_entry >= REMINDER_THRESHOLD:
        print(
            "\U0001f4ad Over two hours since your last entry \u2014 "
            "what have you been up to? (`kaydet --editor`)"
        )
