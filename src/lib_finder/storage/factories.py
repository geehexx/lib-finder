"""Factory objects for storage row preparation and adoption scoring."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

from packaging.utils import (
    canonicalize_name,
    parse_sdist_filename,
    parse_wheel_filename,
)
from pydantic import BaseModel, ConfigDict


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


def _json_dump(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _snapshot_id(
    normalized_name: str,
    payload_hash: str,
    detail_last_serial: int | None,
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
                _json_dump(hashes if hashes is not None else {}),
                _json_dump(core_metadata),
                provenance,
                now,
                now,
                snapshot_id,
            )
        )
    return tuple(rows)


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


class ProjectDetailRowFactory:
    """Prepare normalized detail rows for persistence."""

    __slots__ = ()

    def prepare(
        self,
        record: Mapping[str, Any],
        *,
        now: str,
        source: str,
    ) -> PreparedProjectDetailRows:
        """Normalize one project-detail payload into batch-ready rows."""

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


class AdoptionQualificationCalculator:
    """Score adoption rollups from aggregate package signals."""

    __slots__ = ()

    def score(
        self,
        *,
        project_status: str | None,
        version_count: int,
        artifact_count: int,
        wheel_count: int,
        sdist_count: int,
        yanked_artifact_count: int,
    ) -> tuple[int, str, str]:
        """Return the rollup score, state, and explanation."""

        return _qualification_from_signals(
            project_status=project_status,
            version_count=version_count,
            artifact_count=artifact_count,
            wheel_count=wheel_count,
            sdist_count=sdist_count,
            yanked_artifact_count=yanked_artifact_count,
        )


DEFAULT_PROJECT_DETAIL_ROW_FACTORY = ProjectDetailRowFactory()
DEFAULT_ADOPTION_QUALIFICATION_CALCULATOR = AdoptionQualificationCalculator()
