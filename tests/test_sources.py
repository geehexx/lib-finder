from __future__ import annotations

from lib_finder.sources import models as source_models
from lib_finder.sources import factories as source_factories
from lib_finder.sources import client as source_client
from lib_finder.sources import constants as source_constants
from lib_finder.sources import parsing as source_parsing


def test_sources_models_expose_canonical_record_types() -> None:
    assert source_models.ProjectDiscoveryRecord.__module__ == (
        "lib_finder.sources.models"
    )
    assert source_models.ProjectSelectionRecord.__module__ == (
        "lib_finder.sources.models"
    )
    assert source_models.ProjectFileRecord.__module__ == "lib_finder.sources.models"
    assert source_models.ProjectDetailRecord.__module__ == "lib_finder.sources.models"


def test_sources_constants_are_canonical() -> None:
    assert source_constants.PYPI_SIMPLE_INDEX_URL == "https://pypi.org/simple/"
    assert source_constants.PYPI_SIMPLE_ACCEPT == "application/vnd.pypi.simple.v1+json"
    assert source_constants.DEFAULT_USER_AGENT.startswith("lib-finder/")


def test_sources_parsing_builders_are_canonical() -> None:
    assert source_parsing.build_project_discovery_record.__module__ == (
        "lib_finder.sources.parsing"
    )
    assert source_parsing.build_project_detail_record.__module__ == (
        "lib_finder.sources.parsing"
    )


def test_sources_client_helpers_are_canonical() -> None:
    assert source_client.iter_root_project_records.__module__ == (
        "lib_finder.sources.client"
    )
    assert source_client.iter_root_project_records_from_response.__module__ == (
        "lib_finder.sources.client"
    )
    assert source_client.fetch_project_detail_record.__module__ == (
        "lib_finder.sources.client"
    )


def test_sources_factories_are_canonical() -> None:
    assert source_factories.PyPIRecordFactory.__module__ == (
        "lib_finder.sources.factories"
    )
