"""Helpers that combine settings with CLI overrides."""

from __future__ import annotations

from pathlib import Path

from .pipeline.config import QualificationConfig, SyncConfig
from .settings import LibFinderSettings


def build_sync_config(
    settings: LibFinderSettings,
    *,
    db_path: Path | None = None,
    csv_export_path: Path | None = None,
    package_names: tuple[str, ...] | None = None,
    all_packages: bool | None = None,
    queue_size: int | None = None,
    batch_size: int | None = None,
    request_timeout: float | None = None,
    read_timeout: float | None = None,
    detail_concurrency: int | None = None,
    user_agent: str | None = None,
    record_limit: int | None = None,
) -> SyncConfig:
    """Combine env settings with explicit CLI overrides into a sync config."""

    return SyncConfig(
        db_path=settings.db_path if db_path is None else db_path,
        csv_export_path=(
            settings.csv_export_path if csv_export_path is None else csv_export_path
        ),
        package_names=(
            settings.package_names if package_names is None else tuple(package_names)
        ),
        all_packages=settings.all_packages if all_packages is None else all_packages,
        queue_size=settings.queue_size if queue_size is None else queue_size,
        batch_size=settings.batch_size if batch_size is None else batch_size,
        request_timeout=(
            settings.request_timeout if request_timeout is None else request_timeout
        ),
        read_timeout=settings.read_timeout if read_timeout is None else read_timeout,
        detail_concurrency=(
            settings.detail_concurrency
            if detail_concurrency is None
            else detail_concurrency
        ),
        user_agent=settings.user_agent if user_agent is None else user_agent,
        record_limit=settings.record_limit if record_limit is None else record_limit,
    )


def build_qualification_config(
    settings: LibFinderSettings,
    *,
    db_path: Path | None = None,
    package_names: tuple[str, ...] | None = None,
    record_limit: int | None = None,
) -> QualificationConfig:
    """Combine env settings with explicit CLI overrides into a qualification config."""

    return QualificationConfig(
        db_path=settings.db_path if db_path is None else db_path,
        package_names=(
            settings.package_names if package_names is None else tuple(package_names)
        ),
        record_limit=settings.record_limit if record_limit is None else record_limit,
    )
