from __future__ import annotations

from typing import List

import pytest
from unittest.mock import patch


@pytest.fixture
def mocker():
    """Provide a minimal subset of the pytest-mock mocker fixture."""

    active_patches: List[patch] = []

    class _Mocker:
        def patch(self, target, *args, **kwargs):
            mocked = patch(target, *args, **kwargs)
            active_patches.append(mocked)
            return mocked.start()

    helper = _Mocker()
    try:
        yield helper
    finally:
        while active_patches:
            active_patches.pop().stop()
