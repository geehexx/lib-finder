"""Project-status parsing helpers for PyPI Simple payloads."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def _require_string(value: Any, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"PyPI Simple payload field '{field_name}' must be a string")
    return value


def _parse_status_mapping(
    value: Any,
    *,
    field_name: str,
) -> tuple[str | None, str | None]:
    if value is None:
        return None, None
    if not isinstance(value, Mapping):
        raise TypeError(f"PyPI Simple payload field '{field_name}' must be a mapping")

    status: str | None = None
    reason: str | None = None

    status_value = value.get("status")
    if status_value is not None:
        status = _require_string(status_value, field_name=f"{field_name}.status")

    reason_value = value.get("reason")
    if reason_value is not None:
        reason = _require_string(reason_value, field_name=f"{field_name}.reason")

    return status, reason


def _parse_meta_project_status(
    payload: Mapping[str, Any],
) -> tuple[str | None, str | None]:
    status, reason = _parse_status_mapping(
        payload.get("project-status"),
        field_name="meta.project-status",
    )

    meta_reason_value = payload.get("project-status-reason")
    if reason is None and meta_reason_value is not None:
        reason = _require_string(
            meta_reason_value, field_name="meta.project-status-reason"
        )

    return status, reason


def parse_project_status(payload: Mapping[str, Any]) -> tuple[str | None, str | None]:
    """Return the project status and reason from a PyPI detail payload."""

    status, reason = _parse_status_mapping(
        payload.get("project-status"),
        field_name="project-status",
    )

    meta_value = payload.get("meta")
    if isinstance(meta_value, Mapping):
        meta_status, meta_reason = _parse_meta_project_status(meta_value)
        if status is None:
            status = meta_status
        if reason is None:
            reason = meta_reason

    return status, reason
