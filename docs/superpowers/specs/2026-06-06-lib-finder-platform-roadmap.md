# lib-finder Platform Roadmap

Date: 2026-06-06
Purpose: capture the current long-term stack and quality-gate direction for lib-finder

## What Changed in the Research

The current implementation already has a working SQLite-backed PyPI Simple discovery core.

After reviewing the current repo and current library docs, the best near-term path is:

- keep the current `sqlite3` backend for the immediate ingestion work;
- avoid introducing SQLAlchemy ORM;
- consider SQLAlchemy Core later if the schema and query surface keep growing;
- shift test coverage toward recorded/live integration tests instead of heavy request mocking;
- use LangExtract with local Ollama later for long-document structured extraction;
- treat LlamaIndex/LlamaExtract as a separate option, but not the primary near-term extraction path.

## Storage Recommendation

### Keep for now

The current hand-rolled `sqlite3` layer is acceptable for the present shape of the project because:

- the repo is still early;
- the schema is small but evolving;
- the current code already has a single-writer ingestion path;
- the primary need right now is clear data modeling, not ORM abstraction.

### Revisit later

Introduce SQLAlchemy Core only if one or more of the following become true:

- the schema grows enough that manual DDL and upsert logic becomes repetitive;
- we need better composable query building for selection and reporting;
- migrations become painful enough that a Core metadata layer clearly reduces risk;
- we want a more portable backend strategy.

### Avoid for now

Do not migrate to SQLAlchemy ORM for ingestion storage. The ORM would add abstraction without much benefit for a batch ETL-style pipeline.

### If SQLAlchemy is introduced later

Use Core only:

- explicit tables and metadata;
- SQLite dialect upserts;
- batch `INSERT ... ON CONFLICT DO UPDATE`;
- transaction-scoped writes.

## Extraction / LLM Recommendation

### Near term

Do not block ingestion on LLM extraction infrastructure.

### Long term

Prefer LangExtract with local Ollama for structured extraction from long text artifacts because:

- current docs show explicit local Ollama support;
- it is designed for schema-based extraction;
- it is better aligned with local, reproducible workflows than a cloud-first extraction service;
- it fits the future need to extract facts from README/docs/release notes at scale.

### Keep separate

Treat LlamaIndex/LlamaExtract as an optional future branch, not the default path. It is service-oriented and better suited to a managed extraction platform than the current local-first roadmap.

## Testing Strategy

The current tests rely too much on pure mocks for HTTP and need to evolve.

### Testing pyramid

1. Property-based tests for pure normalization and persistence invariants.
2. Recorded HTTP integration tests for PyPI traffic using VCR-style cassettes.
3. Live smoke tests for the small number of endpoints that are cheap and stable.
4. End-to-end CLI tests over local SQLite, preferably using recorded network traffic.

### What to keep using mocks for

Use lightweight mocks for very small unit boundaries:

- pure parser helpers;
- deterministic serialization helpers;
- narrow error-path tests.

### What should move to recorded/live tests

Prefer recorded or live coverage for:

- PyPI root discovery;
- PyPI project-detail fetching;
- CLI-to-SQLite end-to-end flows;
- pagination/batch behavior;
- retry/resume behavior.

### Suggested tools

- `pytest-recording` + VCR.py for recorded HTTP tests;
- `pytest` markers for `live`, `recorded`, `smoke`, `property`, `slow`;
- `hypothesis` for invariants and round-trip checks;
- keep `respx` only where a tiny synthetic transport is the clearest unit test.

## Quality Gates

The repo should add a hook-driven quality gate stack:

- `ruff check`;
- `ruff format --check` or equivalent formatting gate;
- `pyright`;
- fast pytest tier by default;
- recorded/live smoke tier before merge;
- broader live suite on a pre-push or CI job.

## Hook Strategy

Use a single hook runner for the repo. Prefer `lefthook` because:

- it supports parallel jobs;
- it has straightforward config and local override support;
- it is a good fit for running format, lint, type-check, and test jobs in one place.

Suggested hook split:

- `pre-commit`: formatting, linting, type-checking, fast tests;
- `pre-push`: recorded/live smoke tests and broader integration tests.

## Near-Term Phases

### Phase 2

- finish project-detail fetching;
- persist detail snapshots, release rows, and artifact rows;
- select packages from SQLite by default;
- allow explicit package override for ad hoc runs.

### Phase 3

- adoption rollups;
- qualification features;
- ranking signals and staged scoring.

### Phase 4

- documentation / long-text ingestion;
- LangExtract + Ollama extraction pipeline;
- optional broader model-backed enrichment.

## Open Follow-Ups

- add a `lefthook.yml` once the hook job list is finalized;
- add pytest markers and test tiers;
- introduce `pytest-recording` and cassette storage for endpoint coverage;
- revisit SQLAlchemy Core only if the schema surface keeps expanding faster than the current sqlite3 layer can remain clear.
