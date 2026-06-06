from __future__ import annotations

import json

import httpx
import pytest

from lib_finder.sources.factories import PyPIRecordFactory
from lib_finder.sources.client import iter_root_project_records_from_response
from lib_finder.sources.models import (
    ProjectFileRecord,
    ProjectDetailRecord,
    ProjectDiscoveryRecord,
    ProjectSelectionRecord,
)
from lib_finder.sources.parsing import (
    build_project_detail_record,
    build_project_discovery_record,
)


def test_project_discovery_record_exposes_properties_and_string_serial() -> None:
    record = build_project_discovery_record(
        {"name": "Requests", "_last-serial": "123"},
        root_last_serial=99,
        fetched_at="2026-06-06T00:00:00+00:00",
    )

    assert isinstance(record, ProjectDiscoveryRecord)
    assert record.source == "pypi_simple_root"
    assert record.record_type == "project_discovery"
    assert record.identity == "requests"
    assert record.project_last_serial == 123


def test_project_detail_record_defaults_optional_fields_and_properties() -> None:
    record = build_project_detail_record(
        {"name": "requests"},
        raw_name="Requests",
        root_last_serial=99,
        fetched_at="2026-06-06T00:00:00+00:00",
    )

    assert isinstance(record, ProjectDetailRecord)
    assert record.source == "pypi_simple_project_detail"
    assert record.record_type == "project_detail"
    assert record.identity == "requests"
    assert record.project_status is None
    assert record.status_reason is None
    assert record.meta_api_version is None
    assert record.versions == ()
    assert record.files == ()


def test_project_detail_record_reads_project_status_from_meta_fallback() -> None:
    factory = PyPIRecordFactory()
    record = factory.build_project_detail_record(
        {
            "name": "requests",
            "meta": {
                "project-status": {
                    "status": "active",
                    "reason": "maintained upstream",
                },
                "project-status-reason": "meta fallback",
            },
        },
        raw_name="Requests",
        root_last_serial=99,
        fetched_at="2026-06-06T00:00:00+00:00",
    )

    assert record.project_status == "active"
    assert record.status_reason == "maintained upstream"


def test_project_detail_record_factory_uses_canonical_names() -> None:
    factory = PyPIRecordFactory()
    record = factory.build_project_detail_record(
        {
            "name": "requests",
            "meta": {"_last-serial": 2469},
            "versions": ["2.31.0"],
            "files": [],
        },
        raw_name="Requests",
        root_last_serial=99,
        fetched_at="2026-06-06T00:00:00+00:00",
    )

    assert record.normalized_name == "requests"
    assert record.project_name == "requests"
    assert record.project_last_serial == 2469


def test_project_discovery_record_coerces_serials() -> None:
    record = ProjectDiscoveryRecord.model_validate(
        {
            "raw_name": "Requests",
            "normalized_name": "requests",
            "root_last_serial": "123",
            "project_last_serial": "456",
            "fetched_at": "2026-06-06T00:00:00+00:00",
            "suspicion": {},
            "raw_payload_json": "{}",
            "payload_hash": "abc123",
        }
    )

    assert record.root_last_serial == 123
    assert record.project_last_serial == 456


def test_project_selection_record_coerces_root_last_serial() -> None:
    record = ProjectSelectionRecord.model_validate(
        {
            "raw_name": "Requests",
            "normalized_name": "requests",
            "root_last_serial": "123",
        }
    )

    assert record.root_last_serial == 123


def test_project_detail_record_coerces_versions_and_files() -> None:
    record = ProjectDetailRecord.model_validate(
        {
            "raw_name": "Requests",
            "normalized_name": "requests",
            "project_name": "requests",
            "root_last_serial": 99,
            "project_last_serial": 100,
            "fetched_at": "2026-06-06T00:00:00+00:00",
            "project_status": None,
            "status_reason": None,
            "meta_api_version": None,
            "versions": ["2.32.0"],
            "files": [
                {
                    "filename": "requests-2.32.0-py3-none-any.whl",
                    "url": "https://files.pythonhosted.org/packages/example.whl",
                    "hashes": {"sha256": "abc123"},
                    "size": 12345,
                    "upload_time": None,
                    "requires_python": None,
                    "core_metadata": None,
                    "dist_info_metadata": None,
                    "provenance": None,
                    "yanked": None,
                }
            ],
            "suspicion": {},
            "raw_payload_json": "{}",
            "payload_hash": "abc123",
        }
    )

    assert record.versions == ("2.32.0",)
    assert isinstance(record.files[0], ProjectFileRecord)
    assert record.files[0].filename == "requests-2.32.0-py3-none-any.whl"


@pytest.mark.asyncio
async def test_iter_root_project_records_from_response_rejects_non_mapping_payload() -> (
    None
):
    response = httpx.Response(
        200,
        headers={"X-PyPI-Last-Serial": "123"},
        content=json.dumps({"projects": [1]}, separators=(",", ":")).encode("utf-8"),
        request=httpx.Request("GET", "https://pypi.org/simple/"),
    )

    with pytest.raises(TypeError, match="Unexpected PyPI Simple project payload type"):
        [
            record
            async for record in iter_root_project_records_from_response(
                response,
                root_last_serial=123,
            )
        ]
