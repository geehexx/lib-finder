"""Local extraction helpers for `lib-finder`."""

from __future__ import annotations

import langextract as lx

from .models import (
    ExtractedFact,
    ExtractionRunResult,
    ExtractionSourceDocument,
    ExtractionSpan,
)
from .prompts import (
    build_package_extraction_examples,
    build_package_extraction_prompt,
)


def _build_empty_result(
    document: ExtractionSourceDocument,
    *,
    model_id: str | None = None,
    model_url: str | None = None,
) -> ExtractionRunResult:
    return ExtractionRunResult(
        source_document=document,
        facts=tuple(),
        model_id=model_id,
        model_url=model_url,
    )


def _annotated_document_to_result(
    document: ExtractionSourceDocument,
    annotated_document: lx.data.AnnotatedDocument,
    *,
    model_id: str | None,
    model_url: str | None,
) -> ExtractionRunResult:
    facts: list[ExtractedFact] = []
    annotated_text = annotated_document.text or document.text
    for extraction in annotated_document.extractions or []:
        char_interval = extraction.char_interval
        if char_interval is None:
            continue
        if char_interval.start_pos is None or char_interval.end_pos is None:
            continue
        snippet = annotated_text[char_interval.start_pos : char_interval.end_pos]
        if not snippet.strip():
            continue
        facts.append(
            ExtractedFact(
                fact_type=extraction.extraction_class,
                value=extraction.extraction_text,
                source_document=document,
                source_spans=(
                    ExtractionSpan(
                        start=char_interval.start_pos,
                        end=char_interval.end_pos,
                        snippet=snippet,
                    ),
                ),
            )
        )
    return ExtractionRunResult(
        source_document=document,
        facts=tuple(facts),
        model_id=model_id,
        model_url=model_url,
    )


def run_text_extraction(
    document: ExtractionSourceDocument,
    *,
    model_id: str | None = None,
    model_url: str | None = None,
) -> ExtractionRunResult:
    """Extract grounded package facts from a source document."""

    if model_id is None and model_url is None:
        return _build_empty_result(document)

    annotated_document = lx.extract(
        text_or_documents=document.text,
        prompt_description=build_package_extraction_prompt(),
        examples=list(build_package_extraction_examples()),
        model_id=model_id or "gemma2:2b",
        model_url=model_url or "http://localhost:11434",
        fence_output=False,
        use_schema_constraints=False,
        show_progress=False,
    )
    if isinstance(annotated_document, list):
        if not annotated_document:
            return _build_empty_result(document, model_id=model_id, model_url=model_url)
        annotated_document = annotated_document[0]
    return _annotated_document_to_result(
        document,
        annotated_document,
        model_id=model_id,
        model_url=model_url,
    )
