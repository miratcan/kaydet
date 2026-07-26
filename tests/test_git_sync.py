"""Tests for git sync commands."""

from __future__ import annotations

from pathlib import Path

from kaydet.commands.git_sync import git_init, git_status, git_sync


def test_git_init_creates_repo(tmp_path: Path):
    """--init creates a .git directory."""
    res = git_init(tmp_path)
    assert res["success"] is True
    assert (tmp_path / ".git").exists()


def test_git_init_idempotent(tmp_path: Path):
    """--init on an existing repo warns without error."""
    git_init(tmp_path)
    res = git_init(tmp_path)
    assert res["success"] is False
    assert "already initialized" in res["message"]


def test_git_sync_commits_changes(tmp_path: Path):
    """--sync after adding a file commits it."""
    git_init(tmp_path)
    (tmp_path / "test.txt").write_text("hello")
    res = git_sync(tmp_path)
    assert res["success"] is True


def test_git_sync_no_remote_success(tmp_path: Path):
    """--sync without remote still commits locally."""
    git_init(tmp_path)
    (tmp_path / "note.txt").write_text("test content")
    res = git_sync(tmp_path)
    assert res["success"] is True
    assert "no remote" in res["message"]


def test_git_status_clean(tmp_path: Path):
    """--status shows clean after init."""
    git_init(tmp_path)
    res = git_status(tmp_path)
    assert res["success"] is True
    assert "Clean" in res["message"]


def test_git_status_dirty(tmp_path: Path):
    """--status shows dirty after adding a file."""
    git_init(tmp_path)
    (tmp_path / "untracked.txt").write_text("data")
    res = git_status(tmp_path)
    assert res["success"] is True
    assert "Clean" not in res["message"]


def test_git_status_no_repo(tmp_path: Path):
    """--status outside a repo shows error."""
    res = git_status(tmp_path)
    assert res["success"] is False
    assert "Not a git" in res["message"]


def test_git_sync_no_repo(tmp_path: Path):
    """--sync without git repo shows error."""
    res = git_sync(tmp_path)
    assert res["success"] is False
    assert "Not a git" in res["message"]
