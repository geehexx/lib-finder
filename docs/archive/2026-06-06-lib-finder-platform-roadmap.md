# lib-finder Platform Roadmap

> Superseded by [docs/architecture/LIB_FINDER_AGENT_REALIGNMENT_PLAN_FINAL_V3.md](/home/gxx/projects/lib-finder/docs/architecture/LIB_FINDER_AGENT_REALIGNMENT_PLAN_FINAL_V3.md) and archived in [`docs/archive/README.md`](/home/gxx/projects/lib-finder/docs/archive/README.md). Kept for historical context only.

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
- keep RTK as an agent-side output filter for noisy command sessions, while
  leaving `uv run ...` as the canonical command surface in docs and CI.

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

## Configuration and Model Standardization

The repo now uses `pydantic-settings` for the shared `LIB_FINDER_` settings
surface and `pydantic.BaseModel` for the CLI-facing sync/qualification configs,
PyPI record models, and storage batch results. The remaining resource wrapper is
the SQLite store class. The `src/lib_finder` package no longer uses dataclasses.
The long-term direction should still be more deliberate:

- keep environment-variable loading centralized in the settings model instead of
  ad hoc `os.environ` access;
- use `pydantic.BaseModel` for configuration and schema-bearing objects that need
  validation, serialization, or a stable JSON contract;
- keep resource wrappers as plain classes when they are not natural data models;
- migrate any future outward-facing record contracts before converting every
  internal helper type.

The migration remains incremental, not a blanket "replace every dataclass"
rewrite. Prioritize the remaining boundary-facing record models that are
exchanged across module boundaries.

The detailed migration contract lives in
[pydantic standardization plan](docs/archive/2026-06-06-lib-finder-pydantic-standardization-plan.md).

## Extraction / LLM Recommendation

### Near term

Do not block ingestion on LLM extraction infrastructure. The first runtime slice
now exists, but it remains optional and local-first.

### Long term

Prefer LangExtract with local Ollama for structured extraction from long text artifacts because:

- current docs show explicit local Ollama support;
- it is designed for schema-based extraction;
- it is better aligned with local, reproducible workflows than a cloud-first extraction service;
- it fits the future need to extract facts from README/docs/release notes at scale.

### Keep separate

Treat LlamaIndex/LlamaExtract as an optional future branch, not the default path. It is service-oriented and better suited to a managed extraction platform than the current local-first roadmap.

### Current runtime slice

The current codebase now ships a thin `lib-finder extract` command backed by
LangExtract and a local Ollama model. The adapter stays intentionally small:

- Pydantic models own the grounded contract;
- prompts and examples live in the extraction package;
- the runner filters grounded spans into repo-owned output models;
- the live smoke test uses a small local model and stays behind
  `LIB_FINDER_LIVE=1`.

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
- `interrogate`;
- branch coverage on the package surface;
- Ruff McCabe complexity limits;
- fast pytest tier by default;
- recorded/live smoke tier before merge, but with a separate serial lane if a
  smoke test proves xdist-unsafe;
- broader live suite on a pre-push or CI job.

The current implementation already enforces the core gate set through `lefthook`,
branch coverage, and recorded smoke tests. Radon/Xenon were researched as
dedicated complexity tools, but Ruff complexity remains the chosen hard gate for
now because it is already wired in and does not add another duplicate policy
surface.

## Documentation Quality

The repository should treat code documentation as a measurable gate, not an
afterthought:

- keep `README.md` focused on operator workflow, verification, and entry points;
- require public module/class/function docstrings for the `src/lib_finder` surface;
- use `interrogate` to track docstring coverage and fail when the threshold drops;
- keep branch coverage and complexity gates alongside docstring coverage so the
  testing and development pipeline stays aligned;
- keep the current roadmap and phase specs as the deeper design record instead of
  overloading the README.

## Hook Strategy

Use a single hook runner for the repo. Prefer `lefthook` because:

- it supports parallel jobs;
- it has straightforward config and local override support;
- it is a good fit for running format, lint, type-check, and test jobs in one place.

Suggested hook split:

- `pre-commit`: formatting, linting, type-checking, fast tests, and the
  temporary architecture probe;
- `pre-push`: parallel non-live deterministic tests, excluding the temporary
  architecture probe, then a fast recorded HTTP smoke lane and a dedicated
  serial pipeline smoke lane for the SQLite-backed path that is too slow or
  flaky under xdist.

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

- documentation / long-text ingestion and the current extraction runtime;
- LangExtract + Ollama extraction pipeline;
- optional broader model-backed enrichment;
- quality-gate hardening across documentation, coverage, and complexity checks;
- maintain the recorded/live testing shift by converting the remaining mock-heavy
  API paths to replayable HTTP coverage when practical.

Phase 4 is currently defined in more detail in
[phase 4 extraction design](docs/archive/2026-06-06-lib-finder-phase4-extraction-design.md).
That spec should remain the source of truth before any runtime extraction code is added.

## Open Follow-Ups

- tighten the Ruff complexity ceiling only if the current threshold stops being useful;
- revisit SQLAlchemy Core only if the schema surface keeps expanding faster than the current sqlite3 layer can remain clear;
- expand phase 4 evaluation fixtures once a real extraction corpus exists;
- revisit complexity tooling only if Ruff’s McCabe limit stops giving enough signal.
