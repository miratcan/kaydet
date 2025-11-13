"""Minimal cross-platform replacement for the external startfile package."""

from __future__ import annotations

import os
import subprocess
import sys


def startfile(path: str) -> None:
    """Open the provided path using the platform default handler."""

    if sys.platform.startswith("win"):
        os.startfile(path)  # type: ignore[attr-defined]
        return
    if sys.platform == "darwin":
        subprocess.Popen(["open", path])
        return
    subprocess.Popen(["xdg-open", path])
