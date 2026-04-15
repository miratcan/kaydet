"""Kaydet package metadata."""

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
__version__ = "0.36.0"
__description__ = (
    "A queryable personal database stored in plain text. "
    "Capture, query, and remember."
)

from .cli import main
