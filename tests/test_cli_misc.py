from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from kaydet import __version__ as package_version
from kaydet import cli, utils


def test_version_flag(setup_kaydet, capsys):
    """Ensure --version reports the current kaydet version."""
    monkeypatch = setup_kaydet["monkeypatch"]
    monkeypatch.setattr(sys, "argv", ["kaydet", "--version"])

    with pytest.raises(SystemExit) as exc:
        cli.main()

    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert f"kaydet {package_version}" in captured.out


def test_reminder_no_previous_entries(setup_kaydet, capsys):
    """Test the reminder command when no entries exist yet."""
    monkeypatch = setup_kaydet["monkeypatch"]
    monkeypatch.setattr(sys, "argv", ["kaydet", "--reminder"])

    cli.main()

    captured = capsys.readouterr()
    assert "No entries yet" in captured.out


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
    assert "Over two hours since" in captured.out


def test_folder_command_opens_main_log_dir(setup_kaydet, mocker):
    """Test that `kaydet --folder` opens the main log directory."""
    fake_log_dir = setup_kaydet["fake_log_dir"]
    monkeypatch = setup_kaydet["monkeypatch"]
    mock_startfile = mocker.patch("kaydet.cli.startfile")

    monkeypatch.setattr(sys, "argv", ["kaydet", "--folder"])

    cli.main()

    mock_startfile.assert_called_once_with(str(fake_log_dir))


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
    assert "Over two hours since" in captured.out


def test_load_config_creation(monkeypatch, tmp_path):
    """Test that a new config file is created from scratch."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setitem(
        cli.DEFAULT_SETTINGS, "LOG_DIR", str(tmp_path / ".kaydet")
    )
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)

    # Mock prompt_storage_location to return default storage path

    default_storage = tmp_path / "Documents" / "Kaydet"
    monkeypatch.setattr(
        utils, "prompt_storage_location", lambda: default_storage
    )

    section, config_path, _, storage_dir, index_dir = cli.load_config()

    assert config_path.exists()
    assert config_path.name == "config.ini"
    assert section["editor"] == "vim"
    assert section["storage_dir"] == str(default_storage)
    assert storage_dir == default_storage
    assert storage_dir.exists()
    assert index_dir.exists()


def test_load_config_existing_partial(monkeypatch, tmp_path):
    """Test that missing values are populated in an existing config."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setitem(
        cli.DEFAULT_SETTINGS, "LOG_DIR", str(tmp_path / ".kaydet")
    )
    config_dir = tmp_path / ".config" / "kaydet"
    config_dir.mkdir(parents=True)
    config_path = config_dir / "config.ini"

    custom_storage = tmp_path / "custom" / "storage"
    log_dir = tmp_path / ".kaydet"
    config_content = (
        f"[SETTINGS]\nstorage_dir = {custom_storage}\nlog_dir = {log_dir}\n"
    )
    config_path.write_text(config_content)

    section, _, _, storage_dir, index_dir = cli.load_config()

    assert section["storage_dir"] == str(custom_storage)
    assert section["editor"] == "vim"
    assert storage_dir == custom_storage
    assert storage_dir.exists()
    assert index_dir.exists()


def test_load_config_xdg_home(monkeypatch, tmp_path):
    """Test that XDG_CONFIG_HOME environment variable is respected."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setitem(
        cli.DEFAULT_SETTINGS, "LOG_DIR", str(tmp_path / ".kaydet")
    )
    xdg_path = tmp_path / "custom_xdg"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg_path))

    # Mock prompt_storage_location to return default storage path

    default_storage = tmp_path / "Documents" / "Kaydet"
    monkeypatch.setattr(
        utils, "prompt_storage_location", lambda: default_storage
    )

    _, config_path, _, storage_dir, index_dir = cli.load_config()

    assert str(xdg_path / "kaydet") in str(config_path.parent)
    assert storage_dir == default_storage
    assert storage_dir.exists()
    assert index_dir.exists()


# --- Final push for 100% coverage ---


def test_extract_tags_empty_string():
    """Test the pure function extract_tags_from_text with an empty string."""
    assert cli.extract_tags_from_text("") == ()
