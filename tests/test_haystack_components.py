from __future__ import annotations

import pytest
from haystack import Document

from lib_finder.pipeline.haystack_components import PackageDocumentNormalizer


@pytest.mark.unit
def test_package_document_normalizer_converts_a_record_to_a_document() -> None:
    component = PackageDocumentNormalizer(pipeline_stage="document")

    result = component.run(
        raw_name="Requests",
        normalized_name="requests",
        source="pypi_simple_root",
        record_type="project_discovery",
        content="Requests is a popular HTTP library.",
        meta={"root_last_serial": 123},
    )

    document = result["documents"][0]
    assert isinstance(document, Document)
    assert document.content == "Requests is a popular HTTP library."
    assert document.meta["raw_name"] == "Requests"
    assert document.meta["normalized_name"] == "requests"
    assert document.meta["source"] == "pypi_simple_root"
    assert document.meta["record_type"] == "project_discovery"
    assert document.meta["pipeline_stage"] == "document"
    assert document.meta["root_last_serial"] == 123


@pytest.mark.unit
def test_package_document_normalizer_rejects_blank_fields() -> None:
    component = PackageDocumentNormalizer()

    with pytest.raises(ValueError, match="must not be empty"):
        component.run(
            raw_name="",
            normalized_name="requests",
            source="pypi_simple_root",
            record_type="project_discovery",
            content="Requests is a popular HTTP library.",
        )
