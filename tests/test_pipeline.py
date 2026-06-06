from __future__ import annotations

import asyncio
import json
import sqlite3

import httpx
import pytest
import respx

from lib_finder.pipeline import SyncConfig, run_discovery_sync, run_sync
from lib_finder.pypi import PYPI_SIMPLE_INDEX_URL, build_project_discovery_record
from lib_finder.storage import SQLiteStore


@pytest.mark.parametrize("csv_export", [None, "export.csv"])
@respx.mock
def test_run_discovery_sync_writes_sqlite_and_optional_csv(
    tmp_path, csv_export
) -> None:
    project_names = ["Requests", "numpy", "pandas"]
    root_payload = json.dumps(
        {
            "meta": {"_last-serial": 2468},
            "projects": [
                {"name": name, "_last-serial": index + 10}
                for index, name in enumerate(project_names)
            ],
        },
        separators=(",", ":"),
    ).encode("utf-8")
    respx.get(PYPI_SIMPLE_INDEX_URL).mock(
        return_value=httpx.Response(
            200,
            headers={"X-PyPI-Last-Serial": "2468"},
            content=root_payload,
        )
    )

    db_path = tmp_path / "lib-finder.sqlite3"
    csv_path = None if csv_export is None else tmp_path / csv_export
    result = asyncio.run(
        run_discovery_sync(
            SyncConfig(
                db_path=db_path,
                csv_export_path=csv_path,
                queue_size=2,
                batch_size=2,
                request_timeout=5.0,
                read_timeout=5.0,
                record_limit=None,
            )
        )
    )

    assert result.records_seen == 3
    assert result.records_written == 3
    assert result.root_last_serial == 2468
    assert db_path.exists()

    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        run_row = connection.execute(
            "SELECT status, root_last_serial, records_seen, records_written FROM index_runs ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        assert run_row["status"] == "completed"
        assert run_row["root_last_serial"] == 2468
        assert run_row["records_seen"] == 3
        assert run_row["records_written"] == 3

        packages = connection.execute(
            "SELECT normalized_name, raw_name FROM packages ORDER BY normalized_name"
        ).fetchall()
        assert [row["normalized_name"] for row in packages] == [
            "numpy",
            "pandas",
            "requests",
        ]
        source_count = connection.execute(
            "SELECT COUNT(*) FROM source_records"
        ).fetchone()[0]
        assert source_count == 3

    if csv_path is not None:
        csv_text = csv_path.read_text(encoding="utf-8").splitlines()
        assert (
            csv_text[0]
            == "raw_name,normalized_name,root_last_serial,fetched_at,payload_hash,suspicion_json"
        )
        assert len(csv_text) == 4


@respx.mock
def test_run_sync_selects_packages_from_sqlite_and_fetches_details(tmp_path) -> None:
    project_names = ["Requests", "numpy", "pandas", "Flask"]
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
        records=tuple(
            build_project_discovery_record(
                {"name": name},
                root_last_serial=2468,
                fetched_at="2026-06-06T00:00:00+00:00",
            )
            for name in project_names
        ),
    )
    store.close()

    name_to_index = {name.lower(): index for index, name in enumerate(project_names)}

    active_requests = 0
    max_active_requests = 0

    async def make_detail_response(request: httpx.Request) -> httpx.Response:
        nonlocal active_requests, max_active_requests
        active_requests += 1
        max_active_requests = max(max_active_requests, active_requests)
        try:
            await asyncio.sleep(0.05)
            normalized = request.url.path.rstrip("/").split("/")[-1]
            index = name_to_index[normalized]
            return httpx.Response(
                200,
                headers={"X-PyPI-Last-Serial": str(5000 + index)},
                content=json.dumps(
                    {
                        "name": normalized,
                        "meta": {"api-version": "1.4", "_last-serial": 5000 + index},
                        "versions": [f"1.0.{index}"],
                        "files": [
                            {
                                "filename": f"{normalized}-1.0.{index}.tar.gz",
                                "url": f"https://files.pythonhosted.org/{normalized}-{index}.tar.gz",
                                "hashes": {"sha256": f"sha-{index}"},
                                "size": 100 + index,
                                "upload-time": "2026-06-06T00:00:00Z",
                            }
                        ],
                    },
                    separators=(",", ":"),
                ).encode("utf-8"),
            )
        finally:
            active_requests -= 1

    for name in project_names:
        normalized = name.lower()
        respx.get(f"https://pypi.org/simple/{normalized}/").mock(
            side_effect=make_detail_response
        )

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

    assert result.records_written == 4
    assert result.root_last_serial is None
    assert max_active_requests <= 2

    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        package_rows = connection.execute(
            """
            SELECT normalized_name, project_last_serial, project_status, status_reason
            FROM packages
            ORDER BY normalized_name
            """
        ).fetchall()
        assert [row["normalized_name"] for row in package_rows] == [
            "flask",
            "numpy",
            "pandas",
            "requests",
        ]
        assert all(row["project_last_serial"] is not None for row in package_rows)

        detail_source_count = connection.execute(
            "SELECT COUNT(*) FROM source_records WHERE source = ?",
            ("pypi_simple_project_detail",),
        ).fetchone()[0]
        assert detail_source_count == 4
        snapshot_count = connection.execute(
            "SELECT COUNT(*) FROM project_detail_snapshots"
        ).fetchone()[0]
        artifact_count = connection.execute(
            "SELECT COUNT(*) FROM project_artifacts"
        ).fetchone()[0]
        version_count = connection.execute(
            "SELECT COUNT(*) FROM project_versions"
        ).fetchone()[0]
        assert snapshot_count == 4
        assert artifact_count == 4
        assert version_count == 4
