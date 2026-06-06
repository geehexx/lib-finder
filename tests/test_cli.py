from __future__ import annotations

import runpy
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from lib_finder.cli import app


def test_default_command_builds_sync_config_and_echoes_csv_path(
    monkeypatch, tmp_path
) -> None:
    captured: dict[str, SimpleNamespace] = {}

    def fake_run_sync(config):
        captured["config"] = config
        return SimpleNamespace(
            records_written=12,
            csv_export_path=Path("snapshot.csv"),
        )

    monkeypatch.setattr("lib_finder.cli.run_sync", fake_run_sync)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "--database",
            str(tmp_path / "lib-finder.sqlite3"),
            "--csv-export",
            str(tmp_path / "snapshot.csv"),
            "--package-name",
            "Requests",
            "--package-name",
            "numpy",
            "--all-packages",
            "--queue-size",
            "3",
            "--batch-size",
            "4",
            "--request-timeout",
            "5.5",
            "--read-timeout",
            "6.5",
            "--detail-concurrency",
            "7",
            "--user-agent",
            "lib-finder-test/1.0",
            "--record-limit",
            "8",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "synced 12 records into" in result.output
    config = captured["config"]
    assert config.db_path == tmp_path / "lib-finder.sqlite3"
    assert config.csv_export_path == tmp_path / "snapshot.csv"
    assert config.package_names == ("Requests", "numpy")
    assert config.all_packages is True
    assert config.queue_size == 3
    assert config.batch_size == 4
    assert config.request_timeout == 5.5
    assert config.read_timeout == 6.5
    assert config.detail_concurrency == 7
    assert config.user_agent == "lib-finder-test/1.0"
    assert config.record_limit == 8


def test_default_command_uses_env_settings_when_cli_omits_overrides(
    monkeypatch, tmp_path
) -> None:
    captured: dict[str, SimpleNamespace] = {}

    def fake_run_sync(config):
        captured["config"] = config
        return SimpleNamespace(
            records_written=21,
            csv_export_path=config.csv_export_path,
        )

    monkeypatch.setattr("lib_finder.cli.run_sync", fake_run_sync)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [],
        env={
            "LIB_FINDER_DB_PATH": str(tmp_path / "env.sqlite3"),
            "LIB_FINDER_CSV_EXPORT_PATH": str(tmp_path / "env.csv"),
            "LIB_FINDER_PACKAGE_NAMES": '["Requests","numpy"]',
            "LIB_FINDER_ALL_PACKAGES": "true",
            "LIB_FINDER_QUEUE_SIZE": "13",
            "LIB_FINDER_BATCH_SIZE": "14",
            "LIB_FINDER_REQUEST_TIMEOUT": "15.5",
            "LIB_FINDER_READ_TIMEOUT": "16.5",
            "LIB_FINDER_DETAIL_CONCURRENCY": "17",
            "LIB_FINDER_USER_AGENT": "lib-finder-env/1.0",
            "LIB_FINDER_RECORD_LIMIT": "18",
        },
    )

    assert result.exit_code == 0, result.output
    assert "synced 21 records into" in result.output
    config = captured["config"]
    assert config.db_path == tmp_path / "env.sqlite3"
    assert config.csv_export_path == tmp_path / "env.csv"
    assert config.package_names == ("Requests", "numpy")
    assert config.all_packages is True
    assert config.queue_size == 13
    assert config.batch_size == 14
    assert config.request_timeout == 15.5
    assert config.read_timeout == 16.5
    assert config.detail_concurrency == 17
    assert config.user_agent == "lib-finder-env/1.0"
    assert config.record_limit == 18


def test_discover_and_qualify_commands_delegate_to_runners(
    monkeypatch, tmp_path
) -> None:
    captured: dict[str, SimpleNamespace] = {}

    def fake_discovery(config):
        captured["discover"] = config
        return SimpleNamespace(records_written=4, csv_export_path=None)

    def fake_qualification(config):
        captured["qualify"] = config
        return SimpleNamespace(records_written=2, qualified_count=1)

    monkeypatch.setattr("lib_finder.cli.run_discovery_sync", fake_discovery)
    monkeypatch.setattr("lib_finder.cli.run_qualification_sync", fake_qualification)

    runner = CliRunner()
    discover_result = runner.invoke(
        app,
        [
            "discover",
            "--database",
            str(tmp_path / "discover.sqlite3"),
            "--record-limit",
            "2",
        ],
    )
    qualify_result = runner.invoke(
        app,
        [
            "qualify",
            "--database",
            str(tmp_path / "qualify.sqlite3"),
            "--package-name",
            "Requests",
            "--package-name",
            "Flask",
            "--record-limit",
            "1",
        ],
    )

    assert discover_result.exit_code == 0, discover_result.output
    assert "synced 4 records into" in discover_result.output
    discover_config = captured["discover"]
    assert discover_config.db_path == tmp_path / "discover.sqlite3"
    assert discover_config.record_limit == 2

    assert qualify_result.exit_code == 0, qualify_result.output
    assert "refreshed 2 rollups" in qualify_result.output
    qualify_config = captured["qualify"]
    assert qualify_config.db_path == tmp_path / "qualify.sqlite3"
    assert qualify_config.package_names == ("Requests", "Flask")
    assert qualify_config.record_limit == 1


@pytest.mark.smoke
def test_module_entrypoint_works_via_python_m() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "lib_finder", "--help"],
        capture_output=True,
        text=True,
        check=True,
    )

    assert "Synchronize PyPI Simple metadata into SQLite." in result.stdout


def test_module_entrypoint_dispatches_to_cli_main(monkeypatch) -> None:
    calls: list[bool] = []

    def fake_main() -> None:
        calls.append(True)

    monkeypatch.setattr("lib_finder.cli.main", fake_main)
    runpy.run_module("lib_finder.__main__", run_name="__main__")

    assert calls == [True]
