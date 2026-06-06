from __future__ import annotations

from lib_finder.storage.factories import (
    AdoptionQualificationCalculator,
    ProjectDetailRowFactory,
)


def test_project_detail_row_factory_uses_fallback_name_and_optional_keys() -> None:
    factory = ProjectDetailRowFactory()
    prepared = factory.prepare(
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

    assert prepared.normalized_name == "requests"
    assert prepared.detail_last_serial == 4321
    assert prepared.package_row[0] == "requests"
    assert prepared.package_row[5] == "active"
    assert prepared.package_row[6] == "maintained"
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


def test_adoption_qualification_calculator_scores_and_states() -> None:
    calculator = AdoptionQualificationCalculator()

    assert calculator.score(
        project_status="inactive",
        version_count=1,
        artifact_count=1,
        wheel_count=1,
        sdist_count=0,
        yanked_artifact_count=0,
    ) == (0, "excluded", "excluded: project_status=inactive")

    assert calculator.score(
        project_status=None,
        version_count=0,
        artifact_count=0,
        wheel_count=0,
        sdist_count=0,
        yanked_artifact_count=0,
    ) == (0, "discovered", "score=0; versions=0; artifacts=0")

    assert calculator.score(
        project_status="active",
        version_count=2,
        artifact_count=2,
        wheel_count=1,
        sdist_count=1,
        yanked_artifact_count=0,
    ) == (36, "qualified", "score=36; versions=2; artifacts=2; status=active")

    assert calculator.score(
        project_status="active",
        version_count=2,
        artifact_count=2,
        wheel_count=1,
        sdist_count=1,
        yanked_artifact_count=2,
    ) == (16, "excluded", "excluded: all_artifacts_yanked")
