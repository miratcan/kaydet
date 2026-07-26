from __future__ import annotations

import sys
from datetime import datetime

import pytest

from kaydet import cli


def test_search_command(setup_kaydet, capsys):
    """Test the --search command output."""
    fake_log_dir = setup_kaydet["fake_log_dir"]
    monkeypatch = setup_kaydet["monkeypatch"]
    fake_log_dir.mkdir(exist_ok=True)

    (fake_log_dir / "2025-10-01.txt").write_text(
        "2025/10/01/ - Wednesday\n"
        "-----------------------\n"
        "10:00 [1]: An entry about a secret project.\n"
        "11:00 [2]: Another line that should not match.\n"
    )
    (fake_log_dir / "2025-10-02.txt").write_text(
        "2025/10/02/ - Thursday\n"
        "----------------------\n"
        "14:00 [3]: Planning the #secret-meeting.\n"
    )
    (fake_log_dir / "2025-10-03.txt").write_text(
        "2025/10/03/ - Friday\n"
        "--------------------\n"
        "16:00 [4]: This is a completely unrelated note.\n"
    )

    monkeypatch.setattr(sys, "argv", ["kaydet", "--filter", "secret"])

    cli.main()

    captured = capsys.readouterr()
    output = captured.out

    assert "An entry about a secret project." in output
    # Tag is displayed on a separate line now with the new formatter
    assert "Planning the" in output
    assert "secret-meeting" in output
    assert "unrelated note" not in output
    assert "2 entries containing secret" in output


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
            "time:1.5",
            "branch:hotfix/security",
        ],
    )
    cli.main()

    monkeypatch.setattr(sys, "argv", ["kaydet", "--filter", "status:done"])
    cli.main()
    output = capsys.readouterr().out
    assert "Feature complete" in output
    assert "status:done" in output
    assert "Bugfix" in output
    assert "Implement feature" not in output

    monkeypatch.setattr(sys, "argv", ["kaydet", "--filter", "time:<2"])
    cli.main()
    output = capsys.readouterr().out
    assert "Bugfix" in output
    assert "Feature complete" not in output
    assert "Implement feature" not in output

    monkeypatch.setattr(
        sys, "argv", ["kaydet", "--filter", "branch:feature/* status:done"]
    )
    cli.main()
    output = capsys.readouterr().out
    assert "Feature complete" in output
    assert "branch:feature/api" in output
    assert "Bugfix" not in output


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
    # Tags are now written naturally without pipe separator
    day_file.write_text(
        content.replace("Initial note #work", "Updated entry #updated"),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        sys, "argv", ["kaydet", "--filter", "#updated since:0"]
    )
    cli.main()
    output = capsys.readouterr().out

    assert "Updated entry" in output


def test_search_no_results(setup_kaydet, capsys):
    """Test the --search command when no entries match."""
    fake_log_dir = setup_kaydet["fake_log_dir"]
    monkeypatch = setup_kaydet["monkeypatch"]
    fake_log_dir.mkdir(exist_ok=True)

    (fake_log_dir / "2025-10-01.txt").write_text(
        "10:00: Some unrelated content.\n"
    )

    monkeypatch.setattr(sys, "argv", ["kaydet", "--filter", "nonexistent"])

    cli.main()

    captured = capsys.readouterr()
    assert "No entries matched 'nonexistent'" in captured.out
    assert "since:0" in captured.out or "widen search" in captured.out


def test_list_empty_shows_default_month_window(
    setup_kaydet, capsys, mock_datetime_factory
):
    """Bare --list with no entries should mention the month window."""
    fake_log_dir = setup_kaydet["fake_log_dir"]
    monkeypatch = setup_kaydet["monkeypatch"]
    fake_log_dir.mkdir(exist_ok=True)

    mock_datetime_factory(datetime(2025, 10, 27, 12, 0, 0))
    monkeypatch.setattr(sys, "argv", ["kaydet", "--list"])

    cli.main()

    captured = capsys.readouterr()
    assert "No entries found" in captured.out
    assert "this month by default" in captured.out
    assert "since:0" in captured.out


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

    monkeypatch.setattr(sys, "argv", ["kaydet", "--filter", "first line"])
    cli.main()

    captured = capsys.readouterr()
    output = captured.out

    assert "The first line" in output
    # Body lines are left-aligned (no indent under HH:MM [id] chrome)
    assert "This is the second line." in output
    assert "And a third." in output


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
        sys, "argv", ["kaydet", "--filter", "http://example.com"]
    )
    cli.main()
    output = capsys.readouterr().out
    assert "http://example.com" in output
    assert "Meeting" not in output

    # Search for time - should match as plain text
    monkeypatch.setattr(sys, "argv", ["kaydet", "--filter", "12:30"])
    cli.main()
    output = capsys.readouterr().out
    assert "12:30" in output
    assert "http://example.com" not in output

    # Search for valid metadata should still work
    monkeypatch.setattr(sys, "argv", ["kaydet", "--filter", "commit:38edf60"])
    cli.main()
    output = capsys.readouterr().out
    assert "Deployed fix" in output
    assert "commit:38edf60" in output
    assert "Meeting" not in output
    assert "http://example.com" not in output


def test_week_shorthand_filters_to_monday(
    setup_kaydet, capsys, mock_datetime_factory
):
    """--week lists entries since Monday of the current ISO week."""
    fake_log_dir = setup_kaydet["fake_log_dir"]
    monkeypatch = setup_kaydet["monkeypatch"]
    fake_log_dir.mkdir(exist_ok=True)

    # Wednesday 2025-10-29 → week starts Monday 2025-10-27
    mock_datetime_factory(datetime(2025, 10, 26, 10, 0, 0))  # Sunday prior
    monkeypatch.setattr(sys, "argv", ["kaydet", "Before this week"])
    cli.main()
    capsys.readouterr()

    mock_datetime_factory(datetime(2025, 10, 27, 10, 0, 0))  # Monday
    monkeypatch.setattr(sys, "argv", ["kaydet", "Monday note"])
    cli.main()
    capsys.readouterr()

    mock_datetime_factory(datetime(2025, 10, 29, 15, 0, 0))  # Wednesday
    monkeypatch.setattr(sys, "argv", ["kaydet", "Wednesday note"])
    cli.main()
    capsys.readouterr()

    monkeypatch.setattr(sys, "argv", ["kaydet", "--week"])
    cli.main()
    output = capsys.readouterr().out
    assert "Monday note" in output
    assert "Wednesday note" in output
    assert "Before this week" not in output
    assert "since 2025-10-27" in output


def test_month_shorthand_filters_to_first(
    setup_kaydet, capsys, mock_datetime_factory
):
    """--month lists entries since the 1st of the current month."""
    fake_log_dir = setup_kaydet["fake_log_dir"]
    monkeypatch = setup_kaydet["monkeypatch"]
    fake_log_dir.mkdir(exist_ok=True)

    mock_datetime_factory(datetime(2025, 9, 30, 10, 0, 0))
    monkeypatch.setattr(sys, "argv", ["kaydet", "September leftover"])
    cli.main()
    capsys.readouterr()

    mock_datetime_factory(datetime(2025, 10, 1, 9, 0, 0))
    monkeypatch.setattr(sys, "argv", ["kaydet", "October first"])
    cli.main()
    capsys.readouterr()

    mock_datetime_factory(datetime(2025, 10, 15, 12, 0, 0))
    monkeypatch.setattr(sys, "argv", ["kaydet", "Mid October"])
    cli.main()
    capsys.readouterr()

    monkeypatch.setattr(sys, "argv", ["kaydet", "--month"])
    cli.main()
    output = capsys.readouterr().out
    assert "October first" in output
    assert "Mid October" in output
    assert "September leftover" not in output
    assert "since 2025-10-01" in output


def test_week_and_today_are_mutually_exclusive(setup_kaydet, capsys):
    """--week and --today cannot be combined."""
    monkeypatch = setup_kaydet["monkeypatch"]
    monkeypatch.setattr(sys, "argv", ["kaydet", "--week", "--today"])
    with pytest.raises(SystemExit):
        cli.main()
