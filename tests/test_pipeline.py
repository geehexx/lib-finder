from __future__ import annotations

import json
import sqlite3

import httpx
import pytest
import respx

from lib_finder.pipeline import SyncConfig, run_sync
from lib_finder.pypi import PYPI_SIMPLE_INDEX_URL


@pytest.mark.parametrize("csv_export", [None, "export.csv"])
@respx.mock
def test_run_sync_writes_sqlite_and_optional_csv(tmp_path, csv_export) -> None:
    payload = json.dumps(
        {
            "meta": {"_last-serial": 2468},
            "projects": [
                {"name": "Requests"},
                {"name": "numpy"},
                {"name": "pandas"},
            ],
        },
        separators=(",", ":"),
    ).encode("utf-8")
    respx.get(PYPI_SIMPLE_INDEX_URL).mock(
        return_value=httpx.Response(
            200,
            headers={"X-PyPI-Last-Serial": "2468"},
            content=payload,
        )
    )

    db_path = tmp_path / "lib-finder.sqlite3"
    csv_path = None if csv_export is None else tmp_path / csv_export
    result = run_sync(
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
        assert [row["normalized_name"] for row in packages] == ["numpy", "pandas", "requests"]
        source_count = connection.execute("SELECT COUNT(*) FROM source_records").fetchone()[0]
        assert source_count == 3

    if csv_path is not None:
        csv_text = csv_path.read_text(encoding="utf-8").splitlines()
        assert csv_text[0] == "raw_name,normalized_name,root_last_serial,fetched_at,payload_hash,suspicion_json"
        assert len(csv_text) == 4
