"""Pydantic models for grounded extraction results."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ExtractionSpan(BaseModel):
    """A grounded snippet within a source document."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    start: int
    end: int
    snippet: str

    @model_validator(mode="after")
    def _validate_bounds(self) -> "ExtractionSpan":
        if self.start < 0:
            raise ValueError("span start must be non-negative")
        if self.end <= self.start:
            raise ValueError("span end must be greater than start")
        if not self.snippet:
            raise ValueError("span snippet must not be empty")
        return self


class ExtractionSourceDocument(BaseModel):
    """Normalized source text fed into the extraction pipeline."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_id: str
    title: str
    text: str
    uri: str | None = None

    @model_validator(mode="after")
    def _validate_text(self) -> "ExtractionSourceDocument":
        if not self.source_id.strip():
            raise ValueError("source_id must not be empty")
        if not self.title.strip():
            raise ValueError("title must not be empty")
        if not self.text.strip():
            raise ValueError("text must not be empty")
        return self


class ExtractedFact(BaseModel):
    """A grounded fact extracted from a source document."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    fact_type: str
    value: str
    source_document: ExtractionSourceDocument
    source_spans: tuple[ExtractionSpan, ...] = Field(default_factory=tuple)
    confidence: float | None = None

    @model_validator(mode="after")
    def _validate_grounding(self) -> "ExtractedFact":
        if not self.fact_type.strip():
            raise ValueError("fact_type must not be empty")
        if not self.value.strip():
            raise ValueError("value must not be empty")
        if not self.source_spans:
            raise ValueError("source_spans must not be empty")
        document_text = self.source_document.text
        for span in self.source_spans:
            if span.end > len(document_text):
                raise ValueError("span end exceeds source document length")
            if document_text[span.start : span.end] != span.snippet:
                raise ValueError("span snippet must match source document text")
        if self.confidence is not None and not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0.0 and 1.0")
        return self


class ExtractionRunResult(BaseModel):
    """Structured output from a local extraction run."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_document: ExtractionSourceDocument
    facts: tuple[ExtractedFact, ...] = Field(default_factory=tuple)
    model_id: str | None = None
    model_url: str | None = None
