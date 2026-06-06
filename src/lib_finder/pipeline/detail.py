"""Project-detail sync pipeline."""

from __future__ import annotations

import asyncio
import csv
import json
from typing import Any

import httpx

from ..sources.client import (
    ProjectDetailRecord,
    ProjectSelectionRecord,
    fetch_project_detail_record,
)
from ..storage import SQLiteStore
from .config import SyncConfig, SyncResult


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


async def _produce_detail_targets(
    queue: asyncio.Queue[ProjectSelectionRecord | None],
    targets: tuple[ProjectSelectionRecord, ...],
    *,
    record_limit: int | None,
    worker_count: int,
) -> int | None:
    seen = 0
    root_last_serial: int | None = None
    for target in targets:
        await queue.put(target)
        seen += 1
        root_last_serial = (
            target.root_last_serial
            if target.root_last_serial is not None
            else root_last_serial
        )
        if record_limit is not None and seen >= record_limit:
            break
    for _ in range(worker_count):
        await queue.put(None)
    return root_last_serial


async def _fetch_detail_records(
    root_queue: asyncio.Queue[ProjectSelectionRecord | None],
    detail_queue: asyncio.Queue[ProjectDetailRecord | None],
    client: httpx.AsyncClient,
) -> None:
    while True:
        item = await root_queue.get()
        if item is None:
            break
        await detail_queue.put(await fetch_project_detail_record(client, item))
    await detail_queue.put(None)


async def _consume_detail_records(
    queue: asyncio.Queue[ProjectDetailRecord | None],
    store: SQLiteStore,
    *,
    run_id: str,
    batch_size: int,
    csv_writer: Any | None,
    worker_count: int,
) -> tuple[int, int, int | None]:
    batch: list[ProjectDetailRecord] = []
    records_seen = 0
    records_written = 0
    project_last_serial: int | None = None
    completed_workers = 0

    async def flush() -> None:
        nonlocal batch, records_seen, records_written, project_last_serial
        if not batch:
            return
        batch_names = tuple(record.normalized_name for record in batch)
        result = store.write_project_detail_batch(
            run_id=run_id,
            records=tuple(record.model_dump(mode="python") for record in batch),
            source="pypi_simple_project_detail",
            mode="detail",
        )
        records_seen += result.records_seen
        records_written += result.records_written
        project_last_serial = (
            result.project_last_serial
            if result.project_last_serial is not None
            else project_last_serial
        )

        if csv_writer is not None:
            for record in batch:
                csv_writer.writerow(
                    [
                        record.raw_name,
                        record.normalized_name,
                        record.root_last_serial,
                        record.fetched_at,
                        record.payload_hash,
                        json.dumps(
                            record.suspicion, sort_keys=True, separators=(",", ":")
                        ),
                    ]
                )
        store.refresh_adoption_rollups(package_names=batch_names)
        batch = []

    while completed_workers < worker_count:
        item = await queue.get()
        if item is None:
            completed_workers += 1
            continue
        batch.append(item)
        if len(batch) >= batch_size:
            await flush()
    await flush()
    return records_seen, records_written, project_last_serial


async def _run_detail_sync_impl(config: SyncConfig) -> SyncResult:
    """Synchronize project-detail pages for SQLite-selected packages."""

    store = SQLiteStore.open(config.db_path)
    run_id: str | None = None
    records_seen = 0
    records_written = 0
    csv_file = None
    csv_writer = None

    if config.csv_export_path is not None:
        config.csv_export_path.parent.mkdir(parents=True, exist_ok=True)
        csv_file = config.csv_export_path.open("w", encoding="utf-8", newline="")
        csv_writer = csv.writer(csv_file, lineterminator="\n")
        csv_writer.writerow(
            [
                "raw_name",
                "normalized_name",
                "root_last_serial",
                "fetched_at",
                "payload_hash",
                "suspicion_json",
            ]
        )

    targets = store.list_package_selections(
        package_names=config.package_names if config.package_names else None,
        all_packages=config.all_packages,
        limit=config.record_limit,
        after_normalized_name=(
            None
            if config.package_names
            else _checkpoint_after_normalized_name(
                store,
                "pypi_simple_project_detail",
            )
        ),
    )
    detail_concurrency = max(1, config.detail_concurrency)
    root_queue: asyncio.Queue[ProjectSelectionRecord | None] = asyncio.Queue(
        maxsize=config.queue_size
    )
    detail_queue: asyncio.Queue[ProjectDetailRecord | None] = asyncio.Queue(
        maxsize=config.queue_size
    )
    timeout = httpx.Timeout(config.request_timeout, read=config.read_timeout)

    try:
        run_id = store.start_run(
            source="pypi_simple_project_detail",
            mode="detail",
            root_last_serial=None,
            settings=config.as_settings(),
        )
        async with httpx.AsyncClient(
            headers={"User-Agent": config.user_agent},
            timeout=timeout,
            follow_redirects=True,
        ) as client:
            async with asyncio.TaskGroup() as task_group:
                task_group.create_task(
                    _produce_detail_targets(
                        root_queue,
                        targets,
                        record_limit=config.record_limit,
                        worker_count=detail_concurrency,
                    )
                )
                for _ in range(detail_concurrency):
                    task_group.create_task(
                        _fetch_detail_records(
                            root_queue,
                            detail_queue,
                            client,
                        )
                    )
                consumer_task = task_group.create_task(
                    _consume_detail_records(
                        detail_queue,
                        store,
                        run_id=run_id,
                        batch_size=config.batch_size,
                        csv_writer=csv_writer,
                        worker_count=detail_concurrency,
                    )
                )
            records_seen, records_written, _ = consumer_task.result()
        store.finish_run(
            run_id=run_id,
            status="completed",
            root_last_serial=None,
            records_seen=records_seen,
            records_written=records_written,
            error_count=0,
        )
        return SyncResult(
            run_id=run_id,
            records_seen=records_seen,
            records_written=records_written,
            root_last_serial=None,
            csv_export_path=config.csv_export_path,
        )
    except Exception as exc:
        if run_id is not None:
            current_seen, current_written, current_root_last_serial = (
                store.get_run_progress(run_id)
            )
            store.record_failure(
                run_id=run_id,
                stage="pypi_simple_project_detail",
                identity=None,
                error=exc,
                retryable=True,
            )
            store.finish_run(
                run_id=run_id,
                status="failed",
                root_last_serial=current_root_last_serial,
                records_seen=current_seen if current_seen is not None else records_seen,
                records_written=current_written
                if current_written is not None
                else records_written,
                error_count=1,
            )
        raise
    finally:
        if csv_file is not None:
            csv_file.close()
        store.close()


def run_detail_sync(config: SyncConfig) -> SyncResult:
    """Synchronize project-detail pages for SQLite-selected packages."""

    return asyncio.run(_run_detail_sync_impl(config))
