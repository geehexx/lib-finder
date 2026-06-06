from __future__ import annotations

from pathlib import Path

from lib_finder.pipeline import (
    QualificationConfig,
    QualificationResult,
    SyncConfig,
    SyncResult,
)
from lib_finder.settings import LibFinderSettings


def test_lib_finder_settings_reads_prefixed_env(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("LIB_FINDER_DB_PATH", str(tmp_path / "env.sqlite3"))
    monkeypatch.setenv("LIB_FINDER_CSV_EXPORT_PATH", str(tmp_path / "snapshot.csv"))
    monkeypatch.setenv("LIB_FINDER_PACKAGE_NAMES", '["Requests","numpy"]')
    monkeypatch.setenv("LIB_FINDER_ALL_PACKAGES", "true")
    monkeypatch.setenv("LIB_FINDER_QUEUE_SIZE", "11")
    monkeypatch.setenv("LIB_FINDER_BATCH_SIZE", "12")
    monkeypatch.setenv("LIB_FINDER_REQUEST_TIMEOUT", "13.5")
    monkeypatch.setenv("LIB_FINDER_READ_TIMEOUT", "14.5")
    monkeypatch.setenv("LIB_FINDER_DETAIL_CONCURRENCY", "15")
    monkeypatch.setenv("LIB_FINDER_USER_AGENT", "lib-finder-env/1.0")
    monkeypatch.setenv("LIB_FINDER_RECORD_LIMIT", "16")
    monkeypatch.setenv("LIB_FINDER_EXTRACTION_MODEL_ID", "gemma2:2b")
    monkeypatch.setenv("LIB_FINDER_EXTRACTION_MODEL_URL", "http://localhost:11434")

    settings = LibFinderSettings()

    assert settings.db_path == tmp_path / "env.sqlite3"
    assert settings.csv_export_path == tmp_path / "snapshot.csv"
    assert settings.package_names == ("Requests", "numpy")
    assert settings.all_packages is True
    assert settings.queue_size == 11
    assert settings.batch_size == 12
    assert settings.request_timeout == 13.5
    assert settings.read_timeout == 14.5
    assert settings.detail_concurrency == 15
    assert settings.user_agent == "lib-finder-env/1.0"
    assert settings.record_limit == 16
    assert settings.extraction_model_id == "gemma2:2b"
    assert settings.extraction_model_url == "http://localhost:11434"


def test_pipeline_models_coerce_cross_boundary_values(tmp_path) -> None:
    sync_config = SyncConfig.model_validate(
        {
            "db_path": str(tmp_path / "sync.sqlite3"),
            "csv_export_path": str(tmp_path / "export.csv"),
            "package_names": ["Requests", "numpy"],
            "all_packages": True,
            "queue_size": "3",
            "batch_size": "4",
            "request_timeout": "5.5",
            "read_timeout": "6.5",
            "detail_concurrency": "7",
            "user_agent": "lib-finder-test/1.0",
            "record_limit": "8",
        }
    )
    qualification_config = QualificationConfig.model_validate(
        {
            "db_path": str(tmp_path / "qualification.sqlite3"),
            "package_names": ["Flask"],
            "record_limit": "9",
        }
    )
    sync_result = SyncResult.model_validate(
        {
            "run_id": "run-1",
            "records_seen": "10",
            "records_written": "11",
            "root_last_serial": "12",
            "csv_export_path": str(tmp_path / "result.csv"),
        }
    )
    qualification_result = QualificationResult.model_validate(
        {
            "run_id": "run-2",
            "records_seen": "13",
            "records_written": "14",
            "qualified_count": "15",
        }
    )

    assert sync_config.db_path == tmp_path / "sync.sqlite3"
    assert sync_config.csv_export_path == tmp_path / "export.csv"
    assert sync_config.package_names == ("Requests", "numpy")
    assert sync_config.queue_size == 3
    assert sync_config.batch_size == 4
    assert sync_config.request_timeout == 5.5
    assert sync_config.read_timeout == 6.5
    assert sync_config.detail_concurrency == 7
    assert sync_config.record_limit == 8
    assert sync_config.as_settings()["db_path"] == str(tmp_path / "sync.sqlite3")
    assert sync_config.as_settings()["package_names"] == ["Requests", "numpy"]

    assert qualification_config.db_path == tmp_path / "qualification.sqlite3"
    assert qualification_config.package_names == ("Flask",)
    assert qualification_config.as_settings()["db_path"] == str(
        tmp_path / "qualification.sqlite3"
    )

    assert sync_result.records_seen == 10
    assert sync_result.records_written == 11
    assert sync_result.root_last_serial == 12
    assert sync_result.csv_export_path == Path(tmp_path / "result.csv")

    assert qualification_result.records_seen == 13
    assert qualification_result.records_written == 14
    assert qualification_result.qualified_count == 15
