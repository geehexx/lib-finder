"""Haystack pipeline factory for detail records."""

from __future__ import annotations

from haystack import Pipeline

from .haystack_components import PackageDocumentNormalizer


def build_detail_pipeline() -> Pipeline:
    """Build a deterministic detail-document pipeline."""

    pipeline = Pipeline()
    pipeline.add_component(
        "detail_document_normalizer",
        PackageDocumentNormalizer(pipeline_stage="detail"),
    )
    return pipeline
