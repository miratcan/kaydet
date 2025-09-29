from __future__ import annotations

import os
import sys
from configparser import ConfigParser
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from kaydet import cli


@pytest.fixture
def setup_kaydet(monkeypatch, tmp_path: Path) -> dict:
    """A pytest fixture to set up a controlled environment for testing kaydet."""
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
    assert "10:30: my first test entry" in content


def test_add_entry_with_tags(setup_kaydet, mock_datetime_factory):
    """Test that an entry with hashtags is mirrored to tag folders."""
    fake_log_dir = setup_kaydet["fake_log_dir"]
    monkeypatch = setup_kaydet["monkeypatch"]
    mock_datetime_factory(datetime(2025, 9, 30, 11, 0, 0))

    entry_text = "This is a test for #work and #project-a"
    monkeypatch.setattr(sys, "argv", ["kaydet", entry_text])

    cli.main()

    main_log_file = fake_log_dir / "2025-09-30.txt"
    assert main_log_file.exists()
    assert (
        "11:00: This is a test for #work and #project-a"
        in main_log_file.read_text()
    )

    for tag in ["work", "project-a"]:
        tag_dir = fake_log_dir / tag
        assert tag_dir.is_dir()
        tag_log_file = tag_dir / "2025-09-30.txt"
        assert tag_log_file.exists()
        content = tag_log_file.read_text()
        assert "2025/09/30/ - Tuesday" in content
        assert "11:00: This is a test for #work and #project-a" in content


def test_editor_usage(setup_kaydet, mock_datetime_factory):
    """Test that the editor is used when no entry is provided."""
    fake_log_dir = setup_kaydet["fake_log_dir"]
    monkeypatch = setup_kaydet["monkeypatch"]
    mock_datetime_factory(datetime(2025, 9, 30, 12, 0, 0))

    monkeypatch.setattr(sys, "argv", ["kaydet"])

    editor_text = "This entry came from the editor."
    monkeypatch.setattr(cli, "open_editor", lambda *args: editor_text)

    cli.main()

    log_file = fake_log_dir / "2025-09-30.txt"
    assert log_file.exists()
    content = log_file.read_text()
    assert "12:00: This entry came from the editor." in content


def test_stats_command(setup_kaydet, capsys, mock_datetime_factory):
    """Test the --stats command output."""
    fake_log_dir = setup_kaydet["fake_log_dir"]
    monkeypatch = setup_kaydet["monkeypatch"]
    fake_log_dir.mkdir(exist_ok=True)

    (fake_log_dir / "2025-09-01.txt").write_text(
        "09:00: entry 1\n10:00: entry 2\n11:00: entry 3"
    )
    (fake_log_dir / "2025-09-15.txt").write_text(
        "12:00: entry 1\n13:00: entry 2\n14:00: entry 3\n15:00: entry 4\n16:00: entry 5"
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


def test_tags_command(setup_kaydet, capsys):
    """Test the --tags command output."""
    fake_log_dir = setup_kaydet["fake_log_dir"]
    monkeypatch = setup_kaydet["monkeypatch"]
    fake_log_dir.mkdir(exist_ok=True)

    (fake_log_dir / "work").mkdir()
    (fake_log_dir / "personal").mkdir()
    (fake_log_dir / "project-a").mkdir()
    (fake_log_dir / "a-file.txt").touch()

    monkeypatch.setattr(sys, "argv", ["kaydet", "--tags"])

    cli.main()

    captured = capsys.readouterr()
    output = captured.out

    expected_output = "personal\nproject-a\nwork\n"
    assert output == expected_output


def test_doctor_command(setup_kaydet, capsys):
    """Test the --doctor command rebuilds tag archives correctly."""
    fake_log_dir = setup_kaydet["fake_log_dir"]
    monkeypatch = setup_kaydet["monkeypatch"]
    fake_log_dir.mkdir(exist_ok=True)

    (fake_log_dir / "2025-10-10.txt").write_text(
        "10:00: A task for #work.\n"
        "11:00: A personal note for #home.\n"
        "12:00: Another #work thing to do.\n"
    )

    orphaned_tag_dir = fake_log_dir / "orphaned"
    orphaned_tag_dir.mkdir()
    (orphaned_tag_dir / "stale.txt").touch()

    monkeypatch.setattr(sys, "argv", ["kaydet", "--doctor"])

    cli.main()

    captured = capsys.readouterr()
    output = captured.out

    assert "Rebuilt tag archives for 2 tags." in output
    assert "#home: 1" in output
    assert "#work: 2" in output
    assert not orphaned_tag_dir.exists()

    work_dir = fake_log_dir / "work"
    home_dir = fake_log_dir / "home"
    assert work_dir.is_dir()
    assert home_dir.is_dir()

    work_log = work_dir / "2025-10-10.txt"
    home_log = home_dir / "2025-10-10.txt"
    assert work_log.exists()
    assert home_log.exists()

    work_content = work_log.read_text()
    home_content = home_log.read_text()

    assert "10:00: A task for #work." in work_content
    assert "12:00: Another #work thing to do." in work_content
    assert "11:00: A personal note for #home." in home_content
    assert "A personal note for #home." not in work_content


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


def test_folder_command_opens_tag_dir(setup_kaydet, mocker):
    """Test that `kaydet --folder TAG` opens the correct tag directory."""
    fake_log_dir = setup_kaydet["fake_log_dir"]
    monkeypatch = setup_kaydet["monkeypatch"]
    mock_startfile = mocker.patch("kaydet.cli.startfile")

    tag_dir = fake_log_dir / "work"
    fake_log_dir.mkdir(exist_ok=True)
    tag_dir.mkdir()

    monkeypatch.setattr(sys, "argv", ["kaydet", "--folder", "work"])

    cli.main()

    mock_startfile.assert_called_once_with(str(tag_dir))


def test_folder_command_non_existent_tag(setup_kaydet, capsys, mocker):
    """Test that `kaydet --folder TAG` shows an error for a non-existent tag."""
    monkeypatch = setup_kaydet["monkeypatch"]
    mock_startfile = mocker.patch("kaydet.cli.startfile")

    monkeypatch.setattr(sys, "argv", ["kaydet", "--folder", "non-existent"])

    cli.main()

    mock_startfile.assert_not_called()
    captured = capsys.readouterr()
    assert "No tag folder found for '#non-existent'." in captured.out


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

    assert "Rebuilt tag archives for 2 tags." in output
    assert "#project: 1" in output
    assert "#work: 1" in output


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

    monkeypatch.setattr(cli, "open_editor", lambda *args: " \n ")

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
        "10:00: The first line of a multiline note.\n    This is the second line.\n    And a third."
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
        "10:00: An entry with #work.\n11:00: An entry with no tags.\n"
    )

    monkeypatch.setattr(sys, "argv", ["kaydet", "--doctor"])
    cli.main()

    captured = capsys.readouterr()
    # Assert that it completes successfully and only rebuilds the tag that exists
    assert "Rebuilt tag archives for 1 tags." in captured.out
    assert "#work: 1" in captured.out


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
