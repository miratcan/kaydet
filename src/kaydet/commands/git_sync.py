"""Git sync commands for kaydet."""

from __future__ import annotations

import subprocess
from pathlib import Path

COMMIT_MESSAGE = "kaydet: auto-sync"


def _run_git(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
    )


def git_init(storage_dir: Path, remote_url: str | None = None) -> dict:
    """Initialize a git repo in the storage directory."""
    if (storage_dir / ".git").exists():
        return {"success": False, "message": "Git repo already initialized."}

    proc = _run_git(["init"], storage_dir)
    if proc.returncode != 0:
        return {"success": False, "message": proc.stderr.strip()}

    _run_git(["add", "-A"], storage_dir)
    proc = _run_git(
        ["commit", "-m", f"{COMMIT_MESSAGE} (initial)"], storage_dir
    )

    if remote_url:
        proc = _run_git(
            ["remote", "add", "origin", remote_url], storage_dir
        )
        if proc.returncode == 0:
            branch = _run_git(
                ["rev-parse", "--abbrev-ref", "HEAD"], storage_dir
            ).stdout.strip()
            _run_git(
                ["push", "-u", "origin", branch], storage_dir
            )

    msg = "Git repo initialized."
    if remote_url:
        msg += f" Remote set to {remote_url}."
    return {"success": True, "message": msg}


def git_commit(storage_dir: Path) -> dict:
    """Commit all changes to git."""
    if not (storage_dir / ".git").exists():
        return {"success": False, "message": "Not a git repository."}

    _run_git(["add", "-A"], storage_dir)
    proc = _run_git(
        ["commit", "-m", COMMIT_MESSAGE], storage_dir
    )

    if proc.returncode == 0:
        return {"success": True, "message": "Changes committed."}
    if "nothing to commit" in proc.stderr:
        return {"success": True, "message": "Nothing to commit."}
    return {"success": False, "message": proc.stderr.strip()}


def git_push(storage_dir: Path) -> dict:
    """Push commits to remote."""
    if not (storage_dir / ".git").exists():
        return {"success": False, "message": "Not a git repository."}

    proc = _run_git(["push"], storage_dir)
    if proc.returncode == 0:
        return {"success": True, "message": "Pushed to remote."}
    return {"success": False, "message": proc.stderr.strip()}


def git_pull(storage_dir: Path) -> dict:
    """Pull changes from remote."""
    if not (storage_dir / ".git").exists():
        return {"success": False, "message": "Not a git repository."}

    proc = _run_git(["pull", "--ff-only"], storage_dir)
    if proc.returncode == 0:
        return {"success": True, "message": "Pulled from remote."}
    return {"success": False, "message": proc.stderr.strip()}


def git_sync(storage_dir: Path) -> dict:
    """Commit, push, and pull in one step."""
    commit_result = git_commit(storage_dir)
    if not commit_result["success"] and "Nothing" not in commit_result.get(
        "message", ""
    ):
        return commit_result

    has_remote = _run_git(["remote", "-v"], storage_dir).stdout.strip()
    if not has_remote:
        return {
            "success": True,
            "message": "Committed (no remote configured).",
        }

    push_result = git_push(storage_dir)
    if not push_result["success"]:
        return push_result

    pull_result = git_pull(storage_dir)
    messages = [
        r["message"]
        for r in [commit_result, push_result, pull_result]
        if r["message"]
    ]
    return {"success": True, "message": " | ".join(messages)}


def git_status(storage_dir: Path) -> dict:
    """Show git status."""
    if not (storage_dir / ".git").exists():
        return {"success": False, "message": "Not a git repository."}

    proc = _run_git(["status", "--short"], storage_dir)
    return {"success": True, "message": proc.stdout.strip() or "Clean."}
