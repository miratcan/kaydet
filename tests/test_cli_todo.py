"""CLI --todo: create path + bare --todo as pure filter sugar."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime

from kaydet import cli


def test_expand_cli_sugar_bare_todo():
    """Bare --todo desugars to filter '#todo' and clears args.todo."""
    args = argparse.Namespace(todo=[], filter=None)
    cli.expand_cli_sugar(args)
    assert args.filter == "#todo"
    assert args.todo is None


def test_expand_cli_sugar_todo_with_existing_filter():
    args = argparse.Namespace(todo=[], filter="#work")
    cli.expand_cli_sugar(args)
    assert args.filter == "#work #todo"
    assert args.todo is None


def test_expand_cli_sugar_create_path_untouched():
    args = argparse.Namespace(todo=["Buy milk"], filter=None)
    cli.expand_cli_sugar(args)
    assert args.todo == ["Buy milk"]
    assert args.filter is None


def test_bare_todo_identical_to_filter_todo(
    setup_kaydet, capsys, mock_datetime_factory
):
    """kaydet --todo and kaydet --filter '#todo' must be byte-identical."""
    monkeypatch = setup_kaydet["monkeypatch"]

    mock_datetime_factory(datetime(2025, 10, 27, 10, 0, 0))
    monkeypatch.setattr(
        sys,
        "argv",
        ["kaydet", "--todo", "Ship the release notes", "priority:high"],
    )
    cli.main()
    capsys.readouterr()

    log_dir = setup_kaydet["fake_log_dir"]
    day = log_dir / "2025-10-27.txt"
    lines = day.read_text(encoding="utf-8").splitlines(keepends=True)
    out = []
    for line in lines:
        out.append(line)
        if "Ship the release notes" in line:
            out.append("Details go in the body paragraph.\n")
    day.write_text("".join(out), encoding="utf-8")

    monkeypatch.setattr(sys, "argv", ["kaydet", "--todo"])
    cli.main()
    via_todo = capsys.readouterr().out

    monkeypatch.setattr(sys, "argv", ["kaydet", "--filter", "#todo"])
    cli.main()
    via_filter = capsys.readouterr().out

    assert via_todo == via_filter
    assert "Details go in the body paragraph." in via_todo
    assert "Pending Todos" not in via_todo


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
    via_todo = capsys.readouterr().out

    monkeypatch.setattr(
        sys, "argv", ["kaydet", "--filter", "#work #todo"]
    )
    cli.main()
    via_filter = capsys.readouterr().out

    assert via_todo == via_filter
    assert "Work item only" in via_todo
    assert "Home chore" not in via_todo
