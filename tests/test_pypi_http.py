from __future__ import annotations

import httpx
import pytest

from lib_finder.sources.client import (
    fetch_project_detail_record,
    iter_root_project_records,
)


@pytest.fixture(scope="module")
def vcr_config() -> dict[str, object]:
    return {
        "filter_headers": ["user-agent"],
    }


@pytest.mark.recorded
@pytest.mark.vcr
@pytest.mark.smoke
@pytest.mark.asyncio
async def test_recorded_root_and_detail_round_trip() -> None:
    async with httpx.AsyncClient() as client:
        target = None
        async for record in iter_root_project_records(client):
            if record.normalized_name == "requests":
                target = record
                break

        assert target is not None

        detail = await fetch_project_detail_record(client, target)

    assert detail.normalized_name == "requests"
    assert detail.versions
    assert detail.files
    assert detail.project_last_serial is not None


@pytest.mark.live
@pytest.mark.smoke
@pytest.mark.asyncio
async def test_live_root_and_detail_round_trip() -> None:
    async with httpx.AsyncClient() as client:
        target = None
        async for record in iter_root_project_records(client):
            if record.normalized_name == "requests":
                target = record
                break

        assert target is not None

        detail = await fetch_project_detail_record(client, target)

    assert detail.normalized_name == "requests"
    assert detail.versions
    assert detail.files
