from __future__ import annotations

from lib_finder.storage.store import (
    _artifact_version_from_filename,
    _artifact_yanked_fields,
    _detail_last_serial,
    _detail_record_name,
    _mapping_first_value,
    _prepare_project_detail_rows,
    _project_status_fields,
)


def test_detail_helpers_cover_serial_status_and_artifact_fallbacks() -> None:
    assert _detail_last_serial({"project_last_serial": 1}) == 1
    assert _detail_last_serial({"project_last_serial": "2"}) == 2
    assert _detail_last_serial({"detail_last_serial": 3}) == 3
    assert _detail_last_serial({"detail_last_serial": "4"}) == 4
    assert _detail_last_serial({"meta": {"_last-serial": 5}}) == 5
    assert _detail_last_serial({"_last-serial": "6"}) == 6
    assert _detail_last_serial({}) is None

    assert _project_status_fields(
        {"project_status": "active", "status_reason": "maintained"}
    ) == ("active", "maintained")
    assert _project_status_fields({"project_status": "active"}) == ("active", None)
    assert _project_status_fields(
        {"project-status": {"status": "deprecated", "reason": "old"}}
    ) == ("deprecated", "old")
    assert _project_status_fields({"status": "archived"}) == ("archived", None)
    assert _project_status_fields({}) == (None, None)

    assert _artifact_version_from_filename("requests-2.0-py3-none-any.whl") == "2.0"
    assert _artifact_version_from_filename("requests-2.0.tar.gz") == "2.0"
    assert _artifact_version_from_filename("not-a-package.txt") is None

    assert _artifact_yanked_fields("broken release") == (1, "broken release")
    assert _artifact_yanked_fields(True) == (1, None)
    assert _artifact_yanked_fields(False) == (0, None)
    assert _artifact_yanked_fields("") == (0, None)


def test_prepare_project_detail_rows_uses_fallback_name_and_optional_keys() -> None:
    prepared = _prepare_project_detail_rows(
        {
            "raw_name": "Requests",
            "detail_last_serial": "4321",
            "project_status": "active",
            "status_reason": "maintained",
            "versions": ["2.0", ""],
            "files": [
                {
                    "filename": "requests-2.0-py3-none-any.whl",
                    "url": "https://files.pythonhosted.org/packages/example.whl",
                    "hashes": {"sha256": "abc123"},
                    "size": 123,
                    "upload_time": "2026-06-06T00:00:00Z",
                    "requires_python": ">=3.11",
                    "core_metadata": {"sha256": "core"},
                    "data-provenance": "https://example.org/provenance.json",
                    "yanked": "needs rebuild",
                }
            ],
        },
        now="2026-06-06T00:00:00+00:00",
        source="pypi_simple_project_detail",
    )

    assert _detail_record_name({"raw_name": "Requests"}) == "Requests"
    assert prepared.normalized_name == "requests"
    assert prepared.detail_last_serial == 4321
    assert prepared.package_row[0] == "requests"
    assert prepared.source_row[1] == "pypi_simple_project_detail"
    assert prepared.snapshot_row[1] == "requests"
    assert prepared.version_rows == (
        (
            "requests",
            "2.0",
            "2026-06-06T00:00:00+00:00",
            "2026-06-06T00:00:00+00:00",
            prepared.snapshot_row[0],
        ),
    )
    assert prepared.artifact_rows[0][1] == "requests-2.0-py3-none-any.whl"
    assert prepared.artifact_rows[0][6] == ">=3.11"
    assert prepared.artifact_rows[0][8] == "needs rebuild"
    assert (
        _mapping_first_value(
            {"first": None, "second": "value"},
            "first",
            "second",
        )
        == "value"
    )
