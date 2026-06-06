from __future__ import annotations

import pytest

from lib_finder.extraction.models import (
    ExtractedFact,
    ExtractionRunResult,
    ExtractionSourceDocument,
    ExtractionSpan,
)


def test_extraction_fact_requires_grounded_span() -> None:
    document = ExtractionSourceDocument(
        source_id="pypi:requests:README.md",
        title="requests README",
        text="hello world",
    )
    span = ExtractionSpan(start=0, end=5, snippet="hello")
    fact = ExtractedFact(
        fact_type="supported_python",
        value=">=3.9",
        source_document=document,
        source_spans=(span,),
    )

    assert fact.source_spans[0].snippet == "hello"
    assert fact.source_document.source_id == "pypi:requests:README.md"


def test_extraction_fact_rejects_mismatched_snippet() -> None:
    document = ExtractionSourceDocument(
        source_id="pypi:requests:README.md",
        title="requests README",
        text="hello world",
    )

    with pytest.raises(ValueError, match="snippet must match"):
        ExtractedFact(
            fact_type="supported_python",
            value=">=3.9",
            source_document=document,
            source_spans=(ExtractionSpan(start=0, end=5, snippet="HELLO"),),
        )


def test_extraction_run_result_serializes_empty_facts() -> None:
    document = ExtractionSourceDocument(
        source_id="pypi:requests:README.md",
        title="requests README",
        text="hello world",
    )
    result = ExtractionRunResult(source_document=document)

    assert result.model_dump(mode="json") == {
        "facts": [],
        "model_id": None,
        "model_url": None,
        "source_document": {
            "source_id": "pypi:requests:README.md",
            "text": "hello world",
            "title": "requests README",
            "uri": None,
        },
    }
