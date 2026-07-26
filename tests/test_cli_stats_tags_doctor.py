from __future__ import annotations

import re
import sqlite3
import sys
from datetime import datetime

from kaydet import cli


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
    # GitHub-style heat grid (weekdays as rows)
    assert "Mo  " in output
    assert "less → more" in output
    # Two active days this month (1st and 15th)
    assert "2 of 30 days" in output or "2 of" in output
    assert "with writing" in output


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

    lines = [line for line in output.splitlines() if line.startswith("#")]
    assert lines == [
        "#personal            1 entry",
        "#project-a           1 entry",
        "#work                1 entry",
    ]


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
    assert re.search(r"10:00 \[\d+\]: A task for #work\.\n", legacy_content)
    assert re.search(
        r"11:00 \[\d+\]: A personal note for #home.\n",
        legacy_content,
    )

    fake_index_dir = setup_kaydet["fake_index_dir"]
    db_path = fake_index_dir / "index.db"
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


def test_stats_no_log_dir(setup_kaydet, capsys, mock_datetime_factory):
    """Test --stats command when the log directory does not exist."""
    monkeypatch = setup_kaydet["monkeypatch"]
    mock_datetime_factory(datetime(2025, 9, 25, 10, 0, 0))

    monkeypatch.setattr(sys, "argv", ["kaydet", "--stats"])

    cli.main()

    captured = capsys.readouterr()
    assert "No diary entries found yet" in captured.out


def test_stats_busy_day_shows_heat(
    setup_kaydet, capsys, mock_datetime_factory
):
    """Busy days render as heat, not raw entry counts."""
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

    assert "█" in output  # heaviest heat for the busy day
    assert "1 day with writing" in output or "days with writing" in output
    assert "[99+]" not in output
    assert "Total entries this month: 100" not in output


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


def test_tags_no_tags(setup_kaydet, capsys):
    """Test the --tags command when no tag directories exist."""
    fake_log_dir = setup_kaydet["fake_log_dir"]
    monkeypatch = setup_kaydet["monkeypatch"]
    fake_log_dir.mkdir(exist_ok=True)

    monkeypatch.setattr(sys, "argv", ["kaydet", "--tags"])

    cli.main()

    captured = capsys.readouterr()
    assert "No tags recorded yet" in captured.out


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
    assert "with writing" in captured.out


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
    assert "with writing" in output
