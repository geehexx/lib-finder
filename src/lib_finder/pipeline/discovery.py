"""Discovery sync pipeline."""

from __future__ import annotations

import asyncio
import csv
import json
from typing import Any

import httpx

from ..sources.client import ProjectDiscoveryRecord, iter_root_project_records
from ..storage import SQLiteStore
from .config import SyncConfig, SyncResult


async def _produce_root_records(
    queue: asyncio.Queue[ProjectDiscoveryRecord | None],
    client: httpx.AsyncClient,
    *,
    record_limit: int | None,
) -> int | None:
    seen = 0
    root_last_serial: int | None = None
    async for record in iter_root_project_records(client):
        await queue.put(record)
        seen += 1
        root_last_serial = (
            record.root_last_serial
            if record.root_last_serial is not None
            else root_last_serial
        )
        if record_limit is not None and seen >= record_limit:
            break
    await queue.put(None)
    return root_last_serial


async def _consume_root_records(
    queue: asyncio.Queue[ProjectDiscoveryRecord | None],
    store: SQLiteStore,
    *,
    run_id: str,
    batch_size: int,
    csv_writer: Any | None,
) -> tuple[int, int, int | None]:
    batch: list[ProjectDiscoveryRecord] = []
    records_seen = 0
    records_written = 0
    root_last_serial: int | None = None

    async def flush() -> None:
        nonlocal batch, records_seen, records_written, root_last_serial
        if not batch:
            return
        result = store.write_discovery_batch(
            run_id=run_id,
            records=tuple(batch),
        )
        records_seen += result.records_seen
        records_written += result.records_written
        root_last_serial = (
            result.root_last_serial
            if result.root_last_serial is not None
            else root_last_serial
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
        batch = []

    while True:
        item = await queue.get()
        if item is None:
            break
        batch.append(item)
        if len(batch) >= batch_size:
            await flush()
    await flush()
    return records_seen, records_written, root_last_serial


async def _run_discovery_sync_impl(config: SyncConfig) -> SyncResult:
    """Synchronize the PyPI Simple root index into SQLite."""

    store = SQLiteStore.open(config.db_path)
    run_id: str | None = None
    records_seen = 0
    records_written = 0
    root_last_serial: int | None = None
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

    queue: asyncio.Queue[ProjectDiscoveryRecord | None] = asyncio.Queue(
        maxsize=config.queue_size
    )
    timeout = httpx.Timeout(config.request_timeout, read=config.read_timeout)

    try:
        run_id = store.start_run(
            source="pypi_simple_root",
            mode="discovery",
            root_last_serial=None,
            settings=config.as_settings(),
        )
        async with httpx.AsyncClient(
            headers={"User-Agent": config.user_agent},
            timeout=timeout,
            follow_redirects=True,
        ) as client:
            async with asyncio.TaskGroup() as task_group:
                producer_task = task_group.create_task(
                    _produce_root_records(
                        queue,
                        client,
                        record_limit=config.record_limit,
                    )
                )
                consumer_task = task_group.create_task(
                    _consume_root_records(
                        queue,
                        store,
                        run_id=run_id,
                        batch_size=config.batch_size,
                        csv_writer=csv_writer,
                    )
                )
            root_last_serial = producer_task.result()
            records_seen, records_written, consumer_root_last_serial = (
                consumer_task.result()
            )
            root_last_serial = (
                consumer_root_last_serial
                if consumer_root_last_serial is not None
                else root_last_serial
            )
        store.finish_run(
            run_id=run_id,
            status="completed",
            root_last_serial=root_last_serial,
            records_seen=records_seen,
            records_written=records_written,
            error_count=0,
        )
        return SyncResult(
            run_id=run_id,
            records_seen=records_seen,
            records_written=records_written,
            root_last_serial=root_last_serial,
            csv_export_path=config.csv_export_path,
        )
    except Exception as exc:
        if run_id is not None:
            current_seen, current_written, current_root_last_serial = (
                store.get_run_progress(run_id)
            )
            store.record_failure(
                run_id=run_id,
                stage="pypi_simple_root",
                identity=None,
                error=exc,
                retryable=True,
            )
            store.finish_run(
                run_id=run_id,
                status="failed",
                root_last_serial=current_root_last_serial
                if current_root_last_serial is not None
                else root_last_serial,
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


def run_discovery_sync(config: SyncConfig) -> SyncResult:
    """Synchronize the PyPI Simple root index into SQLite."""

    return asyncio.run(_run_discovery_sync_impl(config))
