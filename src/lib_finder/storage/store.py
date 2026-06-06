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
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Connection, Engine
from pydantic import BaseModel, ConfigDict
from packaging.utils import (
    canonicalize_name,
    parse_sdist_filename,
    parse_wheel_filename,
)

from ..sources.models import ProjectDiscoveryRecord, ProjectSelectionRecord


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


class PreparedProjectDetailRows(BaseModel):
    """Normalized rows prepared from a single project-detail payload."""

    model_config = ConfigDict(frozen=True)

    normalized_name: str
    detail_last_serial: int | None
    package_row: tuple[Any, ...]
    source_row: tuple[Any, ...]
    snapshot_row: tuple[Any, ...]
    version_rows: tuple[tuple[Any, ...], ...]
    artifact_rows: tuple[tuple[Any, ...], ...]


class AdoptionRollupBatchResult(BaseModel):
    """Result summary for an adoption-rollup refresh."""

    model_config = ConfigDict(frozen=True)

    records_seen: int
    records_written: int
    qualified_count: int


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
        if statement_is_count_query:
            return result
        return result.mappings()

    def executemany(self, statement: str, params: Sequence[Any]):
        result = None
        for param in params:
            result = self._connection.exec_driver_sql(statement, param)
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


def _mapping_first_value(mapping: Mapping[str, Any], *keys: str) -> Any | None:
    for key in keys:
        value = mapping.get(key)
        if value is not None:
            return value
    return None


def _detail_record_name(payload: Mapping[str, Any]) -> str:
    for key in ("name", "raw_name", "project_name"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value
    raise ValueError("Project detail record is missing a valid name")


def _detail_version_rows(
    normalized_name: str,
    versions: Any,
    *,
    now: str,
    snapshot_id: str,
) -> tuple[tuple[Any, ...], ...]:
    if not isinstance(versions, Sequence) or isinstance(versions, (str, bytes)):
        return ()

    rows: list[tuple[Any, ...]] = []
    for version in versions:
        if not isinstance(version, str) or not version.strip():
            continue
        rows.append((normalized_name, version, now, now, snapshot_id))
    return tuple(rows)


def _detail_artifact_rows(
    normalized_name: str,
    files: Any,
    *,
    now: str,
    snapshot_id: str,
) -> tuple[tuple[Any, ...], ...]:
    if not isinstance(files, Sequence) or isinstance(files, (str, bytes)):
        return ()

    rows: list[tuple[Any, ...]] = []
    for file_entry in files:
        if not isinstance(file_entry, Mapping):
            raise TypeError("Project detail artifact entry must be a mapping")

        filename = file_entry.get("filename")
        url = file_entry.get("url")
        if not isinstance(filename, str) or not filename.strip():
            raise ValueError("Project detail artifact is missing a valid filename")
        if not isinstance(url, str) or not url.strip():
            raise ValueError("Project detail artifact is missing a valid url")

        version = _artifact_version_from_filename(filename)
        yanked, yanked_reason = _artifact_yanked_fields(file_entry.get("yanked"))
        hashes = file_entry.get("hashes", {})
        core_metadata = _mapping_first_value(
            file_entry,
            "core-metadata",
            "core_metadata",
            "data-core-metadata",
            "data-dist-info-metadata",
            "dist-info-metadata",
            "dist_info_metadata",
        )
        provenance = _mapping_first_value(file_entry, "provenance", "data-provenance")
        upload_time = _mapping_first_value(file_entry, "upload-time", "upload_time")
        requires_python = _mapping_first_value(
            file_entry, "requires-python", "requires_python"
        )

        rows.append(
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
    return tuple(rows)


def _prepare_project_detail_rows(
    record: Mapping[str, Any], *, now: str, source: str
) -> PreparedProjectDetailRows:
    raw_name = _detail_record_name(record)
    normalized_name = canonicalize_name(raw_name)
    project_status, status_reason = _project_status_fields(record)
    detail_last_serial = _detail_last_serial(record)
    raw_payload_json = _json_dump(record)
    payload_hash = hashlib.sha256(raw_payload_json.encode("utf-8")).hexdigest()
    snapshot_id = _snapshot_id(normalized_name, payload_hash, detail_last_serial)

    return PreparedProjectDetailRows(
        normalized_name=normalized_name,
        detail_last_serial=detail_last_serial,
        package_row=(
            normalized_name,
            raw_name,
            now,
            now,
            detail_last_serial,
            project_status,
            status_reason,
        ),
        source_row=(
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
        ),
        snapshot_row=(
            snapshot_id,
            normalized_name,
            raw_name,
            now,
            detail_last_serial,
            project_status,
            status_reason,
            payload_hash,
            raw_payload_json,
        ),
        version_rows=_detail_version_rows(
            normalized_name,
            record.get("versions", []),
            now=now,
            snapshot_id=snapshot_id,
        ),
        artifact_rows=_detail_artifact_rows(
            normalized_name,
            record.get("files", []),
            now=now,
            snapshot_id=snapshot_id,
        ),
    )


def _qualification_from_signals(
    *,
    project_status: str | None,
    version_count: int,
    artifact_count: int,
    wheel_count: int,
    sdist_count: int,
    yanked_artifact_count: int,
) -> tuple[int, str, str]:
    status = project_status.strip().lower() if isinstance(project_status, str) else None
    if status in {"deprecated", "inactive", "archived"}:
        return 0, "excluded", f"excluded: project_status={status}"

    base_score = (
        version_count * 8
        + artifact_count * 5
        + wheel_count * 7
        + sdist_count * 3
        - yanked_artifact_count * 10
    )
    score = max(0, min(100, base_score))

    if version_count == 0 and artifact_count == 0:
        return (
            score,
            "discovered",
            (f"score={score}; versions={version_count}; artifacts={artifact_count}"),
        )

    if artifact_count > 0 and yanked_artifact_count == artifact_count:
        return score, "excluded", "excluded: all_artifacts_yanked"

    if score >= 30 and version_count >= 1 and artifact_count >= 1:
        return (
            score,
            "qualified",
            (
                f"score={score}; versions={version_count}; artifacts={artifact_count}; status="
                f"{status or 'none'}"
            ),
        )

    return (
        score,
        "candidate",
        (
            f"score={score}; versions={version_count}; artifacts={artifact_count}; status="
            f"{status or 'none'}"
        ),
    )


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

        self.connection.close()
        self.engine.dispose()

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
            score, state, reason = _qualification_from_signals(
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

            prepared = _prepare_project_detail_rows(record, now=now, source=source)
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
