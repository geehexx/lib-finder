"""PyPI Simple API client helpers."""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from datetime import UTC, datetime

import httpx
import ijson

from .constants import PYPI_SIMPLE_ACCEPT, PYPI_SIMPLE_INDEX_URL
from .models import ProjectDetailRecord, ProjectDiscoveryRecord, ProjectSelectionRecord
from .parsing import (
    build_project_detail_record,
    build_project_discovery_record,
)


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _parse_last_serial(value: str | None) -> int | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


async def fetch_project_detail_record(
    client: httpx.AsyncClient,
    project: ProjectDiscoveryRecord | ProjectSelectionRecord,
) -> ProjectDetailRecord:
    """Fetch and normalize the project-detail payload for a package."""

    response = await client.get(
        f"{PYPI_SIMPLE_INDEX_URL}{project.normalized_name}/",
        headers={"Accept": PYPI_SIMPLE_ACCEPT},
        follow_redirects=True,
    )
    response.raise_for_status()
    return build_project_detail_record(
        response.json(),
        raw_name=project.raw_name,
        root_last_serial=project.root_last_serial,
        fetched_at=_iso_now(),
        project_last_serial=_parse_last_serial(
            response.headers.get("X-PyPI-Last-Serial")
        ),
    )


async def iter_root_project_records(
    client: httpx.AsyncClient,
) -> AsyncIterator[ProjectDiscoveryRecord]:
    """Yield normalized discovery records from the PyPI Simple root."""

    async with client.stream(
        "GET",
        PYPI_SIMPLE_INDEX_URL,
        headers={"Accept": PYPI_SIMPLE_ACCEPT},
        follow_redirects=True,
    ) as response:
        response.raise_for_status()
        root_last_serial = _parse_last_serial(
            response.headers.get("X-PyPI-Last-Serial")
        )
        async for record in iter_root_project_records_from_response(
            response,
            root_last_serial=root_last_serial,
        ):
            yield record


async def iter_root_project_records_from_response(
    response: httpx.Response,
    *,
    root_last_serial: int | None,
) -> AsyncIterator[ProjectDiscoveryRecord]:
    """Yield discovery records from a parsed PyPI Simple root response."""

    fetched_at = _iso_now()
    stream = ijson.from_iter(response.aiter_bytes(chunk_size=64 * 1024))

    async for payload in ijson.items(stream, "projects.item"):
        if not isinstance(payload, Mapping):
            raise TypeError("Unexpected PyPI Simple project payload type")
        yield build_project_discovery_record(
            payload,
            root_last_serial=root_last_serial,
            fetched_at=fetched_at,
        )


__all__ = [
    "fetch_project_detail_record",
    "iter_root_project_records",
    "iter_root_project_records_from_response",
]
