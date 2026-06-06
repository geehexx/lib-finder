from __future__ import annotations

import pytest

from lib_finder.config import build_qualification_config, build_sync_config
from lib_finder.settings import LibFinderSettings


@pytest.mark.unit
def test_build_sync_config_prefers_cli_overrides(tmp_path) -> None:
    settings = LibFinderSettings(
        db_path=tmp_path / "env.sqlite3",
        csv_export_path=tmp_path / "env.csv",
        package_names=("Requests",),
        all_packages=True,
        queue_size=11,
        batch_size=12,
        request_timeout=13.5,
        read_timeout=14.5,
        detail_concurrency=15,
        user_agent="env-agent/1.0",
        record_limit=16,
    )

    config = build_sync_config(
        settings,
        db_path=tmp_path / "cli.sqlite3",
        csv_export_path=tmp_path / "cli.csv",
        package_names=("numpy", "flask"),
        all_packages=False,
        queue_size=21,
        batch_size=22,
        request_timeout=23.5,
        read_timeout=24.5,
        detail_concurrency=25,
        user_agent="cli-agent/1.0",
        record_limit=26,
    )

    assert config.db_path == tmp_path / "cli.sqlite3"
    assert config.csv_export_path == tmp_path / "cli.csv"
    assert config.package_names == ("numpy", "flask")
    assert config.all_packages is False
    assert config.queue_size == 21
    assert config.batch_size == 22
    assert config.request_timeout == 23.5
    assert config.read_timeout == 24.5
    assert config.detail_concurrency == 25
    assert config.user_agent == "cli-agent/1.0"
    assert config.record_limit == 26


@pytest.mark.unit
def test_build_qualification_config_uses_env_defaults(tmp_path) -> None:
    settings = LibFinderSettings(
        db_path=tmp_path / "env.sqlite3",
        package_names=("Requests", "Flask"),
        record_limit=7,
    )

    config = build_qualification_config(settings)

    assert config.db_path == tmp_path / "env.sqlite3"
    assert config.package_names == ("Requests", "Flask")
    assert config.record_limit == 7
