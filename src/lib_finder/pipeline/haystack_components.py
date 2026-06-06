"""Haystack components for deterministic package-document normalization."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from haystack import Document, component


def _require_non_empty(value: str, field_name: str) -> str:
    if not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    return value


@component
class PackageDocumentNormalizer:
    """Convert package records into Haystack documents."""

    def __init__(self, pipeline_stage: str = "document") -> None:
        self.pipeline_stage = _require_non_empty(pipeline_stage, "pipeline_stage")

    @component.output_types(documents=list[Document])
    def run(
        self,
        *,
        raw_name: str,
        normalized_name: str,
        source: str,
        record_type: str,
        content: str,
        meta: Mapping[str, Any] | None = None,
    ) -> dict[str, list[Document]]:
        """Return a single normalized Haystack document."""

        content = _require_non_empty(content, "content")
        metadata: dict[str, Any] = {}
        if meta is not None:
            metadata.update(meta)
        metadata.update(
            {
                "raw_name": _require_non_empty(raw_name, "raw_name"),
                "normalized_name": _require_non_empty(
                    normalized_name, "normalized_name"
                ),
                "source": _require_non_empty(source, "source"),
                "record_type": _require_non_empty(record_type, "record_type"),
                "pipeline_stage": self.pipeline_stage,
            }
        )
        return {"documents": [Document(content=content, meta=metadata)]}
