"""Shared default values for `lib-finder` settings and pipeline helpers."""

from __future__ import annotations

from pathlib import Path

DEFAULT_DB_PATH = Path("data/cache/lib-finder.sqlite3")
DEFAULT_QUEUE_SIZE = 5_000
DEFAULT_BATCH_SIZE = 1_000
DEFAULT_REQUEST_TIMEOUT = 60.0
DEFAULT_READ_TIMEOUT = 300.0
DEFAULT_DETAIL_CONCURRENCY = 8
