from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .pypi import ProjectDiscoveryRecord

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA busy_timeout = 5000;

CREATE TABLE IF NOT EXISTS index_runs (
  id TEXT PRIMARY KEY,
  source TEXT NOT NULL,
  mode TEXT NOT NULL,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  status TEXT NOT NULL,
  root_last_serial INTEGER,
  records_seen INTEGER NOT NULL DEFAULT 0,
  records_written INTEGER NOT NULL DEFAULT 0,
  error_count INTEGER NOT NULL DEFAULT 0,
  settings_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS packages (
  normalized_name TEXT PRIMARY KEY,
  raw_name TEXT NOT NULL,
  first_seen_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  root_last_serial INTEGER,
  project_last_serial INTEGER,
  project_status TEXT,
  status_reason TEXT,
  suspicion_json TEXT NOT NULL DEFAULT '{}',
  qualification_state TEXT NOT NULL DEFAULT 'discovered'
);

CREATE TABLE IF NOT EXISTS source_records (
  id TEXT PRIMARY KEY,
  source TEXT NOT NULL,
  record_type TEXT NOT NULL,
  identity TEXT NOT NULL,
  fetched_at TEXT NOT NULL,
  etag TEXT,
  last_modified TEXT,
  serial INTEGER,
  payload_hash TEXT NOT NULL,
  raw_payload_json TEXT NOT NULL,
  normalized_name TEXT,
  FOREIGN KEY(normalized_name) REFERENCES packages(normalized_name)
);

CREATE TABLE IF NOT EXISTS stage_checkpoints (
  stage TEXT PRIMARY KEY,
  checkpoint_json TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS failure_events (
  id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  stage TEXT NOT NULL,
  identity TEXT,
  error_type TEXT NOT NULL,
  error_message TEXT NOT NULL,
  occurred_at TEXT NOT NULL,
  retryable INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_packages_status ON packages(project_status);
CREATE INDEX IF NOT EXISTS idx_packages_last_serial ON packages(root_last_serial);
CREATE INDEX IF NOT EXISTS idx_source_records_identity ON source_records(source, record_type, identity);
"""


@dataclass(slots=True, frozen=True)
class DiscoveryBatchResult:
    records_seen: int
    records_written: int
    root_last_serial: int | None


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _json_dump(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _source_record_id(record: ProjectDiscoveryRecord) -> str:
    serial_bytes = (
        b"" if record.root_last_serial is None else str(record.root_last_serial).encode("utf-8")
    )
    digest = hashlib.sha256()
    digest.update(record.source.encode("utf-8"))
    digest.update(b"|")
    digest.update(record.record_type.encode("utf-8"))
    digest.update(b"|")
    digest.update(record.identity.encode("utf-8"))
    digest.update(b"|")
    digest.update(serial_bytes)
    digest.update(b"|")
    digest.update(record.payload_hash.encode("utf-8"))
    return digest.hexdigest()


def _settings_json(settings: Mapping[str, Any] | dict[str, Any]) -> str:
    return _json_dump(settings)


@dataclass(slots=True)
class SQLiteStore:
    path: Path
    connection: sqlite3.Connection

    @classmethod
    def open(cls, path: Path) -> "SQLiteStore":
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(
            path,
            timeout=30.0,
            isolation_level="DEFERRED",
            check_same_thread=False,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = NORMAL")
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.executescript(SCHEMA_SQL)
        return cls(path=path, connection=connection)

    def close(self) -> None:
        self.connection.close()

    def start_run(
        self,
        *,
        source: str,
        mode: str,
        root_last_serial: int | None,
        settings: Mapping[str, Any] | dict[str, Any],
    ) -> str:
        run_id = hashlib.sha256(
            f"{source}|{mode}|{_utc_now()}".encode("utf-8")
        ).hexdigest()
        self.connection.execute(
            """
            INSERT INTO index_runs (
              id, source, mode, started_at, status, root_last_serial,
              records_seen, records_written, error_count, settings_json
            ) VALUES (?, ?, ?, ?, ?, ?, 0, 0, 0, ?)
            """,
            (
                run_id,
                source,
                mode,
                _utc_now(),
                "running",
                root_last_serial,
                _settings_json(settings),
            ),
        )
        self.connection.commit()
        return run_id

    def finish_run(
        self,
        *,
        run_id: str,
        status: str,
        root_last_serial: int | None,
        records_seen: int,
        records_written: int,
        error_count: int,
    ) -> None:
        self.connection.execute(
            """
            UPDATE index_runs
            SET finished_at = ?,
                status = ?,
                root_last_serial = COALESCE(?, root_last_serial),
                records_seen = ?,
                records_written = ?,
                error_count = ?
            WHERE id = ?
            """,
            (
                _utc_now(),
                status,
                root_last_serial,
                records_seen,
                records_written,
                error_count,
                run_id,
            ),
        )
        self.connection.commit()

    def get_run_progress(self, run_id: str) -> tuple[int, int, int | None]:
        row = self.connection.execute(
            """
            SELECT records_seen, records_written, root_last_serial
            FROM index_runs
            WHERE id = ?
            """,
            (run_id,),
        ).fetchone()
        if row is None:
            return 0, 0, None
        return int(row["records_seen"]), int(row["records_written"]), row["root_last_serial"]

    def record_failure(
        self,
        *,
        run_id: str,
        stage: str,
        identity: str | None,
        error: BaseException,
        retryable: bool,
    ) -> str:
        failure_id = hashlib.sha256(
            f"{run_id}|{stage}|{identity or ''}|{type(error).__name__}|{error}".encode(
                "utf-8"
            )
        ).hexdigest()
        self.connection.execute(
            """
            INSERT OR REPLACE INTO failure_events (
              id, run_id, stage, identity, error_type, error_message, occurred_at, retryable
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                failure_id,
                run_id,
                stage,
                identity,
                type(error).__name__,
                str(error),
                _utc_now(),
                1 if retryable else 0,
            ),
        )
        self.connection.commit()
        return failure_id

    def record_checkpoint(self, *, stage: str, checkpoint: Mapping[str, Any] | dict[str, Any]) -> None:
        self.connection.execute(
            """
            INSERT INTO stage_checkpoints (stage, checkpoint_json, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(stage) DO UPDATE SET
              checkpoint_json = excluded.checkpoint_json,
              updated_at = excluded.updated_at
            """,
            (stage, _json_dump(checkpoint), _utc_now()),
        )

    def write_discovery_batch(
        self,
        *,
        run_id: str,
        records: Sequence[ProjectDiscoveryRecord],
        source: str = "pypi_simple_root",
        mode: str = "discovery",
    ) -> DiscoveryBatchResult:
        if not records:
            return DiscoveryBatchResult(records_seen=0, records_written=0, root_last_serial=None)

        now = _utc_now()
        record_count = len(records)
        root_last_serial = records[-1].root_last_serial

        package_rows = [
            (
                record.normalized_name,
                record.raw_name,
                now,
                now,
                record.root_last_serial,
                _json_dump(record.suspicion),
            )
            for record in records
        ]
        source_rows = [
            (
                _source_record_id(record),
                record.source,
                record.record_type,
                record.identity,
                record.fetched_at,
                None,
                None,
                record.root_last_serial,
                record.payload_hash,
                record.raw_payload_json,
                record.normalized_name,
            )
            for record in records
        ]

        with self.connection:
            self.connection.executemany(
                """
                INSERT INTO packages (
                  normalized_name, raw_name, first_seen_at, last_seen_at,
                  root_last_serial, suspicion_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(normalized_name) DO UPDATE SET
                  raw_name = excluded.raw_name,
                  last_seen_at = excluded.last_seen_at,
                  root_last_serial = excluded.root_last_serial,
                  suspicion_json = excluded.suspicion_json
                """,
                package_rows,
            )
            self.connection.executemany(
                """
                INSERT OR IGNORE INTO source_records (
                  id, source, record_type, identity, fetched_at,
                  etag, last_modified, serial, payload_hash, raw_payload_json,
                  normalized_name
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                source_rows,
            )
            self.connection.execute(
                """
                UPDATE index_runs
                SET root_last_serial = COALESCE(?, root_last_serial),
                    records_seen = records_seen + ?,
                    records_written = records_written + ?
                WHERE id = ?
                """,
                (root_last_serial, record_count, record_count, run_id),
            )
            progress_row = self.connection.execute(
                """
                SELECT records_seen, records_written, root_last_serial
                FROM index_runs
                WHERE id = ?
                """,
                (run_id,),
            ).fetchone()
            self.record_checkpoint(
                stage="pypi_simple_root",
                checkpoint={
                    "run_id": run_id,
                    "root_last_serial": progress_row["root_last_serial"] if progress_row is not None else root_last_serial,
                    "records_seen": progress_row["records_seen"] if progress_row is not None else record_count,
                    "records_written": progress_row["records_written"] if progress_row is not None else record_count,
                    "latest_normalized_name": records[-1].normalized_name,
                },
            )

        return DiscoveryBatchResult(
            records_seen=record_count,
            records_written=record_count,
            root_last_serial=root_last_serial,
        )
