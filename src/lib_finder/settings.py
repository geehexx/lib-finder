"""Settings surface for `lib-finder`.

The settings object reads process environment variables with the
``LIB_FINDER_`` prefix. This tranche does not enable implicit ``.env`` file
loading.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from ._defaults import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_DB_PATH,
    DEFAULT_DETAIL_CONCURRENCY,
    DEFAULT_QUEUE_SIZE,
    DEFAULT_READ_TIMEOUT,
    DEFAULT_REQUEST_TIMEOUT,
)
from .sources.constants import DEFAULT_USER_AGENT


class LibFinderSettings(BaseSettings):
    """Repo-wide environment settings for CLI-driven pipelines."""

    model_config = SettingsConfigDict(
        env_prefix="LIB_FINDER_",
        extra="ignore",
    )

    db_path: Path = DEFAULT_DB_PATH
    csv_export_path: Path | None = None
    package_names: tuple[str, ...] = Field(default_factory=tuple)
    all_packages: bool = False
    queue_size: int = DEFAULT_QUEUE_SIZE
    batch_size: int = DEFAULT_BATCH_SIZE
    request_timeout: float = DEFAULT_REQUEST_TIMEOUT
    read_timeout: float = DEFAULT_READ_TIMEOUT
    detail_concurrency: int = DEFAULT_DETAIL_CONCURRENCY
    user_agent: str = DEFAULT_USER_AGENT
    record_limit: int | None = None
    extraction_model_id: str | None = None
    extraction_model_url: str | None = None
