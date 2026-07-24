"""Tests for file-based attachment support."""

from datetime import date
from pathlib import Path

from kaydet.commands.add import _ensure_attachments_dir, store_attachment
from kaydet.models import Entry
from kaydet.parsers import (
    format_entry_header,
    parse_day_entries,
    parse_stored_entry_remainder,
)


def test_store_attachment_copies_file(tmp_path):
    """--attach should copy the file into attachments/."""
    source = tmp_path / "photo.jpg"
    source.write_bytes(b"fake-jpeg-data")
    log_dir = tmp_path / "logs"
    log_dir.mkdir()

    name = store_attachment(source, 42, log_dir)

    assert name == "42_photo.jpg"
    dest = log_dir / "attachments" / "42_photo.jpg"
    assert dest.exists()
    assert dest.read_bytes() == b"fake-jpeg-data"
    # Original must still exist
    assert source.exists()


def test_store_attachment_grab_removes_original(tmp_path):
    """--grab should move the file (original deleted)."""
    source = tmp_path / "report.pdf"
    source.write_bytes(b"fake-pdf-data")
    log_dir = tmp_path / "logs"
    log_dir.mkdir()

    name = store_attachment(source, 7, log_dir, move=True)

    assert name == "7_report.pdf"
    dest = log_dir / "attachments" / "7_report.pdf"
    assert dest.exists()
    assert dest.read_bytes() == b"fake-pdf-data"
    # Original must be gone
    assert not source.exists()


def test_ensure_attachments_dir_creates_once(tmp_path):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    d1 = _ensure_attachments_dir(log_dir)
    d2 = _ensure_attachments_dir(log_dir)
    assert d1 == d2
    assert d1.is_dir()


def test_format_entry_header_with_attachments():
    header = format_entry_header(
        "10:00",
        "Meeting notes",
        {},
        ("work",),
        entry_id="42",
        attachments=("42_slides.pdf",),
    )
    assert "attachment:42_slides.pdf" in header
    assert "10:00 [42]:" in header
    assert "#work" in header


def test_format_entry_header_without_attachments():
    header = format_entry_header(
        "10:00",
        "Hello",
        {},
        (),
        entry_id="1",
    )
    assert "attachment:" not in header


def test_parse_stored_entry_remainder_extracts_attachments():
    remainder = "Meeting notes attachment:42_slides.pdf #work"
    msg, meta, tags, attachments = parse_stored_entry_remainder(remainder)
    assert msg == "Meeting notes #work"
    assert attachments == ["42_slides.pdf"]
    assert "work" in tags
    assert "attachment" not in meta


def test_parse_stored_entry_remainder_no_attachments():
    remainder = "Just a message #tag"
    msg, meta, tags, attachments = parse_stored_entry_remainder(remainder)
    assert attachments == []
    assert msg == "Just a message #tag"


def test_parse_day_entries_with_attachments(tmp_path):
    day_file = tmp_path / "2026-04-11.txt"
    day_file.write_text(
        "10:00 [1]: Meeting attachment:1_slides.pdf #work\n11:00 [2]: Lunch\n",
        encoding="utf-8",
    )

    entries = parse_day_entries(day_file, date(2026, 4, 11))

    assert len(entries) == 2
    assert entries[0].attachments == ("1_slides.pdf",)
    assert entries[1].attachments == ()


def test_entry_model_with_attachments():
    entry = Entry(
        entry_id="1",
        day=date(2026, 4, 11),
        timestamp="10:00",
        lines=("Hello",),
        tags=(),
        metadata={},
        metadata_numbers={},
        source=Path("test.txt"),
        attachments=("1_photo.jpg",),
    )
    assert entry.attachments == ("1_photo.jpg",)
    d = entry.to_dict()
    assert d["attachments"] == ["1_photo.jpg"]


def test_entry_model_default_empty_attachments():
    entry = Entry(
        entry_id="1",
        day=date(2026, 4, 11),
        timestamp="10:00",
        lines=("Hello",),
        tags=(),
        metadata={},
        metadata_numbers={},
        source=Path("test.txt"),
    )
    assert entry.attachments == ()
    assert entry.to_dict()["attachments"] == []
