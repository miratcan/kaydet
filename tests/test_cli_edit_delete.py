from __future__ import annotations

import re
import sqlite3
import sys
from datetime import datetime, timedelta

from kaydet import cli


def test_edit_command_updates_entry(
    setup_kaydet, mock_datetime_factory, capsys
):
    """Editing by ID should update the diary file and reindex metadata."""

    fake_log_dir = setup_kaydet["fake_log_dir"]
    monkeypatch = setup_kaydet["monkeypatch"]

    mock_datetime_factory(datetime(2025, 9, 30, 9, 0, 0))
    monkeypatch.setattr(
        sys,
        "argv",
        ["kaydet", "Original body text", "status:wip", "#focus"],
    )
    cli.main()
    capsys.readouterr()

    mock_datetime_factory(datetime(2025, 9, 30, 10, 0, 0))
    monkeypatch.setattr(sys, "argv", ["kaydet", "Another entry #later"])
    cli.main()
    capsys.readouterr()

    fake_index_dir = setup_kaydet["fake_index_dir"]
    db_path = fake_index_dir / "index.db"
    with sqlite3.connect(db_path) as db:
        cursor = db.cursor()
        cursor.execute("SELECT id FROM entries WHERE timestamp = '09:00'")
        entry_id = cursor.fetchone()[0]

    edited_content = (
        f"09:00 [{entry_id}]: Updated body | status:done | #focus\n"
        "Follow-up detail\n"
    )
    monkeypatch.setattr(
        "kaydet.commands.edit.open_editor",
        lambda *_args, **_kwargs: edited_content,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["kaydet", "--edit", str(entry_id)],
    )

    cli.main()
    output = capsys.readouterr().out
    assert f"Entry Updated (ID: {entry_id})" in output

    day_file = fake_log_dir / "2025-09-30.txt"
    content = day_file.read_text()
    assert "Updated body" in content
    assert "Follow-up detail" in content
    assert "status:done" in content

    with sqlite3.connect(db_path) as db:
        cursor = db.cursor()
        cursor.execute(
            (
                "SELECT meta_value FROM metadata "
                "WHERE entry_id = ? AND meta_key = 'status'"
            ),
            (entry_id,),
        )
        assert cursor.fetchone()[0] == "done"
        cursor.execute(
            (
                "SELECT COUNT(*) FROM tags "
                "WHERE entry_id = ? AND tag_name = 'focus'"
            ),
            (entry_id,),
        )
        assert cursor.fetchone()[0] == 1


def test_delete_command_removes_entry(
    setup_kaydet, mock_datetime_factory, capsys
):
    """Deleting by ID should remove the entry from disk and index."""

    fake_log_dir = setup_kaydet["fake_log_dir"]
    monkeypatch = setup_kaydet["monkeypatch"]

    mock_datetime_factory(datetime(2025, 9, 30, 9, 0, 0))
    monkeypatch.setattr(
        sys,
        "argv",
        ["kaydet", "First entry to delete", "#temp"],
    )
    cli.main()
    capsys.readouterr()

    mock_datetime_factory(datetime(2025, 9, 30, 10, 0, 0))
    monkeypatch.setattr(sys, "argv", ["kaydet", "Second entry stays"])
    cli.main()
    capsys.readouterr()

    fake_index_dir = setup_kaydet["fake_index_dir"]
    db_path = fake_index_dir / "index.db"
    with sqlite3.connect(db_path) as db:
        cursor = db.cursor()
        cursor.execute("SELECT id FROM entries WHERE timestamp = '09:00'")
        entry_id = cursor.fetchone()[0]

    prompted = []

    def fake_input(prompt=""):
        prompted.append(prompt)
        return "y"

    monkeypatch.setattr("builtins.input", fake_input)
    monkeypatch.setattr(
        sys,
        "argv",
        ["kaydet", "--delete", str(entry_id)],
    )

    cli.main()
    output = capsys.readouterr().out
    assert f"Entry Deleted (ID: {entry_id})" in output
    assert prompted
    assert "First entry to delete" in prompted[0]

    day_file = fake_log_dir / "2025-09-30.txt"
    content = day_file.read_text()
    assert "First entry to delete" not in content
    assert "Second entry stays" in content

    with sqlite3.connect(db_path) as db:
        cursor = db.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM entries WHERE id = ?",
            (entry_id,),
        )
        assert cursor.fetchone()[0] == 0


def test_conflicting_numeric_id_preserves_original_entry(
    setup_kaydet, mock_datetime_factory, capsys
):
    """A conflicting manual ID should not overwrite an existing entry."""

    fake_log_dir = setup_kaydet["fake_log_dir"]
    monkeypatch = setup_kaydet["monkeypatch"]

    mock_datetime_factory(datetime(2025, 9, 29, 8, 0, 0))
    monkeypatch.setattr(sys, "argv", ["kaydet", "Original entry"])
    cli.main()
    capsys.readouterr()

    conflicting_file = fake_log_dir / "2025-09-30.txt"
    conflicting_file.write_text(
        "10:00 [1]: Conflicting entry\n",
        encoding="utf-8",
    )

    mock_datetime_factory(datetime(2025, 9, 30, 9, 0, 0))
    monkeypatch.setattr(sys, "argv", ["kaydet", "--tags"])
    cli.main()
    capsys.readouterr()

    fake_index_dir = setup_kaydet["fake_index_dir"]
    db_path = fake_index_dir / "index.db"
    db = sqlite3.connect(db_path)
    cursor = db.cursor()

    cursor.execute("SELECT source_file FROM entries WHERE id = 1")
    assert cursor.fetchone()[0] == "2025-09-29.txt"

    cursor.execute(
        "SELECT id FROM entries WHERE source_file = ?",
        ("2025-09-30.txt",),
    )
    conflicting_entry_id = cursor.fetchone()[0]
    assert conflicting_entry_id != 1

    cursor.execute("SELECT COUNT(*) FROM entries")
    assert cursor.fetchone()[0] == 2

    db.close()

    updated_content = conflicting_file.read_text()
    match = re.search(r"10:00 \[(\d+)\]: Conflicting entry", updated_content)
    assert match is not None
    assert match.group(1) != "1"


def test_today_file_waits_until_midnight(
    setup_kaydet, mock_datetime_factory, capsys
):
    """Today's diary file should defer ID rewrites until the next day."""

    fake_log_dir = setup_kaydet["fake_log_dir"]
    monkeypatch = setup_kaydet["monkeypatch"]
    fake_log_dir.mkdir(exist_ok=True)

    todays_file = fake_log_dir / "2025-09-30.txt"
    todays_file.write_text("21:00: Manual entry\n", encoding="utf-8")

    first_run = datetime(2025, 9, 30, 21, 0, 0)
    mock_datetime_factory(first_run)
    monkeypatch.setattr(sys, "argv", ["kaydet", "--tags"])
    cli.main()
    capsys.readouterr()

    first_content = todays_file.read_text()
    assert re.search(r"21:00 \[\d+\]: Manual entry\n", first_content)

    fake_index_dir = setup_kaydet["fake_index_dir"]
    db_path = fake_index_dir / "index.db"
    db = sqlite3.connect(db_path)
    cursor = db.cursor()
    cursor.execute("SELECT COUNT(*) FROM entries")
    assert cursor.fetchone()[0] == 1
    db.close()

    mock_datetime_factory(first_run + timedelta(days=1))
    monkeypatch.setattr(sys, "argv", ["kaydet", "--tags"])
    cli.main()
    capsys.readouterr()

    updated_content = todays_file.read_text()
    print(f"\nDEBUG: updated_content repr: {repr(updated_content)}")
    assert re.search(r"21:00 \[\d+\]: Manual entry", updated_content)
