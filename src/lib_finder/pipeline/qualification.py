"""Adoption-rollup qualification backfill pipeline."""

from __future__ import annotations

import asyncio

from ..storage import SQLiteStore
from .config import QualificationConfig, QualificationResult


def _checkpoint_after_normalized_name(
    store: SQLiteStore,
    stage: str,
) -> str | None:
    checkpoint = store.get_stage_checkpoint(stage)
    if checkpoint is None:
        return None
    latest_normalized_name = checkpoint.get("latest_normalized_name")
    if (
        not isinstance(latest_normalized_name, str)
        or not latest_normalized_name.strip()
    ):
        return None
    return latest_normalized_name


async def _run_qualification_sync_impl(
    config: QualificationConfig,
) -> QualificationResult:
    """Recompute adoption rollups from the data already stored in SQLite."""

    store = SQLiteStore.open(config.db_path)
    run_id: str | None = None
    try:
        if config.package_names:
            target_names = tuple(config.package_names)
            if config.record_limit is not None:
                target_names = target_names[: config.record_limit]
        else:
            target_names = tuple(
                selection.normalized_name
                for selection in store.list_package_selections(
                    all_packages=True,
                    limit=config.record_limit,
                    after_normalized_name=_checkpoint_after_normalized_name(
                        store,
                        "sqlite_adoption_rollups",
                    ),
                )
            )

        run_id = store.start_run(
            source="sqlite_adoption_rollups",
            mode="qualification",
            root_last_serial=None,
            settings=config.as_settings(),
        )
        result = store.refresh_adoption_rollups(
            package_names=target_names or None,
        )
        store.finish_run(
            run_id=run_id,
            status="completed",
            root_last_serial=None,
            records_seen=result.records_seen,
            records_written=result.records_written,
            error_count=0,
        )
        return QualificationResult(
            run_id=run_id,
            records_seen=result.records_seen,
            records_written=result.records_written,
            qualified_count=result.qualified_count,
        )
    except Exception as exc:
        if run_id is not None:
            current_seen, current_written, current_root_last_serial = (
                store.get_run_progress(run_id)
            )
            store.record_failure(
                run_id=run_id,
                stage="sqlite_adoption_rollups",
                identity=None,
                error=exc,
                retryable=True,
            )
            store.finish_run(
                run_id=run_id,
                status="failed",
                root_last_serial=current_root_last_serial,
                records_seen=current_seen,
                records_written=current_written,
                error_count=1,
            )
        raise
    finally:
        store.close()


def run_qualification_sync(
    config: QualificationConfig,
) -> QualificationResult:
    """Recompute adoption rollups from the data already stored in SQLite."""

    return asyncio.run(_run_qualification_sync_impl(config))
