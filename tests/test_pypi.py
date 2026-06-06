from __future__ import annotations

import hashlib
import json

import httpx
import pytest
import respx

from lib_finder.pypi import (
    PYPI_SIMPLE_INDEX_URL,
    build_project_discovery_record,
    build_project_detail_record,
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


def test_build_project_detail_record_parses_simple_detail_schema() -> None:
    record = build_project_detail_record(
        {
            "name": "requests",
            "project-status": {
                "status": "active",
                "reason": "maintained upstream",
            },
            "meta": {
                "api-version": "1.4",
                "_last-serial": 2469,
            },
            "versions": ["2.31.0", "2.32.0"],
            "files": [
                {
                    "filename": "requests-2.32.0-py3-none-any.whl",
                    "url": "https://files.pythonhosted.org/packages/example.whl",
                    "hashes": {
                        "sha256": "abc123",
                        "blake2b": "def456",
                    },
                    "requires-python": ">=3.8",
                    "core-metadata": {"sha256": "c0ffee"},
                    "yanked": False,
                    "size": 12345,
                    "upload-time": "2026-06-01T12:34:56.123456Z",
                    "provenance": "https://example.org/provenance.json",
                },
                {
                    "filename": "requests-2.31.0.tar.gz",
                    "url": "https://files.pythonhosted.org/packages/example.tar.gz",
                    "hashes": {"sha256": "fedcba"},
                    "dist-info-metadata": True,
                    "yanked": "bad sdist",
                    "size": 54321,
                    "upload-time": "2026-05-30T01:02:03Z",
                },
            ],
        },
        raw_name="Requests",
        root_last_serial=2468,
        fetched_at="2026-06-06T00:00:00+00:00",
    )

    assert record.raw_name == "Requests"
    assert record.normalized_name == "requests"
    assert record.project_name == "requests"
    assert record.root_last_serial == 2468
    assert record.project_last_serial == 2469
    assert record.project_status == "active"
    assert record.status_reason == "maintained upstream"
    assert record.meta_api_version == "1.4"
    assert record.versions == ("2.31.0", "2.32.0")
    assert len(record.files) == 2
    assert record.files[0].filename == "requests-2.32.0-py3-none-any.whl"
    assert record.files[0].hashes == {"blake2b": "def456", "sha256": "abc123"}
    assert record.files[0].core_metadata == {"sha256": "c0ffee"}
    assert record.files[0].dist_info_metadata is None
    assert record.files[0].yanked is False
    assert record.files[0].size == 12345
    assert record.files[0].upload_time == "2026-06-01T12:34:56.123456Z"
    assert record.files[0].provenance == "https://example.org/provenance.json"
    assert record.files[1].dist_info_metadata is True
    assert record.files[1].yanked == "bad sdist"


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
