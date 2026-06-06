"""Haystack pipeline factory for document normalization."""

from __future__ import annotations

from haystack import Pipeline

from .haystack_components import PackageDocumentNormalizer


def build_document_pipeline() -> Pipeline:
    """Build the canonical document-normalization pipeline."""

    pipeline = Pipeline()
    pipeline.add_component(
        "document_normalizer",
        PackageDocumentNormalizer(pipeline_stage="document"),
    )
    return pipeline
