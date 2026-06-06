# ADR-0003: LangExtract Grounded Facts

Status: Accepted

## Context

The extraction layer needs to pull structured facts from long text while keeping
outputs grounded, testable, and compatible with local Ollama-backed inference.

## Decision

Use LangExtract for grounded fact extraction, with local Ollama as the default
long-form model backend when live extraction is enabled.

- Keep the extraction schema explicit and versioned.
- Prefer deterministic validators and persisted artifacts over ad hoc text
  parsing.
- Keep the live extraction path isolated behind opt-in smoke coverage.

## Consequences

- Extraction remains a bounded runtime slice rather than leaking into ingestion.
- The project can evaluate and iterate on fact schemas without changing the
  storage layer.
- Live model behavior remains optional and testable instead of being required
  for the core pipeline.

