"""Configuration and result models for the sync pipelines."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .._defaults import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_DB_PATH,
    DEFAULT_DETAIL_CONCURRENCY,
    DEFAULT_QUEUE_SIZE,
    DEFAULT_READ_TIMEOUT,
    DEFAULT_REQUEST_TIMEOUT,
)
from ..sources.constants import DEFAULT_USER_AGENT


class SyncConfig(BaseModel):
    """Configuration for the discovery and detail sync pipelines."""

    model_config = ConfigDict(frozen=True)

    db_path: Path = DEFAULT_DB_PATH
    csv_export_path: Path | None = None
    queue_size: int = DEFAULT_QUEUE_SIZE
    batch_size: int = DEFAULT_BATCH_SIZE
    request_timeout: float = DEFAULT_REQUEST_TIMEOUT
    read_timeout: float = DEFAULT_READ_TIMEOUT
    detail_concurrency: int = DEFAULT_DETAIL_CONCURRENCY
    package_names: tuple[str, ...] = Field(default_factory=tuple)
    all_packages: bool = False
    user_agent: str = DEFAULT_USER_AGENT
    record_limit: int | None = None

    def as_settings(self) -> dict[str, Any]:
        """Return a JSON-serializable snapshot of the sync settings."""

        return self.model_dump(mode="json")


class SyncResult(BaseModel):
    """Result summary for discovery and detail synchronization."""

    model_config = ConfigDict(frozen=True)

    run_id: str
    records_seen: int
    records_written: int
    root_last_serial: int | None
    csv_export_path: Path | None


class QualificationConfig(BaseModel):
    """Configuration for adoption-rollup backfills."""

    model_config = ConfigDict(frozen=True)

    db_path: Path = DEFAULT_DB_PATH
    package_names: tuple[str, ...] = Field(default_factory=tuple)
    record_limit: int | None = None

    def as_settings(self) -> dict[str, Any]:
        """Return a JSON-serializable snapshot of the qualification settings."""

        return self.model_dump(mode="json")


class QualificationResult(BaseModel):
    """Result summary for adoption-rollup recomputation."""

    model_config = ConfigDict(frozen=True)

    run_id: str
    records_seen: int
    records_written: int
    qualified_count: int
