from __future__ import annotations

import pytest

from lib_finder.pipeline.discovery_pipeline import build_discovery_pipeline
from lib_finder.pipeline.detail_pipeline import build_detail_pipeline
from lib_finder.pipeline.document_pipeline import build_document_pipeline


@pytest.mark.unit
@pytest.mark.parametrize(
    ("factory", "component_name", "pipeline_stage"),
    [
        (build_document_pipeline, "document_normalizer", "document"),
        (build_discovery_pipeline, "discovery_document_normalizer", "discovery"),
        (build_detail_pipeline, "detail_document_normalizer", "detail"),
    ],
)
def test_haystack_pipeline_factories_return_stage_specific_documents(
    factory,
    component_name: str,
    pipeline_stage: str,
) -> None:
    pipeline = factory()

    result = pipeline.run(
        {
            component_name: {
                "raw_name": "Requests",
                "normalized_name": "requests",
                "source": "pypi_simple_root",
                "record_type": "project_discovery",
                "content": "Requests is a popular HTTP library.",
                "meta": {},
            }
        }
    )

    document = result[component_name]["documents"][0]
    assert document.meta["normalized_name"] == "requests"
    assert document.meta["pipeline_stage"] == pipeline_stage
