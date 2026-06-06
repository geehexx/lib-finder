from __future__ import annotations

import langextract as lx

from lib_finder.extraction.models import ExtractionSourceDocument
from lib_finder.extraction.runner import run_text_extraction


def test_run_text_extraction_returns_empty_result_without_model() -> None:
    document = ExtractionSourceDocument(
        source_id="fixture:requests-readme",
        title="requests README",
        text="Requests supports Python >=3.9 and is actively maintained.",
    )

    result = run_text_extraction(document)

    assert result.source_document == document
    assert result.facts == ()
    assert result.model_id is None
    assert result.model_url is None


def test_run_text_extraction_maps_grounded_langextract_output(monkeypatch) -> None:
    document = ExtractionSourceDocument(
        source_id="fixture:requests-readme",
        title="requests README",
        text="Requests supports Python >=3.9 and is actively maintained.",
    )
    start_pos = document.text.index("Python >=3.9")
    end_pos = start_pos + len("Python >=3.9")
    annotated_document = lx.data.AnnotatedDocument(
        text=document.text,
        extractions=[
            lx.data.Extraction(
                extraction_class="supported_python",
                extraction_text="Python >=3.9",
                char_interval=lx.data.CharInterval(
                    start_pos=start_pos,
                    end_pos=end_pos,
                ),
                attributes={"package": "requests"},
            ),
            lx.data.Extraction(
                extraction_class="ungrounded",
                extraction_text="actively maintained",
                attributes={"package": "requests"},
            ),
        ],
    )

    def fake_extract(*args, **kwargs):
        return annotated_document

    monkeypatch.setattr("lib_finder.extraction.runner.lx.extract", fake_extract)

    result = run_text_extraction(
        document,
        model_id="gemma2:2b",
        model_url="http://localhost:11434",
    )

    assert result.model_id == "gemma2:2b"
    assert result.model_url == "http://localhost:11434"
    assert len(result.facts) == 1
    fact = result.facts[0]
    assert fact.fact_type == "supported_python"
    assert fact.value == "Python >=3.9"
    assert fact.source_spans[0].snippet == "Python >=3.9"
