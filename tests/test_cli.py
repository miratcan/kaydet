from __future__ import annotations

import os
import re
import sqlite3
import sys
from configparser import ConfigParser
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from kaydet import __version__ as package_version
from kaydet import cli


@pytest.fixture
def setup_kaydet(monkeypatch, tmp_path: Path) -> dict:
    """Return a configured Kaydet test environment."""
    fake_home = tmp_path
    fake_config_dir = fake_home / ".config" / "kaydet"
    fake_config_dir.mkdir(parents=True)
    fake_config_path = fake_config_dir / "config.ini"
    fake_log_dir = fake_home / ".kaydet"

    config = ConfigParser(interpolation=None)
    config.add_section("SETTINGS")
    config["SETTINGS"]["LOG_DIR"] = str(fake_log_dir)
    config["SETTINGS"]["DAY_FILE_PATTERN"] = "%Y-%m-%d.txt"
    config["SETTINGS"]["DAY_TITLE_PATTERN"] = "%Y/%m/%d/ - %A"
    config["SETTINGS"]["EDITOR"] = "vim"

    def fake_get_config():
        return config["SETTINGS"], fake_config_path, fake_config_dir

    monkeypatch.setattr(cli, "get_config", fake_get_config)

    return {
        "monkeypatch": monkeypatch,
        "fake_log_dir": fake_log_dir,
        "fake_config_dir": fake_config_dir,
    }


@pytest.fixture
def mock_datetime_factory(monkeypatch):
    """Factory fixture to mock datetime.now() to a specific time."""

    def factory(now_fixed: datetime):
        class MockDateTime(datetime):
            @classmethod
            def now(cls, tz=None):
                return now_fixed

        monkeypatch.setattr(cli, "datetime", MockDateTime)

    return factory


# --- Tests for main application logic (using setup_kaydet fixture) ---


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
    assert re.search(r"10:30 \[\d+\]: my first test entry", content)


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
    assert re.search(
        r"11:00 \[\d+\]: This is a test for #work and #project-a",
        content,
    )

    # 2. Check the SQLite database
    db_path = fake_log_dir / "index.db"
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

    db_path = fake_log_dir / "index.db"
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
    assert re.search(r"12:00 \[\d+\]: This entry came from the editor.", content)


def test_stats_command(setup_kaydet, capsys, mock_datetime_factory):
    """Test the --stats command output."""
    fake_log_dir = setup_kaydet["fake_log_dir"]
    monkeypatch = setup_kaydet["monkeypatch"]
    fake_log_dir.mkdir(exist_ok=True)

    (fake_log_dir / "2025-09-01.txt").write_text(
        "\n".join(
            [
                "09:00: entry 1",
                "10:00: entry 2",
                "11:00: entry 3",
            ]
        )
    )
    (fake_log_dir / "2025-09-15.txt").write_text(
        "\n".join(
            [
                "12:00: entry 1",
                "13:00: entry 2",
                "14:00: entry 3",
                "15:00: entry 4",
                "16:00: entry 5",
            ]
        )
    )
    (fake_log_dir / "2025-08-20.txt").write_text(
        "08:00: entry from another month"
    )

    mock_datetime_factory(datetime(2025, 9, 25, 10, 0, 0))

    monkeypatch.setattr(sys, "argv", ["kaydet", "--stats"])

    cli.main()

    captured = capsys.readouterr()
    output = captured.out

    assert "September 2025" in output
    assert " 1[ 3]" in output
    assert "15[ 5]" in output
    assert "Total entries this month: 8" in output


def test_version_flag(setup_kaydet, capsys):
    """Ensure --version reports the current kaydet version."""
    monkeypatch = setup_kaydet["monkeypatch"]
    monkeypatch.setattr(sys, "argv", ["kaydet", "--version"])

    with pytest.raises(SystemExit) as exc:
        cli.main()

    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert f"kaydet {package_version}" in captured.out


def test_search_command(setup_kaydet, capsys):
    """Test the --search command output."""
    fake_log_dir = setup_kaydet["fake_log_dir"]
    monkeypatch = setup_kaydet["monkeypatch"]
    fake_log_dir.mkdir(exist_ok=True)

    (fake_log_dir / "2025-10-01.txt").write_text(
        "2025/10/01/ - Wednesday\n"
        "-----------------------\n"
        "10:00: An entry about a secret project.\n"
        "11:00: Another line that should not match.\n"
    )
    (fake_log_dir / "2025-10-02.txt").write_text(
        "2025/10/02/ - Thursday\n"
        "----------------------\n"
        "14:00: Planning the #secret-meeting.\n"
    )
    (fake_log_dir / "2025-10-03.txt").write_text(
        "2025/10/03/ - Friday\n"
        "--------------------\n"
        "16:00: This is a completely unrelated note.\n"
    )

    monkeypatch.setattr(sys, "argv", ["kaydet", "--search", "secret"])

    cli.main()

    captured = capsys.readouterr()
    output = captured.out

    assert "An entry about a secret project." in output
    assert "Planning the #secret-meeting." in output
    assert "unrelated note" not in output
    assert "Found 2 entries containing 'secret'." in output


def test_search_with_metadata_filters(
    setup_kaydet, capsys, mock_datetime_factory
):
    """Search queries should understand metadata, ranges, and wildcards."""

    fake_log_dir = setup_kaydet["fake_log_dir"]
    monkeypatch = setup_kaydet["monkeypatch"]
    fake_log_dir.mkdir(exist_ok=True)

    mock_datetime_factory(datetime(2025, 10, 5, 9, 0, 0))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "kaydet",
            "Implement feature",
            "status:wip",
            "time:2h",
            "branch:feature/api",
        ],
    )
    cli.main()

    mock_datetime_factory(datetime(2025, 10, 5, 11, 0, 0))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "kaydet",
            "Feature complete",
            "status:done",
            "time:3.5h",
            "branch:feature/api",
            "#release",
        ],
    )
    cli.main()

    mock_datetime_factory(datetime(2025, 10, 5, 13, 0, 0))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "kaydet",
            "Bugfix",
            "status:done",
            "time:45m",
            "branch:hotfix/security",
        ],
    )
    cli.main()

    monkeypatch.setattr(sys, "argv", ["kaydet", "--search", "status:done"])
    cli.main()
    output = capsys.readouterr().out
    assert "Feature complete" in output
    assert "status:done" in output
    assert "Bugfix" in output
    assert "Implement feature" not in output

    monkeypatch.setattr(sys, "argv", ["kaydet", "--search", "time:>2"])
    cli.main()
    output = capsys.readouterr().out
    assert "Feature complete" in output
    assert "Bugfix" not in output

    monkeypatch.setattr(
        sys, "argv", ["kaydet", "--search", "branch:feature/* status:done"]
    )
    cli.main()
    output = capsys.readouterr().out
    assert "Feature complete" in output
    assert "branch:feature/api" in output
    assert "Bugfix" not in output


def test_tags_command(setup_kaydet, capsys, mock_datetime_factory):
    """Verify the --tags command reads from the SQLite index."""
    monkeypatch = setup_kaydet["monkeypatch"]

    # Add a few entries with tags
    mock_datetime_factory(datetime(2025, 10, 1, 9, 0, 0))
    monkeypatch.setattr(
        sys, "argv", ["kaydet", "Entry with #work and #project-a"]
    )
    cli.main()

    mock_datetime_factory(datetime(2025, 10, 1, 10, 0, 0))
    monkeypatch.setattr(sys, "argv", ["kaydet", "Entry with #personal"])
    cli.main()

    # Run the --tags command
    monkeypatch.setattr(sys, "argv", ["kaydet", "--tags"])
    cli.main()

    captured = capsys.readouterr()
    output = captured.out

    expected_output = "personal\nproject-a\nwork\n"
    assert output.endswith(expected_output)


def test_doctor_command(setup_kaydet, capsys):
    """Ensure --doctor rebuilds the index from legacy files."""
    fake_log_dir = setup_kaydet["fake_log_dir"]
    monkeypatch = setup_kaydet["monkeypatch"]
    fake_log_dir.mkdir(exist_ok=True)

    # Create a legacy file without UUIDs
    (fake_log_dir / "2025-10-10.txt").write_text(
        "10:00: A task for #work.\n"
        "11:00: A personal note for #home.\n"
        "12:00: Another #work thing to do.\n"
    )

    monkeypatch.setattr(sys, "argv", ["kaydet", "--doctor"])

    cli.main()

    captured = capsys.readouterr()
    output = captured.out

    assert "Normalized IDs in" in output
    assert "Rebuilt search index for 3 entries." in output

    legacy_content = (fake_log_dir / "2025-10-10.txt").read_text()
    assert re.search(r"10:00 \[\d+\]: A task for #work\.", legacy_content)
    assert re.search(r"11:00 \[\d+\]: A personal note for #home\.", legacy_content)

    db_path = fake_log_dir / "index.db"
    assert db_path.exists()
    db = sqlite3.connect(db_path)
    cursor = db.cursor()

    # Check if entries were added
    cursor.execute("SELECT COUNT(*) FROM entries")
    assert cursor.fetchone()[0] == 3

    # Check if tags were added correctly
    cursor.execute(
        (
            "SELECT tag_name, COUNT(*) FROM tags "
            "GROUP BY tag_name ORDER BY tag_name"
        )
    )
    tag_counts = dict(cursor.fetchall())
    assert tag_counts == {"home": 1, "work": 2}

    db.close()


def test_manual_edit_sync_before_search(
    setup_kaydet, mock_datetime_factory, capsys
):
    """Manual edits should be detected and synchronized before searching."""

    fake_log_dir = setup_kaydet["fake_log_dir"]
    monkeypatch = setup_kaydet["monkeypatch"]

    mock_datetime_factory(datetime(2025, 9, 30, 9, 0, 0))
    monkeypatch.setattr(sys, "argv", ["kaydet", "Initial note #work"])
    cli.main()
    capsys.readouterr()

    day_file = fake_log_dir / "2025-09-30.txt"
    content = day_file.read_text()
    day_file.write_text(
        content.replace("Initial note #work", "Updated entry #updated"),
        encoding="utf-8",
    )

    monkeypatch.setattr(sys, "argv", ["kaydet", "--search", "#updated"])
    cli.main()
    output = capsys.readouterr().out

    assert "Updated entry #updated" in output


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
    conflicting_file.write_text("10:00 [1]: Conflicting entry\n", encoding="utf-8")

    mock_datetime_factory(datetime(2025, 9, 30, 9, 0, 0))
    monkeypatch.setattr(sys, "argv", ["kaydet", "--tags"])
    cli.main()
    capsys.readouterr()

    db_path = fake_log_dir / "index.db"
    db = sqlite3.connect(db_path)
    cursor = db.cursor()

    cursor.execute("SELECT source_file FROM entries WHERE id = 1")
    assert cursor.fetchone()[0] == "2025-09-29.txt"

    cursor.execute("SELECT id FROM entries WHERE source_file = ?", ("2025-09-30.txt",))
    conflicting_entry_id = cursor.fetchone()[0]
    assert conflicting_entry_id != 1

    cursor.execute("SELECT COUNT(*) FROM entries")
    assert cursor.fetchone()[0] == 2

    db.close()

    updated_content = conflicting_file.read_text()
    match = re.search(r"10:00 \[(\d+)\]: Conflicting entry", updated_content)
    assert match is not None
    assert match.group(1) != "1"


def test_today_file_waits_until_midnight(setup_kaydet, mock_datetime_factory, capsys):
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
    first_output = capsys.readouterr().out

    assert "Normalized IDs" not in first_output
    assert "[" not in todays_file.read_text()

    db_path = fake_log_dir / "index.db"
    db = sqlite3.connect(db_path)
    cursor = db.cursor()
    cursor.execute("SELECT COUNT(*) FROM entries")
    assert cursor.fetchone()[0] == 1
    db.close()

    mock_datetime_factory(first_run + timedelta(days=1))
    monkeypatch.setattr(sys, "argv", ["kaydet", "--tags"])
    cli.main()
    second_output = capsys.readouterr().out

    assert "Normalized IDs in" in second_output
    updated_content = todays_file.read_text()
    assert re.search(r"21:00 \[\d+\]: Manual entry", updated_content)


def test_reminder_no_previous_entries(setup_kaydet, capsys):
    """Test the reminder command when no entries exist yet."""
    monkeypatch = setup_kaydet["monkeypatch"]
    monkeypatch.setattr(sys, "argv", ["kaydet", "--reminder"])

    cli.main()

    captured = capsys.readouterr()
    assert "You haven't written any Kaydet entries yet." in captured.out


def test_reminder_recent_entry(setup_kaydet, capsys):
    """Test the reminder command when a recent entry exists."""
    monkeypatch = setup_kaydet["monkeypatch"]
    fake_config_dir = setup_kaydet["fake_config_dir"]

    now = datetime.now()
    recent_timestamp = (now - timedelta(hours=1)).isoformat()
    (fake_config_dir / "last_entry_timestamp").write_text(recent_timestamp)

    monkeypatch.setattr(sys, "argv", ["kaydet", "--reminder"])

    cli.main()

    captured = capsys.readouterr()
    assert captured.out == ""


def test_reminder_old_entry(setup_kaydet, capsys):
    """Test the reminder command when the last entry is old."""
    monkeypatch = setup_kaydet["monkeypatch"]
    fake_config_dir = setup_kaydet["fake_config_dir"]

    now = datetime.now()
    old_timestamp = (now - timedelta(hours=3)).isoformat()
    (fake_config_dir / "last_entry_timestamp").write_text(old_timestamp)

    monkeypatch.setattr(sys, "argv", ["kaydet", "--reminder"])

    cli.main()

    captured = capsys.readouterr()
    assert (
        "It's been over two hours since your last Kaydet entry."
        in captured.out
    )


def test_folder_command_opens_main_log_dir(setup_kaydet, mocker):
    """Test that `kaydet --folder` opens the main log directory."""
    fake_log_dir = setup_kaydet["fake_log_dir"]
    monkeypatch = setup_kaydet["monkeypatch"]
    mock_startfile = mocker.patch("kaydet.cli.startfile")

    monkeypatch.setattr(sys, "argv", ["kaydet", "--folder"])

    cli.main()

    mock_startfile.assert_called_once_with(str(fake_log_dir))


def test_read_diary_with_bad_encoding(
    setup_kaydet, capsys, mock_datetime_factory
):
    """Test that a file with invalid UTF-8 is read gracefully."""
    fake_log_dir = setup_kaydet["fake_log_dir"]
    monkeypatch = setup_kaydet["monkeypatch"]
    fake_log_dir.mkdir(exist_ok=True)

    file_content_bytes = (
        b"10:00: Valid entry.\n11:00: Invalid byte here \xff.\n"
    )
    (fake_log_dir / "2025-09-25.txt").write_bytes(file_content_bytes)

    mock_datetime_factory(datetime(2025, 9, 25, 12, 0, 0))
    monkeypatch.setattr(sys, "argv", ["kaydet", "--stats"])

    cli.main()

    captured = capsys.readouterr()
    output = captured.out
    assert "Total entries this month: 2" in output


def test_reminder_fallback_to_mtime(
    setup_kaydet, capsys, mock_datetime_factory
):
    """Test the reminder fallback logic to check file modification times."""
    fake_log_dir = setup_kaydet["fake_log_dir"]
    monkeypatch = setup_kaydet["monkeypatch"]
    fake_log_dir.mkdir(exist_ok=True)

    now = datetime.now()
    three_hours_ago = now - timedelta(hours=3)
    five_hours_ago = now - timedelta(hours=5)

    file1 = fake_log_dir / "file1.txt"
    file2 = fake_log_dir / "file2.txt"
    file1.touch()
    file2.touch()

    os.utime(file1, (three_hours_ago.timestamp(), three_hours_ago.timestamp()))
    os.utime(file2, (five_hours_ago.timestamp(), five_hours_ago.timestamp()))

    mock_datetime_factory(now)
    monkeypatch.setattr(sys, "argv", ["kaydet", "--reminder"])

    cli.main()

    captured = capsys.readouterr()
    assert (
        "It's been over two hours since your last Kaydet entry."
        in captured.out
    )


def test_stats_no_log_dir(setup_kaydet, capsys, mock_datetime_factory):
    """Test --stats command when the log directory does not exist."""
    monkeypatch = setup_kaydet["monkeypatch"]
    mock_datetime_factory(datetime(2025, 9, 25, 10, 0, 0))

    monkeypatch.setattr(sys, "argv", ["kaydet", "--stats"])

    cli.main()

    captured = capsys.readouterr()
    assert "No diary entries found yet." in captured.out


def test_stats_over_99_entries(setup_kaydet, capsys, mock_datetime_factory):
    """Test --stats command for a day with 100+ entries."""
    fake_log_dir = setup_kaydet["fake_log_dir"]
    monkeypatch = setup_kaydet["monkeypatch"]
    fake_log_dir.mkdir(exist_ok=True)

    entry_lines = [f"{i:02d}:{i:02d}: entry" for i in range(100)]
    (fake_log_dir / "2025-09-05.txt").write_text("\n".join(entry_lines))

    mock_datetime_factory(datetime(2025, 9, 25, 10, 0, 0))
    monkeypatch.setattr(sys, "argv", ["kaydet", "--stats"])

    cli.main()

    captured = capsys.readouterr()
    output = captured.out

    assert " 5[**]" in output
    assert "Total entries this month: 100" in output


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


def test_legacy_tag_parsing(setup_kaydet, capsys):
    """Test that legacy [tag] format is parsed correctly."""
    fake_log_dir = setup_kaydet["fake_log_dir"]
    monkeypatch = setup_kaydet["monkeypatch"]
    fake_log_dir.mkdir(exist_ok=True)

    (fake_log_dir / "2025-10-20.txt").write_text(
        "10:00: [work,project] A legacy entry.\n"
    )

    monkeypatch.setattr(sys, "argv", ["kaydet", "--doctor"])

    cli.main()

    captured = capsys.readouterr()
    output = captured.out

    assert "Rebuilt search index for 1 entry." in output
    assert "Tags: #project: 1, #work: 1" in output


def test_search_no_results(setup_kaydet, capsys):
    """Test the --search command when no entries match."""
    fake_log_dir = setup_kaydet["fake_log_dir"]
    monkeypatch = setup_kaydet["monkeypatch"]
    fake_log_dir.mkdir(exist_ok=True)

    (fake_log_dir / "2025-10-01.txt").write_text(
        "10:00: Some unrelated content.\n"
    )

    monkeypatch.setattr(sys, "argv", ["kaydet", "--search", "nonexistent"])

    cli.main()

    captured = capsys.readouterr()
    assert "No entries matched 'nonexistent'." in captured.out


def test_tags_no_tags(setup_kaydet, capsys):
    """Test the --tags command when no tag directories exist."""
    fake_log_dir = setup_kaydet["fake_log_dir"]
    monkeypatch = setup_kaydet["monkeypatch"]
    fake_log_dir.mkdir(exist_ok=True)

    monkeypatch.setattr(sys, "argv", ["kaydet", "--tags"])

    cli.main()

    captured = capsys.readouterr()
    assert "No tags have been recorded yet." in captured.out


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
    assert "Nothing to save." in captured.out

    log_file = fake_log_dir / "2025-09-30.txt"
    assert log_file.exists()
    content = log_file.read_text()
    assert "12:00:" not in content


# --- Tests for get_config (without setup_kaydet fixture) ---


def test_get_config_creation(monkeypatch, tmp_path):
    """Test that a new config file is created from scratch."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setitem(
        cli.DEFAULT_SETTINGS, "LOG_DIR", str(tmp_path / ".kaydet")
    )
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)

    section, config_path, _ = cli.get_config()

    assert config_path.exists()
    assert config_path.name == "config.ini"
    assert section["editor"] == "vim"
    assert str(tmp_path / ".kaydet") in section["log_dir"]


def test_get_config_existing_partial(monkeypatch, tmp_path):
    """Test that missing values are populated in an existing config."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setitem(
        cli.DEFAULT_SETTINGS, "LOG_DIR", str(tmp_path / ".kaydet")
    )
    config_dir = tmp_path / ".config" / "kaydet"
    config_dir.mkdir(parents=True)
    config_path = config_dir / "config.ini"

    config_content = "[SETTINGS]\nlog_dir = /my/custom/path\n"
    config_path.write_text(config_content)

    section, _, _ = cli.get_config()

    assert section["log_dir"] == "/my/custom/path"
    assert section["editor"] == "vim"


def test_get_config_xdg_home(monkeypatch, tmp_path):
    """Test that XDG_CONFIG_HOME environment variable is respected."""
    monkeypatch.setitem(
        cli.DEFAULT_SETTINGS, "LOG_DIR", str(tmp_path / ".kaydet")
    )
    xdg_path = tmp_path / "custom_xdg"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg_path))

    _, config_path, _ = cli.get_config()

    assert str(xdg_path / "kaydet") in str(config_path.parent)


# --- Final push for 100% coverage ---


def test_search_multiline_result(setup_kaydet, capsys):
    """Test that multiline search results are printed correctly."""
    fake_log_dir = setup_kaydet["fake_log_dir"]
    monkeypatch = setup_kaydet["monkeypatch"]
    fake_log_dir.mkdir(exist_ok=True)

    (fake_log_dir / "2025-11-01.txt").write_text(
        "\n".join(
            [
                "10:00: The first line of a multiline note.",
                "    This is the second line.",
                "    And a third.",
            ]
        )
    )

    monkeypatch.setattr(sys, "argv", ["kaydet", "--search", "first line"])
    cli.main()

    captured = capsys.readouterr()
    output = captured.out

    assert "The first line" in output
    assert "    This is the second line." in output
    assert "    And a third." in output


def test_doctor_with_untagged_entries(setup_kaydet, capsys):
    """Test that the doctor command handles entries with no tags."""
    fake_log_dir = setup_kaydet["fake_log_dir"]
    monkeypatch = setup_kaydet["monkeypatch"]
    fake_log_dir.mkdir(exist_ok=True)

    (fake_log_dir / "2025-11-02.txt").write_text(
        "\n".join(
            [
                "10:00: An entry with #work.",
                "11:00: An entry with no tags.",
                "",
            ]
        )
    )

    monkeypatch.setattr(sys, "argv", ["kaydet", "--doctor"])
    cli.main()

    captured = capsys.readouterr()
    # Ensure the rebuild completes and keeps only the existing tag
    assert "Rebuilt search index for 2 entries." in captured.out
    assert "Tags: #work: 1" in captured.out


def test_stats_ignores_directories(
    setup_kaydet, capsys, mock_datetime_factory
):
    """Test that the stats command ignores subdirectories in the log folder."""
    fake_log_dir = setup_kaydet["fake_log_dir"]
    monkeypatch = setup_kaydet["monkeypatch"]
    fake_log_dir.mkdir(exist_ok=True)

    (fake_log_dir / "2025-09-10.txt").write_text("10:00: entry 1\n")
    (fake_log_dir / "a_subdirectory").mkdir()

    mock_datetime_factory(datetime(2025, 9, 25, 10, 0, 0))
    monkeypatch.setattr(sys, "argv", ["kaydet", "--stats"])

    cli.main()

    captured = capsys.readouterr()
    # Check that only the file is counted and the directory is ignored
    assert "Total entries this month: 1" in captured.out


def test_extract_tags_empty_string():
    """Test the pure function extract_tags_from_text with an empty string."""
    assert cli.extract_tags_from_text("") == ()


def test_search_with_colon_containing_text(
    setup_kaydet, capsys, mock_datetime_factory
):
    """Test that URLs and times with colons are searchable as plain text."""
    fake_log_dir = setup_kaydet["fake_log_dir"]
    monkeypatch = setup_kaydet["monkeypatch"]
    fake_log_dir.mkdir(exist_ok=True)

    # Create entries with URLs and times
    mock_datetime_factory(datetime(2025, 10, 24, 9, 0, 0))
    monkeypatch.setattr(
        sys,
        "argv",
        ["kaydet", "Check out http://example.com for details"],
    )
    cli.main()

    mock_datetime_factory(datetime(2025, 10, 24, 12, 30, 0))
    monkeypatch.setattr(
        sys,
        "argv",
        ["kaydet", "Meeting at 12:30 with the team"],
    )
    cli.main()

    mock_datetime_factory(datetime(2025, 10, 24, 14, 0, 0))
    monkeypatch.setattr(
        sys,
        "argv",
        ["kaydet", "Deployed fix", "commit:38edf60"],
    )
    cli.main()

    # Search for URL - should match as plain text
    monkeypatch.setattr(
        sys, "argv", ["kaydet", "--search", "http://example.com"]
    )
    cli.main()
    output = capsys.readouterr().out
    assert "http://example.com" in output
    assert "Meeting" not in output

    # Search for time - should match as plain text
    monkeypatch.setattr(sys, "argv", ["kaydet", "--search", "12:30"])
    cli.main()
    output = capsys.readouterr().out
    assert "12:30" in output
    assert "http://example.com" not in output

    # Search for valid metadata should still work
    monkeypatch.setattr(sys, "argv", ["kaydet", "--search", "commit:38edf60"])
    cli.main()
    output = capsys.readouterr().out
    assert "Deployed fix" in output
    assert "commit:38edf60" in output
    assert "Meeting" not in output
    assert "http://example.com" not in output
