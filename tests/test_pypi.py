from __future__ import annotations

import hashlib
import json

import httpx
import pytest
import respx

from lib_finder.pypi import (
    PYPI_SIMPLE_INDEX_URL,
    build_project_discovery_record,
    iter_root_project_records,
    iter_root_project_records_from_response,
)


def test_build_project_discovery_record_normalizes_and_scores_name() -> None:
    record = build_project_discovery_record(
        {"name": "Requests"},
        root_last_serial=123,
        fetched_at="2026-06-06T00:00:00+00:00",
    )

    expected_payload = json.dumps({"name": "Requests"}, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    assert record.raw_name == "Requests"
    assert record.normalized_name == "requests"
    assert record.root_last_serial == 123
    assert record.suspicion["has_mixed_case"] is True
    assert record.suspicion["starts_with_digit"] is False
    assert record.suspicion["length"] == len("Requests")
    assert record.payload_hash == hashlib.sha256(expected_payload.encode("utf-8")).hexdigest()


@pytest.mark.asyncio
async def test_iter_root_project_records_from_response_parses_project_list() -> None:
    payload = json.dumps(
        {
            "meta": {"_last-serial": 123},
            "projects": [{"name": "Requests"}, {"name": "numpy"}],
        },
        separators=(",", ":"),
    ).encode("utf-8")
    response = httpx.Response(
        200,
        headers={"X-PyPI-Last-Serial": "123"},
        content=payload,
        request=httpx.Request("GET", PYPI_SIMPLE_INDEX_URL),
    )

    records = [
        record
        async for record in iter_root_project_records_from_response(
            response,
            root_last_serial=123,
        )
    ]

    assert [record.raw_name for record in records] == ["Requests", "numpy"]
    assert [record.normalized_name for record in records] == ["requests", "numpy"]
    assert all(record.root_last_serial == 123 for record in records)


@pytest.mark.asyncio
@respx.mock
async def test_iter_root_project_records_streams_via_httpx() -> None:
    payload = json.dumps(
        {
            "meta": {"_last-serial": 456},
            "projects": [{"name": "Django"}, {"name": "Flask"}],
        },
        separators=(",", ":"),
    ).encode("utf-8")
    respx.get(PYPI_SIMPLE_INDEX_URL).mock(
        return_value=httpx.Response(
            200,
            headers={"X-PyPI-Last-Serial": "456"},
            content=payload,
        )
    )

    async with httpx.AsyncClient() as client:
        records = [record async for record in iter_root_project_records(client)]

    assert [record.raw_name for record in records] == ["Django", "Flask"]
    assert [record.normalized_name for record in records] == ["django", "flask"]
