from __future__ import annotations

import json

from lib_finder.pypi import build_project_discovery_record
from lib_finder.storage import SQLiteStore


def test_sqlite_store_creates_schema_and_persists_batches(tmp_path) -> None:
    db_path = tmp_path / "lib-finder.sqlite3"
    store = SQLiteStore.open(db_path)
    run_id = store.start_run(
        source="pypi_simple_root",
        mode="discovery",
        root_last_serial=987,
        settings={"csv_export_path": None, "queue_size": 10},
    )

    records = (
        build_project_discovery_record(
            {"name": "Requests"},
            root_last_serial=987,
            fetched_at="2026-06-06T00:00:00+00:00",
        ),
        build_project_discovery_record(
            {"name": "numpy"},
            root_last_serial=987,
            fetched_at="2026-06-06T00:00:00+00:00",
        ),
    )

    result = store.write_discovery_batch(run_id=run_id, records=records)
    assert result.records_seen == 2
    assert result.records_written == 2
    assert result.root_last_serial == 987

    package_rows = store.connection.execute(
        "SELECT normalized_name, raw_name, root_last_serial, suspicion_json FROM packages ORDER BY normalized_name"
    ).fetchall()
    assert [row["normalized_name"] for row in package_rows] == ["numpy", "requests"]
    assert package_rows[1]["raw_name"] == "Requests"
    assert package_rows[1]["root_last_serial"] == 987
    assert json.loads(package_rows[1]["suspicion_json"])["has_mixed_case"] is True

    source_count = store.connection.execute(
        "SELECT COUNT(*) FROM source_records"
    ).fetchone()[0]
    assert source_count == 2

    checkpoint = store.connection.execute(
        "SELECT checkpoint_json FROM stage_checkpoints WHERE stage = ?",
        ("pypi_simple_root",),
    ).fetchone()
    assert checkpoint is not None
    checkpoint_json = json.loads(checkpoint["checkpoint_json"])
    assert checkpoint_json["latest_normalized_name"] == "numpy"
    assert checkpoint_json["root_last_serial"] == 987

    store.finish_run(
        run_id=run_id,
        status="completed",
        root_last_serial=987,
        records_seen=2,
        records_written=2,
        error_count=0,
    )
    run_row = store.connection.execute(
        "SELECT status, root_last_serial, records_seen, records_written, error_count FROM index_runs WHERE id = ?",
        (run_id,),
    ).fetchone()
    assert run_row["status"] == "completed"
    assert run_row["root_last_serial"] == 987
    assert run_row["records_seen"] == 2
    assert run_row["records_written"] == 2
    assert run_row["error_count"] == 0

    store.close()


def test_write_discovery_batch_is_idempotent_for_source_records(tmp_path) -> None:
    db_path = tmp_path / "lib-finder.sqlite3"
    store = SQLiteStore.open(db_path)
    run_id = store.start_run(
        source="pypi_simple_root",
        mode="discovery",
        root_last_serial=555,
        settings={},
    )
    record = build_project_discovery_record(
        {"name": "Pydantic"},
        root_last_serial=555,
        fetched_at="2026-06-06T00:00:00+00:00",
    )

    store.write_discovery_batch(run_id=run_id, records=(record,))
    store.write_discovery_batch(run_id=run_id, records=(record,))

    source_count = store.connection.execute(
        "SELECT COUNT(*) FROM source_records"
    ).fetchone()[0]
    assert source_count == 1
    run_row = store.connection.execute(
        "SELECT records_seen, records_written FROM index_runs WHERE id = ?",
        (run_id,),
    ).fetchone()
    assert run_row["records_seen"] == 2
    assert run_row["records_written"] == 2

    store.close()


def test_list_package_selections_defaults_to_unenriched_packages(tmp_path) -> None:
    db_path = tmp_path / "lib-finder.sqlite3"
    store = SQLiteStore.open(db_path)
    run_id = store.start_run(
        source="pypi_simple_root",
        mode="discovery",
        root_last_serial=101,
        settings={},
    )
    store.write_discovery_batch(
        run_id=run_id,
        records=(
            build_project_discovery_record(
                {"name": "Requests"},
                root_last_serial=101,
                fetched_at="2026-06-06T00:00:00+00:00",
            ),
            build_project_discovery_record(
                {"name": "Flask"},
                root_last_serial=101,
                fetched_at="2026-06-06T00:00:00+00:00",
            ),
        ),
    )

    detail_payload = {
        "name": "requests",
        "meta": {"_last-serial": 202, "api-version": "1.4"},
        "versions": ["2.32.0"],
        "files": [],
    }
    store.write_project_detail_batch(run_id=run_id, records=(detail_payload,))

    default_selections = store.list_package_selections()
    assert [selection.normalized_name for selection in default_selections] == ["flask"]

    all_selections = store.list_package_selections(all_packages=True)
    assert [selection.normalized_name for selection in all_selections] == [
        "flask",
        "requests",
    ]

    explicit_selections = store.list_package_selections(
        package_names=["Requests", "Unknown"]
    )
    assert [selection.normalized_name for selection in explicit_selections] == [
        "requests",
        "unknown",
    ]
    assert explicit_selections[1].root_last_serial is None

    store.close()


def test_sqlite_store_creates_project_detail_schema_and_persists_detail_batch(
    tmp_path,
) -> None:
    db_path = tmp_path / "lib-finder.sqlite3"
    store = SQLiteStore.open(db_path)

    detail_tables = {
        row["name"]
        for row in store.connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name IN ('project_detail_snapshots', 'project_versions', 'project_artifacts')
            """
        ).fetchall()
    }
    assert detail_tables == {
        "project_detail_snapshots",
        "project_versions",
        "project_artifacts",
    }

    run_id = store.start_run(
        source="pypi_simple_project_detail",
        mode="detail",
        root_last_serial=None,
        settings={"source": "pypi_simple_project_detail"},
    )
    detail_payload = {
        "name": "requests",
        "meta": {"_last-serial": 4321, "api-version": "1.4"},
        "project-status": {"status": "active", "reason": "maintained"},
        "versions": ["2.31.0", "2.32.0"],
        "files": [
            {
                "filename": "requests-2.31.0.tar.gz",
                "url": "https://files.pythonhosted.org/packages/example/requests-2.31.0.tar.gz",
                "hashes": {"sha256": "1111"},
                "requires-python": None,
                "size": 100,
                "upload-time": "2026-06-06T00:00:00Z",
                "yanked": "broken release",
                "core-metadata": False,
                "provenance": None,
            },
            {
                "filename": "requests-2.32.0-py3-none-any.whl",
                "url": "https://files.pythonhosted.org/packages/example/requests-2.32.0-py3-none-any.whl",
                "hashes": {"sha256": "2222"},
                "requires-python": ">=3.9",
                "size": 200,
                "upload-time": "2026-06-06T01:00:00Z",
                "yanked": False,
                "core-metadata": {"sha256": "3333"},
                "provenance": "https://pypi.org/integrity/requests/2.32.0/requests-2.32.0-py3-none-any.whl/provenance",
            },
        ],
    }

    result = store.write_project_detail_batch(run_id=run_id, records=(detail_payload,))
    assert result.records_seen == 1
    assert result.records_written == 1
    assert result.project_last_serial == 4321

    package_row = store.connection.execute(
        """
        SELECT raw_name, project_last_serial, project_status, status_reason
        FROM packages
        WHERE normalized_name = ?
        """,
        ("requests",),
    ).fetchone()
    assert package_row["raw_name"] == "requests"
    assert package_row["project_last_serial"] == 4321
    assert package_row["project_status"] == "active"
    assert package_row["status_reason"] == "maintained"

    snapshot_row = store.connection.execute(
        """
        SELECT normalized_name, detail_last_serial, project_status, status_reason, raw_payload_json
        FROM project_detail_snapshots
        WHERE normalized_name = ?
        """,
        ("requests",),
    ).fetchone()
    assert snapshot_row["normalized_name"] == "requests"
    assert snapshot_row["detail_last_serial"] == 4321
    assert snapshot_row["project_status"] == "active"
    assert snapshot_row["status_reason"] == "maintained"
    assert json.loads(snapshot_row["raw_payload_json"])["versions"] == [
        "2.31.0",
        "2.32.0",
    ]

    version_rows = store.connection.execute(
        """
        SELECT version, first_seen_at, last_seen_at
        FROM project_versions
        WHERE normalized_name = ?
        ORDER BY version
        """,
        ("requests",),
    ).fetchall()
    assert [row["version"] for row in version_rows] == ["2.31.0", "2.32.0"]
    assert all(row["first_seen_at"] == row["last_seen_at"] for row in version_rows)

    artifact_rows = store.connection.execute(
        """
        SELECT filename, version, size, upload_time, requires_python, yanked, yanked_reason,
               hashes_json, core_metadata_json, provenance
        FROM project_artifacts
        WHERE normalized_name = ?
        ORDER BY filename
        """,
        ("requests",),
    ).fetchall()
    assert [row["filename"] for row in artifact_rows] == [
        "requests-2.31.0.tar.gz",
        "requests-2.32.0-py3-none-any.whl",
    ]
    assert artifact_rows[0]["version"] == "2.31.0"
    assert artifact_rows[0]["size"] == 100
    assert artifact_rows[0]["upload_time"] == "2026-06-06T00:00:00Z"
    assert artifact_rows[0]["requires_python"] is None
    assert artifact_rows[0]["yanked"] == 1
    assert artifact_rows[0]["yanked_reason"] == "broken release"
    assert json.loads(artifact_rows[0]["hashes_json"]) == {"sha256": "1111"}
    assert json.loads(artifact_rows[0]["core_metadata_json"]) is False
    assert artifact_rows[0]["provenance"] is None
    assert artifact_rows[1]["version"] == "2.32.0"
    assert artifact_rows[1]["requires_python"] == ">=3.9"
    assert artifact_rows[1]["yanked"] == 0
    assert artifact_rows[1]["yanked_reason"] is None
    assert json.loads(artifact_rows[1]["hashes_json"]) == {"sha256": "2222"}
    assert json.loads(artifact_rows[1]["core_metadata_json"]) == {"sha256": "3333"}
    assert artifact_rows[1]["provenance"].endswith("/provenance")

    source_row = store.connection.execute(
        """
        SELECT source, record_type, identity, serial
        FROM source_records
        WHERE source = ?
        """,
        ("pypi_simple_project_detail",),
    ).fetchone()
    assert source_row["record_type"] == "project_detail"
    assert source_row["identity"] == "requests"
    assert source_row["serial"] == 4321

    run_row = store.connection.execute(
        """
        SELECT records_seen, records_written
        FROM index_runs
        WHERE id = ?
        """,
        (run_id,),
    ).fetchone()
    assert run_row["records_seen"] == 1
    assert run_row["records_written"] == 1

    store.close()


def test_write_project_detail_batch_is_idempotent_for_detail_rows(tmp_path) -> None:
    db_path = tmp_path / "lib-finder.sqlite3"
    store = SQLiteStore.open(db_path)
    run_id = store.start_run(
        source="pypi_simple_project_detail",
        mode="detail",
        root_last_serial=None,
        settings={},
    )
    detail_payload = {
        "name": "sampleproject",
        "meta": {"_last-serial": 9876, "api-version": "1.4"},
        "project-status": "active",
        "versions": ["1.0.0"],
        "files": [
            {
                "filename": "sampleproject-1.0.0-py3-none-any.whl",
                "url": "https://files.pythonhosted.org/packages/example/sampleproject-1.0.0-py3-none-any.whl",
                "hashes": {"sha256": "aaaa"},
                "requires-python": ">=3.8",
                "size": 321,
                "upload-time": "2026-06-06T02:00:00Z",
                "yanked": False,
                "core-metadata": {"sha256": "bbbb"},
                "provenance": None,
            }
        ],
    }

    store.write_project_detail_batch(run_id=run_id, records=(detail_payload,))
    store.write_project_detail_batch(run_id=run_id, records=(detail_payload,))

    snapshot_count = store.connection.execute(
        "SELECT COUNT(*) FROM project_detail_snapshots WHERE normalized_name = ?",
        ("sampleproject",),
    ).fetchone()[0]
    version_count = store.connection.execute(
        "SELECT COUNT(*) FROM project_versions WHERE normalized_name = ?",
        ("sampleproject",),
    ).fetchone()[0]
    artifact_count = store.connection.execute(
        "SELECT COUNT(*) FROM project_artifacts WHERE normalized_name = ?",
        ("sampleproject",),
    ).fetchone()[0]
    assert snapshot_count == 1
    assert version_count == 1
    assert artifact_count == 1

    run_row = store.connection.execute(
        "SELECT records_seen, records_written FROM index_runs WHERE id = ?",
        (run_id,),
    ).fetchone()
    assert run_row["records_seen"] == 2
    assert run_row["records_written"] == 2

    store.close()
