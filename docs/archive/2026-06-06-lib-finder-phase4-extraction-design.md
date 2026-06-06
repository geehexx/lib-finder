# lib-finder Phase 4 Design

> Superseded by [docs/architecture/LIB_FINDER_AGENT_REALIGNMENT_PLAN_FINAL_V3.md](/home/gxx/projects/lib-finder/docs/architecture/LIB_FINDER_AGENT_REALIGNMENT_PLAN_FINAL_V3.md) and archived in [`docs/archive/README.md`](/home/gxx/projects/lib-finder/docs/archive/README.md). Kept for historical context only.

Date: 2026-06-06
Scope: long-text extraction contract, grounding, and local LLM evaluation

## Goal

Define the contract for a future long-text extraction layer so `lib-finder` can
extract structured facts from package docs without guessing about the corpus,
schema, or model behavior.

The target outcome is not "add an LLM" in the abstract. The target is a repeatable
extraction pipeline with clear inputs, grounded outputs, and an evaluation surface
that can be run locally.

## Current State

The repository already has:

- SQLite-backed discovery, detail enrichment, and adoption rollups;
- recorded and live HTTP verification around PyPI;
- a quality gate stack with `lefthook`, `ruff`, `pyright`, `pytest`,
  `interrogate`, branch coverage, and Ruff McCabe complexity checks;
- a documented preference for LangExtract + local Ollama over a cloud-first
  extraction service;
- a thin local extraction runtime in `src/lib_finder/extraction/` and a
  `lib-finder extract` command that emits grounded JSON;
- a live Ollama smoke test that exercises the local extraction path.

The remaining phase-4 work is no longer to invent the runtime from scratch. The
current focus is to harden the extraction contract, broaden the grounded fact
schema, and expand the evaluation corpus without losing the current boundaries.

## Problem Statement

The current roadmap says "long-text ingestion" and "structured extraction," but
that is too broad to implement safely.

Before code exists, the project needs to answer:

1. What text sources are in scope?
2. What facts are we extracting from them?
3. What JSON shape do we expect back?
4. How do we ground the extracted output to source text?
5. How do we evaluate extraction quality locally and repeatably?

## Recommended Direction

### Primary path

Use LangExtract with a local Ollama model as the default extraction path.

Why:

- LangExtract is designed for grounded structured extraction from long documents;
- it supports local Ollama models, which keeps the workflow local and reproducible;
- Ollama supports structured outputs via JSON schema, which is a good fit for
  deterministic extraction contracts.

### Secondary path

Treat LlamaIndex / LlamaExtract as an optional future integration, not the default.
It remains a useful comparator, but it should not define the repository contract.

### Current runtime slice

The implementation now uses a thin repo-owned adapter:

- `src/lib_finder/extraction/models.py` owns the grounded Pydantic contracts;
- `src/lib_finder/extraction/prompts.py` owns the prompt text and example corpus;
- `src/lib_finder/extraction/runner.py` owns the LangExtract/Ollama boundary and
  converts grounded `AnnotatedDocument` output into repo models;
- `src/lib_finder/cli.py` exposes `lib-finder extract` for local runs.

## Extraction Contract

### In-scope sources

Start with text sources that are already present in package ecosystems and easy to
fetch:

- `README.md`
- release notes / changelog text
- project metadata summaries
- long-form package documentation pages

Do not start with arbitrary web crawling or notebook/document corpora.

### In-scope facts

The first extraction schema should stay narrow:

- package purpose / summary;
- installation and runtime prerequisites;
- supported Python versions;
- compatibility notes;
- deprecation / archival signals;
- maintainership signals;
- any explicit external service dependencies;
- licensing or distribution notes if clearly stated in the source.

### Output shape

The extraction output should be a small, validated JSON object with:

- the extracted field values;
- source spans or grounded references;
- confidence or uncertainty notes only when they are actually useful;
- a source identifier and provenance metadata.

The output must be schema-valid and replayable from the same text input.

### Grounding rules

Every extracted claim should point back to the source text range or source snippet
that justified it. If a claim cannot be grounded, it should not be silently promoted
to canonical data.

## Architecture

### Proposed modules later, not now

- `src/lib_finder/extraction/`
  - document loading and normalization;
  - source chunking / segmentation;
  - extraction schema and validation;
  - grounded output persistence;
  - evaluation helpers.

- `src/lib_finder/cli.py`
  - the current `extract` command; future `enrich-text` behavior can layer on top
    if the contract stays stable.

- `src/lib_finder/storage.py`
  - later tables for document sources, extractions, and evaluation runs.

## Model and Runtime Guidance

### Ollama

Prefer a local Ollama model with structured outputs:

- use a JSON schema for the expected result;
- keep prompts short and explicit;
- validate the decoded JSON before any persistence step;
- prefer deterministic settings and repeatable inputs for tests.
- document the local model and host via `LIB_FINDER_EXTRACTION_MODEL_ID` and
  `LIB_FINDER_EXTRACTION_MODEL_URL`;
- use a small local model for smoke tests, with the model id overrideable rather
  than hardcoded in the CLI.

### LangExtract

Use LangExtract as the orchestration layer for:

- chunking long documents;
- grounding extraction to source spans;
- running multi-pass or parallel extraction when a document is long enough to
  benefit from it;
- producing inspection-friendly outputs during development.

## Evaluation Strategy

Phase 4 should not ship without a local evaluation harness.

### Required evaluation layers

1. Gold-set fixtures for a small set of package texts with hand-validated facts.
2. Recorded extraction runs against frozen text fixtures.
3. Live smoke runs against a tiny set of stable package documents.
4. Regression checks for schema validity, grounding, and deterministic output shape.

### Metrics to track

- schema validity rate;
- grounded-claim rate;
- unsupported-claim rate;
- duplicate-claim rate;
- extraction recall on the gold set;
- extraction latency for representative documents.

## Testing Policy

Prefer tests in this order:

1. pure validation tests for schema and normalization helpers;
2. property-based tests for round-trip and invariants;
3. recorded extraction tests for stable text fixtures;
4. live smoke tests only for a tiny number of cheap targets.

Mocks should remain limited to tiny helper seams.

## Quality Gates And Pipeline

Phase 4 should extend the existing verification pipeline instead of inventing a
new one.

### Required gate tiers

1. `ruff format --check` and `ruff check`, including McCabe complexity limits.
2. `pyright` for type-checking the public and orchestration surfaces.
3. `interrogate` for public docstring coverage.
4. `pytest` with branch coverage for the package surface.
5. recorded and live smoke tests for the stable integration paths.

The current codebase already satisfies the first three tiers and the branch/
smoke tiers for the existing ingestion pipeline. The phase-4 extraction runtime
should keep those gates green while adding extraction-specific unit and live
checks.

### Tooling rules

- keep the hook runner in `lefthook`;
- prefer a single test command that exercises coverage on the non-live suite;
- keep live smoke checks small and explicit;
- do not introduce a second hook runner or a parallel quality-gate system.

### Research direction

When phase 4 implementation begins, evaluate whether the current Ruff complexity
threshold should be tightened further and whether any additional static gates
materially improve signal. Prefer gates that are:

- cheap to run locally;
- stable across Python 3.14+;
- easy to wire into `lefthook`;
- directly actionable when they fail.

## Non-Goals

Do not add in phase 4:

- a broad crawling subsystem;
- general-purpose web scraping;
- a full vector database;
- a cloud-first extraction dependency;
- an ORM migration;
- ungrounded free-form summarization.

## Acceptance Criteria

This phase is complete when:

- the extraction corpus and fact schema are explicitly defined;
- the extraction output is grounded and schema-valid by contract;
- the local model strategy is documented around Ollama;
- the evaluation plan is concrete enough to implement without reopening core
  design decisions;
- the current runtime slice remains small, local, and testable, with a live
  smoke test that exercises the Ollama-backed path.
