from __future__ import annotations

import os

import pytest


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    if os.getenv("LIB_FINDER_LIVE") == "1":
        return

    skip_live = pytest.mark.skip(
        reason="set LIB_FINDER_LIVE=1 to run live external-service tests"
    )
    for item in items:
        if item.get_closest_marker("live") is not None:
            item.add_marker(skip_live)
