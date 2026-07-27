from __future__ import annotations

import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import pytest

from kaydet import cli


def test_add_simple_entry(setup_kaydet, mock_datetime_factory):
    """Test that a simple entry can be added via a CLI argument."""
    fake_log_dir = setup_kaydet["fake_log_dir"]
    monkeypatch = setup_kaydet["monkeypatch"]
    mock_datetime_factory(datetime(2025, 9, 30, 10, 30, 0))

    entry_text = "my first test entry"
    monkeypatch.setattr(sys, "argv", ["kaydet", entry_text])

    cli.main()

    log_file = fake_log_dir / "2025-09-30.txt"
    assert log_file.exists()
    content = log_file.read_text()
    assert "2025/09/30/ - Tuesday" in content
    regex = (
        r"2025/09/30/ - Tuesday\n"
        r"--------------------\n"
        r"10:30 \[\d+\]: my first test entry\n"
    )
    assert re.search(regex, content)


def test_add_multiline_cli_argument(setup_kaydet, mock_datetime_factory):
    """Quoted multiline argv keeps body lines (not one collapsed line)."""
    fake_log_dir = setup_kaydet["fake_log_dir"]
    monkeypatch = setup_kaydet["monkeypatch"]
    mock_datetime_factory(datetime(2025, 9, 30, 10, 45, 0))

    entry_text = "line 1\n\nline 2\n\nline 3"
    monkeypatch.setattr(sys, "argv", ["kaydet", entry_text])

    cli.main()

    content = (fake_log_dir / "2025-09-30.txt").read_text()
    assert re.search(r"10:45 \[\d+\]: line 1\n", content)
    assert "\nline 2\n" in content
    assert "\nline 3\n" in content
    # Must not collapse to a single header line
    assert "line 1 line 2 line 3" not in content


def test_add_entry_with_tags(setup_kaydet, mock_datetime_factory):
    """Test that an entry with hashtags is captured in the new SQLite index."""
    fake_log_dir = setup_kaydet["fake_log_dir"]
    monkeypatch = setup_kaydet["monkeypatch"]
    mock_datetime_factory(datetime(2025, 9, 30, 11, 0, 0))

    entry_text = "This is a test for #work and #project-a"
    monkeypatch.setattr(sys, "argv", ["kaydet", entry_text])

    cli.main()

    # 1. Check the text file for the new format
    main_log_file = fake_log_dir / "2025-09-30.txt"
    assert main_log_file.exists()
    content = main_log_file.read_text()

    # --- DIAGNOSTIC PRINT ---
    print(f"\n--- LOG FILE CONTENT ---\n{content}\n------------------------")

    # Check for the new format with numeric IDs
    # Tags are now extracted from message and appended naturally
    assert re.search(
        r"2025/09/30/ - Tuesday\n--------------------\n"
        r"11:00 \[\d+\]: This is a test for and "
        r"#project-a #work\n",
        content,
    )

    # 2. Check the SQLite database
    fake_index_dir = setup_kaydet["fake_index_dir"]
    db_path = fake_index_dir / "index.db"
    assert db_path.exists()
    db = sqlite3.connect(db_path)
    cursor = db.cursor()

    # Find the entry_id associated with the tags
    cursor.execute(
        (
            "SELECT tag_name FROM tags "
            "WHERE entry_id = (SELECT id FROM entries "
            "WHERE timestamp = '11:00') "
            "ORDER BY tag_name"
        )
    )
    tags_in_db = [row[0] for row in cursor.fetchall()]
    assert tags_in_db == ["project-a", "work"]

    db.close()


def test_add_entry_with_metadata_tokens(setup_kaydet, mock_datetime_factory):
    """Entries with metadata tokens persist them in SQLite."""

    fake_log_dir = setup_kaydet["fake_log_dir"]
    monkeypatch = setup_kaydet["monkeypatch"]
    mock_datetime_factory(datetime(2025, 9, 30, 13, 30, 0))

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "kaydet",
            "Fixed",
            "bug",
            "commit:38edf60",
            "pr:76",
            "status:done",
            "time:2h",
            "#urgent",
        ],
    )

    cli.main()

    day_file = fake_log_dir / "2025-09-30.txt"
    assert day_file.exists()
    content = day_file.read_text()
    assert re.search(
        (
            r"13:30 \[\d+\]: Fixed bug | commit:38edf60 "
            r"pr:76 status:done time:2h | #urgent"
        ),
        content,
    )

    fake_index_dir = setup_kaydet["fake_index_dir"]
    db_path = fake_index_dir / "index.db"
    assert db_path.exists()
    db = sqlite3.connect(db_path)
    cursor = db.cursor()

    cursor.execute("SELECT id FROM entries WHERE timestamp = '13:30'")
    entry_id = cursor.fetchone()[0]

    cursor.execute(
        (
            "SELECT meta_key, meta_value FROM metadata "
            "WHERE entry_id = ? ORDER BY meta_key"
        ),
        (entry_id,),
    )
    metadata_in_db = dict(cursor.fetchall())
    assert metadata_in_db == {
        "commit": "38edf60",
        "pr": "76",
        "status": "done",
        "time": "2h",
    }

    cursor.execute("SELECT tag_name FROM tags WHERE entry_id = ?", (entry_id,))
    tag_in_db = cursor.fetchone()[0]
    assert tag_in_db == "urgent"

    db.close()


def test_add_entry_prints_id(setup_kaydet, mock_datetime_factory, capsys):
    """Adding an entry should report the new numeric identifier."""
    monkeypatch = setup_kaydet["monkeypatch"]
    mock_datetime_factory(datetime(2025, 9, 30, 14, 0, 0))

    monkeypatch.setattr(sys, "argv", ["kaydet", "Check ID output"])
    capsys.readouterr()

    cli.main()

    output = capsys.readouterr().out
    assert "Entry Added" in output
    assert "ID:" in output


def test_editor_usage(setup_kaydet, mock_datetime_factory):
    """Test that the editor is used when no entry is provided."""
    fake_log_dir = setup_kaydet["fake_log_dir"]
    monkeypatch = setup_kaydet["monkeypatch"]
    mock_datetime_factory(datetime(2025, 9, 30, 12, 0, 0))

    monkeypatch.setattr(sys, "argv", ["kaydet"])

    editor_text = "This entry came from the editor."
    monkeypatch.setattr(
        "kaydet.commands.add.open_editor", lambda *args: editor_text
    )

    cli.main()

    log_file = fake_log_dir / "2025-09-30.txt"
    assert log_file.exists()
    content = log_file.read_text()
    assert re.search(
        r"2025/09/30/ - Tuesday\n--------------------\n"
        r"12:00 \[\d+\]: This entry came from the editor.\n",
        content,
    )


def test_open_editor_flow(setup_kaydet, mock_datetime_factory, mocker):
    """Test the full flow of opening an editor and saving the content."""
    fake_log_dir = setup_kaydet["fake_log_dir"]
    monkeypatch = setup_kaydet["monkeypatch"]
    mock_datetime_factory(datetime(2025, 10, 1, 15, 0, 0))

    editor_content = "Text written in the mocked editor."

    def fake_subprocess_call(command_list):
        temp_file_path = Path(command_list[1])
        temp_file_path.write_text(editor_content, encoding="utf-8")

    mock_call = mocker.patch(
        "kaydet.cli.subprocess.call", side_effect=fake_subprocess_call
    )

    monkeypatch.setattr(sys, "argv", ["kaydet", "--editor"])

    cli.main()

    mock_call.assert_called_once()
    log_file = fake_log_dir / "2025-10-01.txt"
    assert log_file.exists()
    assert editor_content in log_file.read_text()


def test_empty_entry_from_editor(setup_kaydet, capsys, mock_datetime_factory):
    """Test that saving an empty entry from the editor does nothing."""
    fake_log_dir = setup_kaydet["fake_log_dir"]
    monkeypatch = setup_kaydet["monkeypatch"]
    mock_datetime_factory(datetime(2025, 9, 30, 12, 0, 0))

    monkeypatch.setattr(sys, "argv", ["kaydet"])

    monkeypatch.setattr(
        "kaydet.commands.add.open_editor", lambda *args: " \n "
    )

    cli.main()

    captured = capsys.readouterr()
    assert "Nothing to save" in captured.out

    log_file = fake_log_dir / "2025-09-30.txt"
    assert log_file.exists()
    content = log_file.read_text()
    assert "12:00:" not in content


# --- Tests for load_config (without setup_kaydet fixture) ---


def test_add_entry_with_at_flag(setup_kaydet, mock_datetime_factory, capsys):
    """Test adding entries with the --at flag for custom timestamps."""
    fake_log_dir = setup_kaydet["fake_log_dir"]
    monkeypatch = setup_kaydet["monkeypatch"]

    # 1. Setup initial entries for chronological test
    mock_datetime_factory(datetime(2025, 10, 25, 10, 0, 0))
    monkeypatch.setattr(sys, "argv", ["kaydet", "First entry"])
    cli.main()

    mock_datetime_factory(datetime(2025, 10, 25, 12, 0, 0))
    monkeypatch.setattr(sys, "argv", ["kaydet", "Third entry"])
    cli.main()
    capsys.readouterr()  # Clear stdout

    # 2. Inject an entry into the middle of the day
    mock_datetime_factory(datetime(2025, 10, 25, 14, 0, 0))  # "now" is 14:00
    monkeypatch.setattr(
        sys,
        "argv",
        ["kaydet", "Second entry", "--at", "11:00"],
    )
    cli.main()

    day_file = fake_log_dir / "2025-10-25.txt"
    content = day_file.read_text()
    assert "Entry Added" in capsys.readouterr().out
    # Check chronological order
    assert re.search(
        r"10:00.*First entry.*\n11:00.*Second entry.*\n12:00.*Third entry",
        content,
        re.DOTALL,
    )

    # 3. Inject an entry into a past date
    monkeypatch.setattr(
        sys,
        "argv",
        ["kaydet", "A past entry", "--at", "2025-10-24:15:00"],
    )
    cli.main()

    past_day_file = fake_log_dir / "2025-10-24.txt"
    assert past_day_file.exists()
    past_content = past_day_file.read_text()
    assert "15:00" in past_content
    assert "A past entry" in past_content

    # 4. Test blocking future entries
    monkeypatch.setattr(
        sys,
        "argv",
        ["kaydet", "A future entry", "--at", "2025-10-26:10:00"],
    )
    cli.main()
    assert "Can't log entries in the future" in capsys.readouterr().out

    # 5. Test invalid format
    monkeypatch.setattr(
        sys,
        "argv",
        ["kaydet", "Invalid time", "--at", "not-a-time"],
    )
    with pytest.raises(ValueError, match="Invalid --at format"):
        cli.main()
