"""Factories for PyPI Simple payload record construction."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from packaging.utils import canonicalize_name

from .models import ProjectDetailRecord, ProjectDiscoveryRecord
from .parsing import (
    _build_project_file_record,
    _canonical_payload_json,
    _parse_files,
    _parse_meta_api_version,
    _parse_serial_from_payload,
    _parse_versions,
    _payload_hash,
    _suspicion_features,
)
from .status import parse_project_status


def _require_project_name(
    payload: Mapping[str, Any],
    *,
    field_name: str,
) -> str:
    try:
        raw_name = payload["name"]
    except KeyError as exc:
        raise ValueError(f"{field_name} is missing a valid name") from exc
    if not isinstance(raw_name, str) or not raw_name.strip():
        raise ValueError(f"{field_name} is missing a valid name")
    return raw_name


def _canonicalized_name(raw_name: str, *, field_name: str) -> str:
    normalized_name = canonicalize_name(raw_name)
    if not normalized_name:
        raise ValueError(f"{field_name} is missing a valid name")
    return normalized_name


@dataclass(slots=True)
class PyPIRecordFactory:
    """Construct normalized record models from PyPI Simple payloads."""

    def build_project_discovery_record(
        self,
        payload: Mapping[str, Any],
        *,
        root_last_serial: int | None,
        fetched_at: str,
    ) -> ProjectDiscoveryRecord:
        """Build a discovery record from a PyPI Simple root payload."""

        raw_name = _require_project_name(payload, field_name="PyPI project entry")
        normalized_name = _canonicalized_name(raw_name, field_name="PyPI project entry")
        raw_payload_json = _canonical_payload_json(payload)
        payload_hash = _payload_hash(raw_payload_json)

        return ProjectDiscoveryRecord(
            raw_name=raw_name,
            normalized_name=normalized_name,
            root_last_serial=root_last_serial,
            project_last_serial=_parse_serial_from_payload(payload),
            fetched_at=fetched_at,
            suspicion=_suspicion_features(raw_name, normalized_name),
            raw_payload_json=raw_payload_json,
            payload_hash=payload_hash,
        )

    def build_project_detail_record(
        self,
        payload: Mapping[str, Any],
        *,
        raw_name: str,
        root_last_serial: int | None,
        fetched_at: str,
        project_last_serial: int | None = None,
    ) -> ProjectDetailRecord:
        """Build a detail record from a PyPI Simple project payload."""

        project_name = _require_project_name(
            payload,
            field_name="PyPI project detail payload",
        )
        normalized_name = _canonicalized_name(
            project_name,
            field_name="PyPI project detail payload",
        )
        if canonicalize_name(raw_name) != normalized_name:
            raise ValueError(
                "PyPI project detail payload name does not match the discovered project"
            )

        raw_payload_json = _canonical_payload_json(payload)
        payload_hash = _payload_hash(raw_payload_json)
        detail_project_last_serial = (
            project_last_serial
            if project_last_serial is not None
            else _parse_serial_from_payload(payload)
        )
        project_status, status_reason = parse_project_status(payload)

        return ProjectDetailRecord(
            raw_name=raw_name,
            normalized_name=normalized_name,
            project_name=project_name,
            root_last_serial=root_last_serial,
            project_last_serial=detail_project_last_serial,
            fetched_at=fetched_at,
            project_status=project_status,
            status_reason=status_reason,
            meta_api_version=_parse_meta_api_version(payload),
            versions=_parse_versions(payload),
            files=tuple(
                _build_project_file_record(file_payload)
                for file_payload in _parse_files(payload)
            ),
            suspicion=_suspicion_features(raw_name, normalized_name),
            raw_payload_json=raw_payload_json,
            payload_hash=payload_hash,
        )


DEFAULT_PYPI_RECORD_FACTORY = PyPIRecordFactory()


__all__ = [
    "DEFAULT_PYPI_RECORD_FACTORY",
    "PyPIRecordFactory",
]
