"""SQLite storage and rollup logic for `lib-finder`."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from pydantic import BaseModel, ConfigDict
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Connection, Engine
from packaging.utils import canonicalize_name

from ..sources.models import ProjectDiscoveryRecord, ProjectSelectionRecord
from .factories import (
    DEFAULT_ADOPTION_QUALIFICATION_CALCULATOR,
    DEFAULT_PROJECT_DETAIL_ROW_FACTORY,
)


class DiscoveryBatchResult(BaseModel):
    """Result summary for a discovery batch write."""

    model_config = ConfigDict(frozen=True)

    records_seen: int
    records_written: int
    root_last_serial: int | None


class ProjectDetailBatchResult(BaseModel):
    """Result summary for a project-detail batch write."""

    model_config = ConfigDict(frozen=True)

    records_seen: int
    records_written: int
    project_last_serial: int | None


class AdoptionRollupBatchResult(BaseModel):
    """Result summary for an adoption-rollup refresh."""

    model_config = ConfigDict(frozen=True)

    records_seen: int
    records_written: int
    qualified_count: int


class _SQLiteResultAdapter:
    """Close SQLAlchemy results after the caller consumes them."""

    def __init__(self, result) -> None:
        self._result = result

    def fetchone(self):
        try:
            return self._result.fetchone()
        finally:
            self._result.close()

    def fetchall(self):
        try:
            return self._result.fetchall()
        finally:
            self._result.close()

    def close(self) -> None:
        self._result.close()


class SQLiteConnectionAdapter:
    """Small compatibility wrapper over a SQLAlchemy connection."""

    def __init__(self, connection: Connection) -> None:
        self._connection = connection
        self._transaction = None

    def execute(self, statement: str, params: Any | None = None):
        statement_is_count_query = (
            isinstance(statement, str) and "SELECT COUNT(" in statement.lstrip().upper()
        )
        if params is None:
            result = self._connection.exec_driver_sql(statement)
        else:
            result = self._connection.exec_driver_sql(statement, params)
        if not result.returns_rows:
            result.close()
            return result
        if statement_is_count_query:
            return _SQLiteResultAdapter(result)
        return _SQLiteResultAdapter(result.mappings())

    def executemany(self, statement: str, params: Sequence[Any]):
        result = None
        for param in params:
            result = self._connection.exec_driver_sql(statement, param)
            if not result.returns_rows:
                result.close()
        return result

    def commit(self) -> None:
        self._connection.commit()

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "SQLiteConnectionAdapter":
        self._transaction = self._connection.begin()
        self._transaction.__enter__()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._transaction is None:
            return None
        return self._transaction.__exit__(exc_type, exc, tb)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _json_dump(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _row_value(row: Any | None, key: str) -> Any:
    """Return a named value from a SQL row or mapping-like result."""

    if row is None:
        return None
    mapping_row: Any = row
    return mapping_row[key]


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


def _alembic_config(path: Path) -> Config:
    """Build an Alembic config bound to the repository-local migration tree."""

    repo_root = Path(__file__).resolve().parents[3]
    config = Config(str(repo_root / "alembic.ini"))
    config.set_main_option(
        "script_location", str(repo_root / "src/lib_finder/storage/migrations")
    )
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{path}")
    return config


class SQLiteStore:
    """Single-writer SQLite persistence wrapper for package metadata."""

    def __init__(
        self,
        path: Path,
        engine: Engine,
        connection: SQLiteConnectionAdapter,
    ) -> None:
        self.path = path
        self.engine = engine
        self.connection = connection
        self._closed = False

    @classmethod
    def open(cls, path: Path) -> "SQLiteStore":
        """Open a SQLite store and initialize the schema."""

        path.parent.mkdir(parents=True, exist_ok=True)
        engine = create_engine(
            f"sqlite+pysqlite:///{path}",
            future=True,
            pool_pre_ping=True,
            connect_args={"timeout": 30.0},
        )

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragmas(dbapi_connection, _connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys = ON")
            cursor.execute("PRAGMA journal_mode = WAL")
            cursor.execute("PRAGMA synchronous = NORMAL")
            cursor.execute("PRAGMA busy_timeout = 5000")
            cursor.close()

        connection = engine.connect()
        with connection.begin():
            alembic_cfg = _alembic_config(path)
            alembic_cfg.attributes["connection"] = connection
            command.upgrade(alembic_cfg, "head")
        return cls(path, engine, SQLiteConnectionAdapter(connection))

    def close(self) -> None:
        """Close the underlying SQLite connection."""

        if self._closed:
            return
        self.connection.close()
        self.engine.dispose()
        self._closed = True

    def __del__(self) -> None:
        if self._closed:
            return
        try:
            self.close()
        except Exception:
            pass

    def start_run(
        self,
        *,
        source: str,
        mode: str,
        root_last_serial: int | None,
        settings: Mapping[str, Any] | dict[str, Any],
    ) -> str:
        """Create a new run record and return its identifier."""

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
        """Finalize a run with its last-known progress and status."""

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
        """Return the current progress counters for a run."""

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
            int(_row_value(row, "records_seen")),
            int(_row_value(row, "records_written")),
            _row_value(row, "root_last_serial"),
        )

    def list_package_selections(
        self,
        *,
        package_names: Sequence[str] | None = None,
        all_packages: bool = False,
        limit: int | None = None,
    ) -> tuple[ProjectSelectionRecord, ...]:
        """Return package targets for detail or rollup work."""

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
                        raw_name=_row_value(row, "raw_name"),
                        normalized_name=_row_value(row, "normalized_name"),
                        root_last_serial=_row_value(row, "root_last_serial"),
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
                raw_name=_row_value(row, "raw_name"),
                normalized_name=_row_value(row, "normalized_name"),
                root_last_serial=_row_value(row, "root_last_serial"),
            )
            for row in rows
        )

    def refresh_adoption_rollups(
        self,
        *,
        package_names: Sequence[str] | None = None,
        all_packages: bool = True,
    ) -> AdoptionRollupBatchResult:
        """Recompute and persist adoption rollups for the selected packages."""

        if package_names is not None:
            normalized_names = tuple(
                dict.fromkeys(
                    canonicalize_name(name)
                    for name in package_names
                    if isinstance(name, str) and name.strip()
                )
            )
        else:
            query = "SELECT normalized_name FROM packages"
            if not all_packages:
                query += " WHERE project_last_serial IS NOT NULL"
            query += " ORDER BY normalized_name"
            normalized_names = tuple(
                _row_value(row, "normalized_name")
                for row in self.connection.execute(query).fetchall()
            )

        if not normalized_names:
            return AdoptionRollupBatchResult(
                records_seen=0, records_written=0, qualified_count=0
            )

        placeholders = ", ".join("?" for _ in normalized_names)
        rows = self.connection.execute(
            f"""
            WITH version_summary AS (
              SELECT normalized_name, COUNT(*) AS version_count
              FROM project_versions
              GROUP BY normalized_name
            ),
            artifact_summary AS (
              SELECT
                normalized_name,
                COUNT(*) AS artifact_count,
                SUM(CASE WHEN lower(filename) LIKE '%.whl' THEN 1 ELSE 0 END) AS wheel_count,
                SUM(CASE WHEN lower(filename) LIKE '%.tar.gz' OR lower(filename) LIKE '%.zip' THEN 1 ELSE 0 END) AS sdist_count,
                SUM(CASE WHEN yanked = 1 THEN 1 ELSE 0 END) AS yanked_artifact_count,
                MAX(upload_time) AS latest_upload_time
              FROM project_artifacts
              GROUP BY normalized_name
            )
            SELECT
              p.normalized_name,
              p.raw_name,
              p.project_last_serial,
              p.project_status,
              COALESCE(v.version_count, 0) AS version_count,
              COALESCE(a.artifact_count, 0) AS artifact_count,
              COALESCE(a.wheel_count, 0) AS wheel_count,
              COALESCE(a.sdist_count, 0) AS sdist_count,
              COALESCE(a.yanked_artifact_count, 0) AS yanked_artifact_count,
              a.latest_upload_time
            FROM packages p
            LEFT JOIN version_summary v ON v.normalized_name = p.normalized_name
            LEFT JOIN artifact_summary a ON a.normalized_name = p.normalized_name
            WHERE p.normalized_name IN ({placeholders})
            ORDER BY p.normalized_name
            """,
            normalized_names,
        ).fetchall()

        now = _utc_now()
        rollup_rows: list[tuple[Any, ...]] = []
        package_updates: list[tuple[Any, ...]] = []
        qualified_count = 0
        for row in rows:
            score, state, reason = DEFAULT_ADOPTION_QUALIFICATION_CALCULATOR.score(
                project_status=_row_value(row, "project_status"),
                version_count=int(_row_value(row, "version_count") or 0),
                artifact_count=int(_row_value(row, "artifact_count") or 0),
                wheel_count=int(_row_value(row, "wheel_count") or 0),
                sdist_count=int(_row_value(row, "sdist_count") or 0),
                yanked_artifact_count=int(
                    _row_value(row, "yanked_artifact_count") or 0
                ),
            )
            if state == "qualified":
                qualified_count += 1
            rollup_rows.append(
                (
                    _row_value(row, "normalized_name"),
                    _row_value(row, "raw_name"),
                    int(_row_value(row, "version_count") or 0),
                    int(_row_value(row, "artifact_count") or 0),
                    int(_row_value(row, "wheel_count") or 0),
                    int(_row_value(row, "sdist_count") or 0),
                    int(_row_value(row, "yanked_artifact_count") or 0),
                    _row_value(row, "latest_upload_time"),
                    _row_value(row, "project_last_serial"),
                    _row_value(row, "project_status"),
                    score,
                    state,
                    reason,
                    now,
                )
            )
            package_updates.append(
                (
                    state,
                    reason,
                    _row_value(row, "normalized_name"),
                )
            )

        self.connection.executemany(
            """
            INSERT INTO package_adoption_rollups (
              normalized_name, raw_name, version_count, artifact_count,
              wheel_count, sdist_count, yanked_artifact_count,
              latest_upload_time, latest_project_last_serial, project_status,
              qualification_score, qualification_state, qualification_reason,
              computed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(normalized_name) DO UPDATE SET
              raw_name = excluded.raw_name,
              version_count = excluded.version_count,
              artifact_count = excluded.artifact_count,
              wheel_count = excluded.wheel_count,
              sdist_count = excluded.sdist_count,
              yanked_artifact_count = excluded.yanked_artifact_count,
              latest_upload_time = excluded.latest_upload_time,
              latest_project_last_serial = excluded.latest_project_last_serial,
              project_status = excluded.project_status,
              qualification_score = excluded.qualification_score,
              qualification_state = excluded.qualification_state,
              qualification_reason = excluded.qualification_reason,
              computed_at = excluded.computed_at
            """,
            rollup_rows,
        )
        self.connection.executemany(
            """
            UPDATE packages
            SET qualification_state = ?,
                qualification_reason = ?
            WHERE normalized_name = ?
            """,
            package_updates,
        )
        self.connection.commit()
        return AdoptionRollupBatchResult(
            records_seen=len(normalized_names),
            records_written=len(rows),
            qualified_count=qualified_count,
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
        """Persist a failure event and return its identifier."""

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
        """Store the latest checkpoint for a named stage."""

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
        """Persist a batch of project-detail records and their artifacts."""

        if not records:
            return ProjectDetailBatchResult(
                records_seen=0, records_written=0, project_last_serial=None
            )

        now = _utc_now()
        record_count = len(records)

        package_rows: list[tuple[Any, ...]] = []
        source_rows: list[tuple[Any, ...]] = []
        snapshot_rows: list[tuple[Any, ...]] = []
        version_rows: list[tuple[Any, ...]] = []
        artifact_rows: list[tuple[Any, ...]] = []
        latest_normalized_name: str | None = None
        latest_detail_last_serial: int | None = None

        for record in records:
            if not isinstance(record, Mapping):
                raise TypeError("Project detail record must be a mapping")

            prepared = DEFAULT_PROJECT_DETAIL_ROW_FACTORY.prepare(
                record,
                now=now,
                source=source,
            )
            latest_normalized_name = prepared.normalized_name
            latest_detail_last_serial = prepared.detail_last_serial
            package_rows.append(prepared.package_row)
            source_rows.append(prepared.source_row)
            snapshot_rows.append(prepared.snapshot_row)
            version_rows.extend(prepared.version_rows)
            artifact_rows.extend(prepared.artifact_rows)

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
                "project_last_serial": latest_detail_last_serial,
                "records_seen": _row_value(progress_row, "records_seen")
                if progress_row is not None
                else record_count,
                "records_written": _row_value(progress_row, "records_written")
                if progress_row is not None
                else record_count,
                "latest_normalized_name": latest_normalized_name,
                "mode": mode,
            },
        )
        self.connection.commit()

        return ProjectDetailBatchResult(
            records_seen=record_count,
            records_written=record_count,
            project_last_serial=latest_detail_last_serial,
        )

    def write_discovery_batch(
        self,
        *,
        run_id: str,
        records: Sequence[ProjectDiscoveryRecord],
        source: str = "pypi_simple_root",
        mode: str = "discovery",
    ) -> DiscoveryBatchResult:
        """Persist a batch of discovery records and update checkpoints."""

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
                "root_last_serial": _row_value(progress_row, "root_last_serial")
                if progress_row is not None
                else root_last_serial,
                "records_seen": _row_value(progress_row, "records_seen")
                if progress_row is not None
                else record_count,
                "records_written": _row_value(progress_row, "records_written")
                if progress_row is not None
                else record_count,
                "latest_normalized_name": records[-1].normalized_name,
            },
        )
        self.connection.commit()

        return DiscoveryBatchResult(
            records_seen=record_count,
            records_written=record_count,
            root_last_serial=root_last_serial,
        )
