# ADR-0005: BigQuery V0 Metrics

Status: Accepted

## Context

The long-term platform needs a place to publish reproducible metrics and sample
evaluation results without coupling the local development loop to a heavy remote
warehouse workflow.

## Decision

Use a V0 BigQuery metrics path for exported evaluation and adoption summaries,
but keep the local repo focused on SQLite-backed development and validation.

- Publish metrics only after they are stable enough to justify external export.
- Keep the local evaluation loop self-contained and cheap to run.
- Treat BigQuery as a downstream reporting sink, not the primary working store.

## Consequences

- The repo can evolve metrics definitions locally before promoting them.
- External reporting stays optional and batch-oriented.
- The development workflow remains reproducible without requiring warehouse access.

