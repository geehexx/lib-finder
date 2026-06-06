# ADR-0002: Haystack-Centered Pipelines

Status: Accepted

## Context

The project needs a pipeline layer that can separate ingestion, normalization,
document conversion, extraction, and downstream enrichment without turning the
CLI or storage layer into a monolith.

## Decision

Use Haystack as the orchestration layer for pipeline components once the source
and storage boundaries are stable enough to support it.

- Build pipeline stages as small typed components.
- Keep normalization and document conversion explicit instead of embedding them
  inside command handlers.
- Add fake/stub component tests before any local model integration.

## Consequences

- Pipeline stages become composable and easier to test in isolation.
- Runtime integration with models and retrieval systems stays behind explicit
  component boundaries.
- The project can add richer source and extraction paths without rewriting the
  orchestration layer.

