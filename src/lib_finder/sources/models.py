"""Typed PyPI source record models."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class ProjectDiscoveryRecord(BaseModel):
    """Normalized discovery record for a PyPI project."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    raw_name: str
    normalized_name: str
    root_last_serial: int | None
    project_last_serial: int | None
    fetched_at: str
    suspicion: dict[str, Any]
    raw_payload_json: str
    payload_hash: str

    @property
    def source(self) -> str:
        """Return the discovery source identifier."""

        return "pypi_simple_root"

    @property
    def record_type(self) -> str:
        """Return the canonical discovery record type."""

        return "project_discovery"

    @property
    def identity(self) -> str:
        """Return the stable discovery identity."""

        return self.normalized_name


class ProjectSelectionRecord(BaseModel):
    """Minimal package selection record used for detail fetches."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    raw_name: str
    normalized_name: str
    root_last_serial: int | None


class ProjectFileRecord(BaseModel):
    """Normalized artifact metadata parsed from a project detail page."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    filename: str
    url: str
    hashes: dict[str, str]
    size: int
    upload_time: str | None
    requires_python: str | None
    core_metadata: bool | dict[str, str] | None
    dist_info_metadata: bool | dict[str, str] | None
    provenance: str | None
    yanked: bool | str | None


class ProjectDetailRecord(BaseModel):
    """Normalized project-detail record with versions and artifacts."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    raw_name: str
    normalized_name: str
    project_name: str
    root_last_serial: int | None
    project_last_serial: int | None
    fetched_at: str
    project_status: str | None
    status_reason: str | None
    meta_api_version: str | None
    versions: tuple[str, ...]
    files: tuple[ProjectFileRecord, ...]
    suspicion: dict[str, Any]
    raw_payload_json: str
    payload_hash: str

    @property
    def source(self) -> str:
        """Return the project-detail source identifier."""

        return "pypi_simple_project_detail"

    @property
    def record_type(self) -> str:
        """Return the canonical project-detail record type."""

        return "project_detail"

    @property
    def identity(self) -> str:
        """Return the stable project-detail identity."""

        return self.normalized_name


__all__ = [
    "ProjectDiscoveryRecord",
    "ProjectSelectionRecord",
    "ProjectFileRecord",
    "ProjectDetailRecord",
]
