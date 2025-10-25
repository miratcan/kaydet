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
__version__ = "0.28.1"
__description__ = (
    "Simple and terminal-based personal diary app designed to help you "
    "preserve your daily thoughts, experiences, and memories."
)

from .cli import main
