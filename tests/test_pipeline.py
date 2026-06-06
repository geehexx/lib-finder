from __future__ import annotations

import sqlite3
from typing import Any

import pytest

from lib_finder.pipeline import SyncConfig, run_discovery_sync, run_sync
from lib_finder.pipeline import QualificationConfig, run_qualification_sync
from lib_finder.sources.parsing import build_project_discovery_record
from lib_finder.storage import SQLiteStore


def _row_value(row: Any | None, key: str) -> Any:
    if row is None:
        return None
    mapping_row: Any = row
    return mapping_row[key]


def _scalar_value(row: Any | None, index: int = 0) -> Any:
    if row is None:
        return None
    sequence_row: Any = row
    return sequence_row[index]


@pytest.fixture(scope="module")
def vcr_config() -> dict[str, object]:
    return {
        "filter_headers": ["user-agent"],
    }


@pytest.mark.parametrize("csv_export", [None, "export.csv"])
@pytest.mark.recorded
@pytest.mark.vcr
@pytest.mark.smoke
def test_run_discovery_sync_writes_sqlite_and_optional_csv(
    tmp_path, csv_export
) -> None:
    db_path = tmp_path / "lib-finder.sqlite3"
    csv_path = None if csv_export is None else tmp_path / csv_export
    result = run_discovery_sync(
        SyncConfig(
            db_path=db_path,
            csv_export_path=csv_path,
            queue_size=2,
            batch_size=2,
            request_timeout=5.0,
            read_timeout=5.0,
            record_limit=3,
        )
    )

    assert result.records_seen == 3
    assert result.records_written == 3
    assert result.root_last_serial is not None
    assert db_path.exists()

    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        run_row = connection.execute(
            "SELECT status, root_last_serial, records_seen, records_written FROM index_runs ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        assert _row_value(run_row, "status") == "completed"
        assert _row_value(run_row, "root_last_serial") == result.root_last_serial
        assert _row_value(run_row, "records_seen") == 3
        assert _row_value(run_row, "records_written") == 3

        packages = connection.execute(
            "SELECT normalized_name, raw_name FROM packages ORDER BY normalized_name"
        ).fetchall()
        assert len(packages) == 3
        assert len({_row_value(row, "normalized_name") for row in packages}) == 3
        assert all(_row_value(row, "raw_name") for row in packages)
        source_count_row = connection.execute(
            "SELECT COUNT(*) FROM source_records"
        ).fetchone()
        assert source_count_row is not None
        source_count = _scalar_value(source_count_row)
        assert source_count == 3

    if csv_path is not None:
        csv_text = csv_path.read_text(encoding="utf-8").splitlines()
        assert (
            csv_text[0]
            == "raw_name,normalized_name,root_last_serial,fetched_at,payload_hash,suspicion_json"
        )
        assert len(csv_text) == 4


@pytest.mark.recorded
@pytest.mark.vcr
@pytest.mark.smoke
def test_run_sync_replays_detail_enrichment_from_sqlite(tmp_path) -> None:
    db_path = tmp_path / "lib-finder.sqlite3"
    store = SQLiteStore.open(db_path)
    discovery_run_id = store.start_run(
        source="pypi_simple_root",
        mode="discovery",
        root_last_serial=2468,
        settings={"seed": True},
    )
    store.write_discovery_batch(
        run_id=discovery_run_id,
        records=(
            build_project_discovery_record(
                {"name": "Requests"},
                root_last_serial=2468,
                fetched_at="2026-06-06T00:00:00+00:00",
            ),
        ),
    )
    store.close()

    result = run_sync(
        SyncConfig(
            db_path=db_path,
            queue_size=2,
            batch_size=2,
            request_timeout=5.0,
            read_timeout=5.0,
            detail_concurrency=2,
            record_limit=None,
        )
    )

    assert result.records_written == 1
    assert result.root_last_serial is None

    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        package_row = connection.execute(
            """
            SELECT normalized_name, project_last_serial, project_status, status_reason,
                   qualification_state, qualification_reason
            FROM packages
            WHERE normalized_name = ?
            """,
            ("requests",),
        ).fetchone()
        assert _row_value(package_row, "normalized_name") == "requests"
        assert _row_value(package_row, "project_last_serial") is not None
        assert _row_value(package_row, "qualification_state") in {
            "candidate",
            "qualified",
        }

        detail_source_count_row = connection.execute(
            "SELECT COUNT(*) FROM source_records WHERE source = ?",
            ("pypi_simple_project_detail",),
        ).fetchone()
        assert detail_source_count_row is not None
        detail_source_count = _scalar_value(detail_source_count_row)
        assert detail_source_count == 1
        snapshot_count_row = connection.execute(
            "SELECT COUNT(*) FROM project_detail_snapshots"
        ).fetchone()
        artifact_count_row = connection.execute(
            "SELECT COUNT(*) FROM project_artifacts"
        ).fetchone()
        version_count_row = connection.execute(
            "SELECT COUNT(*) FROM project_versions"
        ).fetchone()
        rollup_count_row = connection.execute(
            "SELECT COUNT(*) FROM package_adoption_rollups"
        ).fetchone()
        assert snapshot_count_row is not None
        assert artifact_count_row is not None
        assert version_count_row is not None
        assert rollup_count_row is not None
        snapshot_count = _scalar_value(snapshot_count_row)
        artifact_count = _scalar_value(artifact_count_row)
        version_count = _scalar_value(version_count_row)
        rollup_count = _scalar_value(rollup_count_row)
        assert snapshot_count == 1
        assert artifact_count >= 1
        assert version_count >= 1
        assert rollup_count == 1


def test_run_qualification_sync_backfills_rollups_from_sqlite(tmp_path) -> None:
    db_path = tmp_path / "lib-finder.sqlite3"
    store = SQLiteStore.open(db_path)
    discovery_run_id = store.start_run(
        source="pypi_simple_root",
        mode="discovery",
        root_last_serial=111,
        settings={"seed": True},
    )
    store.write_discovery_batch(
        run_id=discovery_run_id,
        records=tuple(
            build_project_discovery_record(
                {"name": name},
                root_last_serial=111,
                fetched_at="2026-06-06T00:00:00+00:00",
            )
            for name in ["Requests", "Flask"]
        ),
    )
    store.write_project_detail_batch(
        run_id=discovery_run_id,
        records=(
            {
                "name": "requests",
                "meta": {"_last-serial": 222, "api-version": "1.4"},
                "project-status": {"status": "active", "reason": "maintained"},
                "versions": ["2.31.0", "2.32.0"],
                "files": [
                    {
                        "filename": "requests-2.31.0.tar.gz",
                        "url": "https://files.pythonhosted.org/packages/example/requests-2.31.0.tar.gz",
                        "hashes": {"sha256": "1111"},
                        "size": 100,
                        "upload-time": "2026-06-06T00:00:00Z",
                        "yanked": False,
                    },
                    {
                        "filename": "requests-2.32.0-py3-none-any.whl",
                        "url": "https://files.pythonhosted.org/packages/example/requests-2.32.0-py3-none-any.whl",
                        "hashes": {"sha256": "2222"},
                        "size": 200,
                        "upload-time": "2026-06-06T01:00:00Z",
                        "yanked": False,
                    },
                ],
            },
        ),
    )
    store.close()

    result = run_qualification_sync(QualificationConfig(db_path=db_path))

    assert result.records_seen == 2
    assert result.records_written == 2
    assert result.qualified_count == 1

    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        package_rows = connection.execute(
            """
            SELECT normalized_name, qualification_state, qualification_reason
            FROM packages
            ORDER BY normalized_name
            """
        ).fetchall()
        assert [_row_value(row, "normalized_name") for row in package_rows] == [
            "flask",
            "requests",
        ]
        assert _row_value(package_rows[0], "qualification_state") == "discovered"
        assert _row_value(package_rows[1], "qualification_state") == "qualified"
        rollup_rows = connection.execute(
            """
            SELECT normalized_name, qualification_state
            FROM package_adoption_rollups
            ORDER BY normalized_name
            """
        ).fetchall()
        assert [_row_value(row, "qualification_state") for row in rollup_rows] == [
            "discovered",
            "qualified",
        ]


def test_run_qualification_sync_honors_record_limit_for_explicit_names(
    tmp_path,
) -> None:
    db_path = tmp_path / "lib-finder.sqlite3"
    store = SQLiteStore.open(db_path)
    discovery_run_id = store.start_run(
        source="pypi_simple_root",
        mode="discovery",
        root_last_serial=111,
        settings={"seed": True},
    )
    store.write_discovery_batch(
        run_id=discovery_run_id,
        records=tuple(
            build_project_discovery_record(
                {"name": name},
                root_last_serial=111,
                fetched_at="2026-06-06T00:00:00+00:00",
            )
            for name in ["Requests", "Flask"]
        ),
    )
    store.write_project_detail_batch(
        run_id=discovery_run_id,
        records=(
            {
                "name": "requests",
                "meta": {"_last-serial": 222, "api-version": "1.4"},
                "project-status": {"status": "active", "reason": "maintained"},
                "versions": ["2.31.0"],
                "files": [
                    {
                        "filename": "requests-2.31.0.tar.gz",
                        "url": "https://files.pythonhosted.org/packages/example/requests-2.31.0.tar.gz",
                        "hashes": {"sha256": "1111"},
                        "size": 100,
                        "upload-time": "2026-06-06T00:00:00Z",
                        "yanked": False,
                    },
                ],
            },
        ),
    )
    store.close()

    result = run_qualification_sync(
        QualificationConfig(
            db_path=db_path,
            package_names=("Requests", "Flask"),
            record_limit=1,
        )
    )

    assert result.records_seen == 1
    assert result.records_written == 1

    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        package_rows = connection.execute(
            """
            SELECT normalized_name, qualification_state, qualification_reason
            FROM packages
            ORDER BY normalized_name
            """
        ).fetchall()
        assert [_row_value(row, "normalized_name") for row in package_rows] == [
            "flask",
            "requests",
        ]
        rollup_count_row = connection.execute(
            "SELECT COUNT(*) FROM package_adoption_rollups"
        ).fetchone()
        assert rollup_count_row is not None
        assert _scalar_value(rollup_count_row) == 1
