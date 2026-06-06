from __future__ import annotations

import os

import pytest

from lib_finder.extraction.models import ExtractionSourceDocument
from lib_finder.extraction.runner import run_text_extraction


@pytest.mark.live
@pytest.mark.smoke
def test_live_extraction_smoke_uses_local_ollama() -> None:
    if os.getenv("LIB_FINDER_LIVE") != "1":
        pytest.skip("live extraction requires LIB_FINDER_LIVE=1")

    document = ExtractionSourceDocument(
        source_id="fixture:requests-readme",
        title="requests README",
        text="Requests supports Python >=3.9 and is actively maintained.",
    )
    result = run_text_extraction(
        document,
        model_id=os.getenv("LIB_FINDER_EXTRACTION_MODEL_ID", "qwen3.5:0.8b"),
        model_url=os.getenv(
            "LIB_FINDER_EXTRACTION_MODEL_URL", "http://localhost:11434"
        ),
    )

    assert result.source_document == document
    assert {fact.fact_type for fact in result.facts} >= {
        "supported_python",
        "maintainership",
    }
    assert all(fact.source_spans for fact in result.facts)
