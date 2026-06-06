from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from packaging.utils import (
    canonicalize_name,
    parse_sdist_filename,
    parse_wheel_filename,
)

from .pypi import ProjectDiscoveryRecord, ProjectSelectionRecord

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

CREATE TABLE IF NOT EXISTS project_detail_snapshots (
  id TEXT PRIMARY KEY,
  normalized_name TEXT NOT NULL,
  raw_name TEXT NOT NULL,
  fetched_at TEXT NOT NULL,
  detail_last_serial INTEGER,
  project_status TEXT,
  status_reason TEXT,
  payload_hash TEXT NOT NULL,
  raw_payload_json TEXT NOT NULL,
  FOREIGN KEY(normalized_name) REFERENCES packages(normalized_name)
);

CREATE TABLE IF NOT EXISTS project_versions (
  normalized_name TEXT NOT NULL,
  version TEXT NOT NULL,
  first_seen_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  snapshot_id TEXT NOT NULL,
  PRIMARY KEY (normalized_name, version),
  FOREIGN KEY(normalized_name) REFERENCES packages(normalized_name),
  FOREIGN KEY(snapshot_id) REFERENCES project_detail_snapshots(id)
);

CREATE TABLE IF NOT EXISTS project_artifacts (
  normalized_name TEXT NOT NULL,
  filename TEXT NOT NULL,
  version TEXT,
  url TEXT NOT NULL,
  size INTEGER,
  upload_time TEXT,
  requires_python TEXT,
  yanked INTEGER NOT NULL DEFAULT 0,
  yanked_reason TEXT,
  hashes_json TEXT NOT NULL DEFAULT '{}',
  core_metadata_json TEXT NOT NULL DEFAULT 'null',
  provenance TEXT,
  first_seen_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  snapshot_id TEXT NOT NULL,
  PRIMARY KEY (normalized_name, filename),
  FOREIGN KEY(normalized_name) REFERENCES packages(normalized_name),
  FOREIGN KEY(snapshot_id) REFERENCES project_detail_snapshots(id)
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
CREATE INDEX IF NOT EXISTS idx_packages_project_last_serial ON packages(project_last_serial);
CREATE INDEX IF NOT EXISTS idx_source_records_identity ON source_records(source, record_type, identity);
CREATE INDEX IF NOT EXISTS idx_project_detail_snapshots_name ON project_detail_snapshots(normalized_name);
CREATE INDEX IF NOT EXISTS idx_project_detail_snapshots_serial ON project_detail_snapshots(detail_last_serial);
CREATE INDEX IF NOT EXISTS idx_project_versions_snapshot ON project_versions(snapshot_id);
CREATE INDEX IF NOT EXISTS idx_project_artifacts_version ON project_artifacts(normalized_name, version);
"""


@dataclass(slots=True, frozen=True)
class DiscoveryBatchResult:
    records_seen: int
    records_written: int
    root_last_serial: int | None


@dataclass(slots=True, frozen=True)
class ProjectDetailBatchResult:
    records_seen: int
    records_written: int
    project_last_serial: int | None


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _json_dump(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _source_record_id(record: ProjectDiscoveryRecord) -> str:
    return _source_record_id_from_parts(
        source=record.source,
        record_type=record.record_type,
        identity=record.identity,
        serial=record.root_last_serial,
        payload_hash=record.payload_hash,
    )


def _source_record_id_from_parts(
    *,
    source: str,
    record_type: str,
    identity: str,
    serial: int | None,
    payload_hash: str,
) -> str:
    serial_bytes = b"" if serial is None else str(serial).encode("utf-8")
    digest = hashlib.sha256()
    digest.update(source.encode("utf-8"))
    digest.update(b"|")
    digest.update(record_type.encode("utf-8"))
    digest.update(b"|")
    digest.update(identity.encode("utf-8"))
    digest.update(b"|")
    digest.update(serial_bytes)
    digest.update(b"|")
    digest.update(payload_hash.encode("utf-8"))
    return digest.hexdigest()


def _settings_json(settings: Mapping[str, Any] | dict[str, Any]) -> str:
    return _json_dump(settings)


def _snapshot_id(
    normalized_name: str, payload_hash: str, detail_last_serial: int | None
) -> str:
    digest = hashlib.sha256()
    digest.update(normalized_name.encode("utf-8"))
    digest.update(b"|")
    digest.update(payload_hash.encode("utf-8"))
    digest.update(b"|")
    digest.update(
        ("" if detail_last_serial is None else str(detail_last_serial)).encode("utf-8")
    )
    return digest.hexdigest()


def _detail_last_serial(payload: Mapping[str, Any]) -> int | None:
    last_serial = payload.get("project_last_serial")
    if isinstance(last_serial, int):
        return last_serial
    if isinstance(last_serial, str) and last_serial.isdigit():
        return int(last_serial)

    last_serial = payload.get("detail_last_serial")
    if isinstance(last_serial, int):
        return last_serial
    if isinstance(last_serial, str) and last_serial.isdigit():
        return int(last_serial)

    meta = payload.get("meta")
    if isinstance(meta, Mapping):
        last_serial = meta.get("_last-serial")
        if isinstance(last_serial, int):
            return last_serial
        if isinstance(last_serial, str) and last_serial.isdigit():
            return int(last_serial)

    last_serial = payload.get("_last-serial")
    if isinstance(last_serial, int):
        return last_serial
    if isinstance(last_serial, str) and last_serial.isdigit():
        return int(last_serial)
    return None


def _project_status_fields(payload: Mapping[str, Any]) -> tuple[str | None, str | None]:
    status_value = payload.get("project_status")
    status_reason = payload.get("status_reason")
    if isinstance(status_value, str) and status_value.strip():
        if isinstance(status_reason, str) and status_reason.strip():
            return status_value, status_reason
        return status_value, None

    status_value = payload.get("project-status")
    if status_value is None:
        status_value = payload.get("project_status")
    if status_value is None:
        status_value = payload.get("status")

    if isinstance(status_value, Mapping):
        status = status_value.get("status")
        if not isinstance(status, str) or not status.strip():
            status = status_value.get("state")
        reason = status_value.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            reason = status_value.get("message")
        return (
            status if isinstance(status, str) and status.strip() else None,
            reason if isinstance(reason, str) and reason.strip() else None,
        )

    if isinstance(status_value, str) and status_value.strip():
        return status_value, None

    return None, None


def _artifact_version_from_filename(filename: str) -> str | None:
    try:
        _, version, _, _ = parse_wheel_filename(filename)
        return str(version)
    except Exception:
        pass

    try:
        _, version = parse_sdist_filename(filename)
        return str(version)
    except Exception:
        return None


def _artifact_yanked_fields(value: Any) -> tuple[int, str | None]:
    if isinstance(value, str):
        stripped = value.strip()
        if stripped:
            return 1, stripped
        return 0, None
    if value:
        return 1, None
    return 0, None


def _artifact_json_value(value: Any) -> str:
    return _json_dump(value)


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
        return (
            int(row["records_seen"]),
            int(row["records_written"]),
            row["root_last_serial"],
        )

    def list_package_selections(
        self,
        *,
        package_names: Sequence[str] | None = None,
        all_packages: bool = False,
        limit: int | None = None,
    ) -> tuple[ProjectSelectionRecord, ...]:
        if package_names is not None:
            selections: list[ProjectSelectionRecord] = []
            for raw_name in package_names:
                if not isinstance(raw_name, str) or not raw_name.strip():
                    raise ValueError("Package name overrides must be non-empty strings")
                normalized_name = canonicalize_name(raw_name)
                row = self.connection.execute(
                    """
                    SELECT raw_name, normalized_name, root_last_serial
                    FROM packages
                    WHERE normalized_name = ?
                    """,
                    (normalized_name,),
                ).fetchone()
                if row is None:
                    selections.append(
                        ProjectSelectionRecord(
                            raw_name=raw_name,
                            normalized_name=normalized_name,
                            root_last_serial=None,
                        )
                    )
                    continue
                selections.append(
                    ProjectSelectionRecord(
                        raw_name=row["raw_name"],
                        normalized_name=row["normalized_name"],
                        root_last_serial=row["root_last_serial"],
                    )
                )
            return tuple(selections)

        query = """
            SELECT raw_name, normalized_name, root_last_serial
            FROM packages
        """
        params: list[Any] = []
        if not all_packages:
            query += " WHERE project_last_serial IS NULL"
        query += " ORDER BY normalized_name"
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)
        rows = self.connection.execute(query, params).fetchall()
        return tuple(
            ProjectSelectionRecord(
                raw_name=row["raw_name"],
                normalized_name=row["normalized_name"],
                root_last_serial=row["root_last_serial"],
            )
            for row in rows
        )

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

    def record_checkpoint(
        self, *, stage: str, checkpoint: Mapping[str, Any] | dict[str, Any]
    ) -> None:
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

    def write_project_detail_batch(
        self,
        *,
        run_id: str,
        records: Sequence[Mapping[str, Any]],
        source: str = "pypi_simple_project_detail",
        mode: str = "detail",
    ) -> ProjectDetailBatchResult:
        if not records:
            return ProjectDetailBatchResult(
                records_seen=0, records_written=0, project_last_serial=None
            )

        now = _utc_now()
        record_count = len(records)
        project_last_serial = _detail_last_serial(records[-1])

        package_rows: list[tuple[Any, ...]] = []
        source_rows: list[tuple[Any, ...]] = []
        snapshot_rows: list[tuple[Any, ...]] = []
        version_rows: list[tuple[Any, ...]] = []
        artifact_rows: list[tuple[Any, ...]] = []
        latest_normalized_name: str | None = None

        for record in records:
            if not isinstance(record, Mapping):
                raise TypeError("Project detail record must be a mapping")

            raw_name = record.get("name")
            if not isinstance(raw_name, str) or not raw_name.strip():
                raw_name = record.get("raw_name")
            if not isinstance(raw_name, str) or not raw_name.strip():
                raw_name = record.get("project_name")
            if not isinstance(raw_name, str) or not raw_name.strip():
                raise ValueError("Project detail record is missing a valid name")

            normalized_name = canonicalize_name(raw_name)
            project_status, status_reason = _project_status_fields(record)
            detail_last_serial = _detail_last_serial(record)
            raw_payload_json = _json_dump(record)
            payload_hash = hashlib.sha256(raw_payload_json.encode("utf-8")).hexdigest()
            snapshot_id = _snapshot_id(
                normalized_name, payload_hash, detail_last_serial
            )
            latest_normalized_name = normalized_name

            package_rows.append(
                (
                    normalized_name,
                    raw_name,
                    now,
                    now,
                    detail_last_serial,
                    project_status,
                    status_reason,
                )
            )
            source_rows.append(
                (
                    _source_record_id_from_parts(
                        source=source,
                        record_type="project_detail",
                        identity=normalized_name,
                        serial=detail_last_serial,
                        payload_hash=payload_hash,
                    ),
                    source,
                    "project_detail",
                    normalized_name,
                    now,
                    None,
                    None,
                    detail_last_serial,
                    payload_hash,
                    raw_payload_json,
                    normalized_name,
                )
            )
            snapshot_rows.append(
                (
                    snapshot_id,
                    normalized_name,
                    raw_name,
                    now,
                    detail_last_serial,
                    project_status,
                    status_reason,
                    payload_hash,
                    raw_payload_json,
                )
            )

            versions = record.get("versions", [])
            if isinstance(versions, Sequence) and not isinstance(
                versions, (str, bytes)
            ):
                for version in versions:
                    if not isinstance(version, str) or not version.strip():
                        continue
                    version_rows.append(
                        (
                            normalized_name,
                            version,
                            now,
                            now,
                            snapshot_id,
                        )
                    )

            files = record.get("files", [])
            if isinstance(files, Sequence) and not isinstance(files, (str, bytes)):
                for file_entry in files:
                    if not isinstance(file_entry, Mapping):
                        raise TypeError(
                            "Project detail artifact entry must be a mapping"
                        )
                    filename = file_entry.get("filename")
                    url = file_entry.get("url")
                    if not isinstance(filename, str) or not filename.strip():
                        raise ValueError(
                            "Project detail artifact is missing a valid filename"
                        )
                    if not isinstance(url, str) or not url.strip():
                        raise ValueError(
                            "Project detail artifact is missing a valid url"
                        )

                    version = _artifact_version_from_filename(filename)
                    yanked, yanked_reason = _artifact_yanked_fields(
                        file_entry.get("yanked")
                    )
                    hashes = file_entry.get("hashes", {})
                    core_metadata = file_entry.get("core-metadata")
                    if core_metadata is None:
                        core_metadata = file_entry.get("core_metadata")
                    if core_metadata is None:
                        core_metadata = file_entry.get("data-core-metadata")
                    if core_metadata is None:
                        core_metadata = file_entry.get("data-dist-info-metadata")
                    if core_metadata is None:
                        core_metadata = file_entry.get("dist-info-metadata")
                    if core_metadata is None:
                        core_metadata = file_entry.get("dist_info_metadata")
                    provenance = file_entry.get("provenance")
                    if provenance is None:
                        provenance = file_entry.get("data-provenance")
                    upload_time = file_entry.get("upload-time")
                    if upload_time is None:
                        upload_time = file_entry.get("upload_time")
                    requires_python = file_entry.get("requires-python")
                    if requires_python is None:
                        requires_python = file_entry.get("requires_python")

                    artifact_rows.append(
                        (
                            normalized_name,
                            filename,
                            version,
                            url,
                            file_entry.get("size"),
                            upload_time,
                            requires_python,
                            yanked,
                            yanked_reason,
                            _artifact_json_value(hashes if hashes is not None else {}),
                            _artifact_json_value(core_metadata),
                            provenance,
                            now,
                            now,
                            snapshot_id,
                        )
                    )

        with self.connection:
            self.connection.executemany(
                """
                INSERT INTO packages (
                  normalized_name, raw_name, first_seen_at, last_seen_at,
                  root_last_serial, project_last_serial, project_status,
                  status_reason, suspicion_json
                ) VALUES (?, ?, ?, ?, NULL, ?, ?, ?, '{}')
                ON CONFLICT(normalized_name) DO UPDATE SET
                  raw_name = COALESCE(packages.raw_name, excluded.raw_name),
                  last_seen_at = excluded.last_seen_at,
                  project_last_serial = COALESCE(excluded.project_last_serial, packages.project_last_serial),
                  project_status = COALESCE(excluded.project_status, packages.project_status),
                  status_reason = COALESCE(excluded.status_reason, packages.status_reason)
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
            self.connection.executemany(
                """
                INSERT OR IGNORE INTO project_detail_snapshots (
                  id, normalized_name, raw_name, fetched_at, detail_last_serial,
                  project_status, status_reason, payload_hash, raw_payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                snapshot_rows,
            )
            self.connection.executemany(
                """
                INSERT INTO project_versions (
                  normalized_name, version, first_seen_at, last_seen_at, snapshot_id
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(normalized_name, version) DO UPDATE SET
                  last_seen_at = excluded.last_seen_at,
                  snapshot_id = excluded.snapshot_id
                """,
                version_rows,
            )
            self.connection.executemany(
                """
                INSERT INTO project_artifacts (
                  normalized_name, filename, version, url, size, upload_time,
                  requires_python, yanked, yanked_reason, hashes_json,
                  core_metadata_json, provenance, first_seen_at, last_seen_at, snapshot_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(normalized_name, filename) DO UPDATE SET
                  version = excluded.version,
                  url = excluded.url,
                  size = excluded.size,
                  upload_time = excluded.upload_time,
                  requires_python = excluded.requires_python,
                  yanked = excluded.yanked,
                  yanked_reason = excluded.yanked_reason,
                  hashes_json = excluded.hashes_json,
                  core_metadata_json = excluded.core_metadata_json,
                  provenance = excluded.provenance,
                  last_seen_at = excluded.last_seen_at,
                  snapshot_id = excluded.snapshot_id
                """,
                artifact_rows,
            )
            self.connection.execute(
                """
                UPDATE index_runs
                SET records_seen = records_seen + ?,
                    records_written = records_written + ?
                WHERE id = ?
                """,
                (record_count, record_count, run_id),
            )
            progress_row = self.connection.execute(
                """
                SELECT records_seen, records_written
                FROM index_runs
                WHERE id = ?
                """,
                (run_id,),
            ).fetchone()
            self.record_checkpoint(
                stage=source,
                checkpoint={
                    "run_id": run_id,
                    "project_last_serial": project_last_serial,
                    "records_seen": progress_row["records_seen"]
                    if progress_row is not None
                    else record_count,
                    "records_written": progress_row["records_written"]
                    if progress_row is not None
                    else record_count,
                    "latest_normalized_name": latest_normalized_name,
                    "mode": mode,
                },
            )

        return ProjectDetailBatchResult(
            records_seen=record_count,
            records_written=record_count,
            project_last_serial=project_last_serial,
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
            return DiscoveryBatchResult(
                records_seen=0, records_written=0, root_last_serial=None
            )

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
                    "root_last_serial": progress_row["root_last_serial"]
                    if progress_row is not None
                    else root_last_serial,
                    "records_seen": progress_row["records_seen"]
                    if progress_row is not None
                    else record_count,
                    "records_written": progress_row["records_written"]
                    if progress_row is not None
                    else record_count,
                    "latest_normalized_name": records[-1].normalized_name,
                },
            )

        return DiscoveryBatchResult(
            records_seen=record_count,
            records_written=record_count,
            root_last_serial=root_last_serial,
        )
