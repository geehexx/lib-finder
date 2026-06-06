from __future__ import annotations

import asyncio
import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from .pypi import DEFAULT_USER_AGENT, ProjectDiscoveryRecord, iter_root_project_records
from .storage import SQLiteStore

DEFAULT_DB_PATH = Path("data/cache/lib-finder.sqlite3")
DEFAULT_QUEUE_SIZE = 5_000
DEFAULT_BATCH_SIZE = 1_000
DEFAULT_REQUEST_TIMEOUT = 60.0
DEFAULT_READ_TIMEOUT = 300.0


@dataclass(slots=True, frozen=True)
class SyncConfig:
    db_path: Path = DEFAULT_DB_PATH
    csv_export_path: Path | None = None
    queue_size: int = DEFAULT_QUEUE_SIZE
    batch_size: int = DEFAULT_BATCH_SIZE
    request_timeout: float = DEFAULT_REQUEST_TIMEOUT
    read_timeout: float = DEFAULT_READ_TIMEOUT
    user_agent: str = DEFAULT_USER_AGENT
    record_limit: int | None = None

    def as_settings(self) -> dict[str, Any]:
        return {
            "db_path": str(self.db_path),
            "csv_export_path": None if self.csv_export_path is None else str(self.csv_export_path),
            "queue_size": self.queue_size,
            "batch_size": self.batch_size,
            "request_timeout": self.request_timeout,
            "read_timeout": self.read_timeout,
            "user_agent": self.user_agent,
            "record_limit": self.record_limit,
        }


@dataclass(slots=True, frozen=True)
class SyncResult:
    run_id: str
    records_seen: int
    records_written: int
    root_last_serial: int | None
    csv_export_path: Path | None


async def _produce_records(
    queue: asyncio.Queue[ProjectDiscoveryRecord | None],
    client: httpx.AsyncClient,
    *,
    record_limit: int | None,
) -> None:
    seen = 0
    async for record in iter_root_project_records(client):
        await queue.put(record)
        seen += 1
        if record_limit is not None and seen >= record_limit:
            break
    await queue.put(None)


async def _consume_records(
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
        result = await asyncio.to_thread(
            store.write_discovery_batch,
            run_id=run_id,
            records=tuple(batch),
        )
        records_seen += result.records_seen
        records_written += result.records_written
        root_last_serial = result.root_last_serial if result.root_last_serial is not None else root_last_serial

        if csv_writer is not None:
            for record in batch:
                csv_writer.writerow(
                    [
                        record.raw_name,
                        record.normalized_name,
                        record.root_last_serial,
                        record.fetched_at,
                        record.payload_hash,
                        json.dumps(record.suspicion, sort_keys=True, separators=(",", ":")),
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


async def run_discovery_sync(config: SyncConfig) -> SyncResult:
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
                task_group.create_task(
                    _produce_records(
                        queue,
                        client,
                        record_limit=config.record_limit,
                    )
                )
                consumer_task = task_group.create_task(
                    _consume_records(
                        queue,
                        store,
                        run_id=run_id,
                        batch_size=config.batch_size,
                        csv_writer=csv_writer,
                    )
                )
            records_seen, records_written, root_last_serial = consumer_task.result()
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
            current_seen, current_written, current_root_last_serial = store.get_run_progress(run_id)
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
                root_last_serial=current_root_last_serial if current_root_last_serial is not None else root_last_serial,
                records_seen=current_seen if current_seen is not None else records_seen,
                records_written=current_written if current_written is not None else records_written,
                error_count=1,
            )
        raise
    finally:
        if csv_file is not None:
            csv_file.close()
        store.close()


def run_sync(config: SyncConfig) -> SyncResult:
    return asyncio.run(run_discovery_sync(config))
