"""PyPI Simple payload parsers and normalized record builders."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .factories import DEFAULT_PYPI_RECORD_FACTORY
from .models import ProjectDetailRecord, ProjectDiscoveryRecord, ProjectFileRecord


def build_project_discovery_record(
    payload: Mapping[str, Any],
    *,
    root_last_serial: int | None,
    fetched_at: str,
) -> ProjectDiscoveryRecord:
    """Build a discovery record from a PyPI Simple root payload."""

    return DEFAULT_PYPI_RECORD_FACTORY.build_project_discovery_record(
        payload,
        root_last_serial=root_last_serial,
        fetched_at=fetched_at,
    )


def build_project_detail_record(
    payload: Mapping[str, Any],
    *,
    raw_name: str,
    root_last_serial: int | None,
    fetched_at: str,
    project_last_serial: int | None = None,
) -> ProjectDetailRecord:
    """Build a detail record from a PyPI Simple project payload."""

    return DEFAULT_PYPI_RECORD_FACTORY.build_project_detail_record(
        payload,
        raw_name=raw_name,
        root_last_serial=root_last_serial,
        fetched_at=fetched_at,
        project_last_serial=project_last_serial,
    )


__all__ = [
    "build_project_discovery_record",
    "build_project_detail_record",
    "ProjectDetailRecord",
    "ProjectDiscoveryRecord",
    "ProjectFileRecord",
]
