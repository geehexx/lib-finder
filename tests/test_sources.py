from __future__ import annotations

from lib_finder.sources import client as source_client
from lib_finder.sources import constants as source_constants
from lib_finder import pypi as root_pypi
from lib_finder.sources import parsing as source_parsing
from lib_finder.sources import models as source_models
from lib_finder.sources import pypi as source_pypi


def test_sources_models_match_root_record_types() -> None:
    assert source_models.ProjectDiscoveryRecord is root_pypi.ProjectDiscoveryRecord
    assert source_models.ProjectSelectionRecord is root_pypi.ProjectSelectionRecord
    assert source_models.ProjectFileRecord is root_pypi.ProjectFileRecord
    assert source_models.ProjectDetailRecord is root_pypi.ProjectDetailRecord


def test_sources_constants_match_root_constants() -> None:
    assert source_constants.PYPI_SIMPLE_INDEX_URL == root_pypi.PYPI_SIMPLE_INDEX_URL
    assert source_constants.PYPI_SIMPLE_ACCEPT == root_pypi.PYPI_SIMPLE_ACCEPT
    assert source_constants.DEFAULT_USER_AGENT == root_pypi.DEFAULT_USER_AGENT


def test_sources_parsing_reexports_root_builders() -> None:
    assert (
        source_parsing.build_project_discovery_record
        is root_pypi.build_project_discovery_record
    )
    assert (
        source_parsing.build_project_detail_record
        is root_pypi.build_project_detail_record
    )


def test_sources_client_reexports_root_http_helpers() -> None:
    assert (
        source_client.iter_root_project_records is root_pypi.iter_root_project_records
    )
    assert (
        source_client.iter_root_project_records_from_response
        is root_pypi.iter_root_project_records_from_response
    )
    assert (
        source_client.fetch_project_detail_record
        is root_pypi.fetch_project_detail_record
    )


def test_sources_pypi_reexports_root_parsers_and_constants() -> None:
    assert source_pypi.PYPI_SIMPLE_INDEX_URL == root_pypi.PYPI_SIMPLE_INDEX_URL
    assert source_pypi.PYPI_SIMPLE_ACCEPT == root_pypi.PYPI_SIMPLE_ACCEPT
    assert source_pypi.DEFAULT_USER_AGENT == root_pypi.DEFAULT_USER_AGENT
    assert source_pypi.ProjectDiscoveryRecord is root_pypi.ProjectDiscoveryRecord
    assert source_pypi.ProjectSelectionRecord is root_pypi.ProjectSelectionRecord
    assert source_pypi.ProjectFileRecord is root_pypi.ProjectFileRecord
    assert source_pypi.ProjectDetailRecord is root_pypi.ProjectDetailRecord
