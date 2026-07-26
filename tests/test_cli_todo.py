"""CLI --todo as filter shortcut and create path."""

from __future__ import annotations

import sys
from datetime import datetime

from kaydet import cli


def test_bare_todo_is_filter_shortcut(
    setup_kaydet, capsys, mock_datetime_factory
):
    """kaydet --todo lists via search UI (same as --filter '#todo')."""
    monkeypatch = setup_kaydet["monkeypatch"]

    mock_datetime_factory(datetime(2025, 10, 27, 10, 0, 0))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "kaydet",
            "--todo",
            "Ship the release notes",
            "priority:high",
        ],
    )
    cli.main()
    capsys.readouterr()

    # Manually append a body line to the day file (create_entry is header-only)
    log_dir = setup_kaydet["fake_log_dir"]
    day = log_dir / "2025-10-27.txt"
    text = day.read_text(encoding="utf-8")
    # Insert body after the todo header line
    lines = text.splitlines(keepends=True)
    out = []
    for line in lines:
        out.append(line)
        if "Ship the release notes" in line:
            out.append("Details go in the body paragraph.\n")
    day.write_text("".join(out), encoding="utf-8")

    monkeypatch.setattr(sys, "argv", ["kaydet", "--todo"])
    cli.main()
    listed = capsys.readouterr().out

    # Search-style output, not TodoFormatter "Pending Todos" chrome
    assert "Pending Todos" not in listed
    assert "Ship the release notes" in listed
    assert "Details go in the body paragraph." in listed
    assert "#todo" in listed or "todo" in listed.lower()


def test_todo_with_filter_appends_todo_tag(
    setup_kaydet, capsys, mock_datetime_factory
):
    monkeypatch = setup_kaydet["monkeypatch"]

    mock_datetime_factory(datetime(2025, 10, 27, 11, 0, 0))
    monkeypatch.setattr(
        sys, "argv", ["kaydet", "--todo", "Work item only", "#work"]
    )
    cli.main()
    capsys.readouterr()

    mock_datetime_factory(datetime(2025, 10, 27, 12, 0, 0))
    monkeypatch.setattr(
        sys, "argv", ["kaydet", "--todo", "Home chore", "#home"]
    )
    cli.main()
    capsys.readouterr()

    monkeypatch.setattr(
        sys, "argv", ["kaydet", "--todo", "--filter", "#work"]
    )
    cli.main()
    out = capsys.readouterr().out
    assert "Work item only" in out
    assert "Home chore" not in out
