"""Kaydet terminal diary package metadata."""

from __future__ import annotations

__all__ = (
    "__version__",
    "__description__",
    "__author__",
    "__copyright__",
    "main",
)

__author__ = "Mirat Can Bayrak"
__copyright__ = "Copyright 2016, Planet Earth"
__version__ = "0.45.0"
__description__ = (
    "Terminal note-taking app for developers. CLI notes, work logs, "
    "daily journal, with SQLite FTS search and MCP AI integration."
)

from .cli import main
