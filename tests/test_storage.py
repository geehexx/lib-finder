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

    source_count = store.connection.execute("SELECT COUNT(*) FROM source_records").fetchone()[0]
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

    source_count = store.connection.execute("SELECT COUNT(*) FROM source_records").fetchone()[0]
    assert source_count == 1
    run_row = store.connection.execute(
        "SELECT records_seen, records_written FROM index_runs WHERE id = ?",
        (run_id,),
    ).fetchone()
    assert run_row["records_seen"] == 2
    assert run_row["records_written"] == 2

    store.close()
