from __future__ import annotations

import hashlib
import json

import httpx
import pytest
from hypothesis import given, settings, strategies as st
from packaging.utils import canonicalize_name

from lib_finder.sources.factories import PyPIRecordFactory
from lib_finder.sources.constants import PYPI_SIMPLE_INDEX_URL
from lib_finder.sources.client import iter_root_project_records_from_response
from lib_finder.sources.parsing import (
    build_project_detail_record,
    build_project_discovery_record,
)


def test_build_project_discovery_record_normalizes_and_scores_name() -> None:
    record = build_project_discovery_record(
        {"name": "Requests"},
        root_last_serial=123,
        fetched_at="2026-06-06T00:00:00+00:00",
    )

    expected_payload = json.dumps(
        {"name": "Requests"}, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    assert record.raw_name == "Requests"
    assert record.normalized_name == "requests"
    assert record.root_last_serial == 123
    assert record.suspicion["has_mixed_case"] is True
    assert record.suspicion["starts_with_digit"] is False
    assert record.suspicion["length"] == len("Requests")
    assert (
        record.payload_hash
        == hashlib.sha256(expected_payload.encode("utf-8")).hexdigest()
    )


def test_factory_build_project_discovery_record_normalizes_and_scores_name() -> None:
    factory = PyPIRecordFactory()
    record = factory.build_project_discovery_record(
        {"name": "Requests"},
        root_last_serial=123,
        fetched_at="2026-06-06T00:00:00+00:00",
    )

    expected_payload = json.dumps(
        {"name": "Requests"}, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    assert record.raw_name == "Requests"
    assert record.normalized_name == "requests"
    assert record.root_last_serial == 123
    assert record.suspicion["has_mixed_case"] is True
    assert record.suspicion["starts_with_digit"] is False
    assert record.suspicion["length"] == len("Requests")
    assert (
        record.payload_hash
        == hashlib.sha256(expected_payload.encode("utf-8")).hexdigest()
    )


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


@pytest.mark.filterwarnings(
    "ignore:unclosed database in <sqlite3.Connection:ResourceWarning"
)
@pytest.mark.property
@settings(max_examples=50, deadline=None, database=None)
@given(
    raw_name=st.text(
        alphabet=st.characters(
            whitelist_categories=("Ll", "Lu", "Nd"),
            whitelist_characters="-_.",
        ),
        min_size=1,
        max_size=32,
    ).filter(lambda value: any(character.isalnum() for character in value)),
    extra_fields=st.dictionaries(
        keys=st.text(
            alphabet=st.characters(
                whitelist_categories=("Ll", "Lu", "Nd"),
                whitelist_characters="-_.",
            ),
            min_size=1,
            max_size=8,
        ).filter(lambda key: key != "name"),
        values=st.text(
            alphabet=st.characters(
                whitelist_categories=("Ll", "Lu", "Nd", "Zs"),
                whitelist_characters="-_./",
            ),
            max_size=16,
        ),
        max_size=3,
    ),
)
def test_build_project_discovery_record_canonicalizes_and_hashes(
    raw_name: str, extra_fields: dict[str, str]
) -> None:
    payload = {"name": raw_name, **extra_fields}
    record = build_project_discovery_record(
        payload,
        root_last_serial=123,
        fetched_at="2026-06-06T00:00:00+00:00",
    )
    expected_payload = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )

    assert record.normalized_name == canonicalize_name(raw_name)
    assert record.raw_payload_json == expected_payload
    assert (
        record.payload_hash
        == hashlib.sha256(expected_payload.encode("utf-8")).hexdigest()
    )
    assert record.suspicion["normalized_differs"] == (
        record.normalized_name != raw_name
    )
    assert record.suspicion["length"] == len(raw_name)


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
