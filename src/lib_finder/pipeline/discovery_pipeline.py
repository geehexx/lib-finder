"""Haystack pipeline factory for discovery records."""

from __future__ import annotations

from haystack import Pipeline

from .haystack_components import PackageDocumentNormalizer


def build_discovery_pipeline() -> Pipeline:
    """Build a deterministic discovery-document pipeline."""

    pipeline = Pipeline()
    pipeline.add_component(
        "discovery_document_normalizer",
        PackageDocumentNormalizer(pipeline_stage="discovery"),
    )
    return pipeline
