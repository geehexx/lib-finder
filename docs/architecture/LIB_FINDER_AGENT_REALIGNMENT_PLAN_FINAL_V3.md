# lib-finder Agent Realignment Plan V3

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Realign `lib-finder` to the V3 architecture plan: SQLAlchemy Core storage, Haystack-centered pipelines, LangExtract/Ollama grounded extraction, ontology-backed evidence, and hybrid retrieval/evaluation infrastructure.

**Architecture:** Treat the V3 plan from Downloads as the controlling source of truth. First consolidate docs and archive contradictory specs, then clean import boundaries so the package root stays light. After that, migrate storage to SQLAlchemy Core + Alembic, split source/pipeline modules into typed boundaries, and then layer in Haystack, LangExtract, ontology, retrieval, and evaluation in bounded batches. The next refactor priority after the boundary splits is the source/parsing cleanup pass: reduce LBYL-heavy coercion paths, prefer EAFP where it makes failure clearer, and centralize repeated construction behind small factory/service objects before expanding the later domain layers.

**Operator policy:** Keep RTK as the agent-side wrapper for noisy local commands, but keep `uv run ...` as the canonical command surface in docs, CI, and examples. Recorded smoke tests that are unstable under xdist should be isolated into a serial lane rather than forcing every non-live run through the same parallel policy.

**Tech Stack:** Python 3.14, SQLAlchemy Core, Alembic, Haystack, LangExtract, Ollama, RDFLib, pySHACL, SQLite FTS5/BM25, BigQuery imports, pydantic, typer, pytest, ruff, pyright, interrogate, lefthook.

---

### Task 0: Consolidate docs and archive superseded specs

**Files:**
- Create: `docs/architecture/`
- Create: `docs/adr/`
- Create: `docs/archive/`
- Modify: `README.md`
- Create: `docs/testing/README.md`
- Modify archived copies in `docs/archive/`:
  - `docs/archive/2026-06-06-lib-finder-platform-roadmap.md`
  - `docs/archive/2026-06-06-lib-finder-quality-hygiene-plan.md`
  - `docs/archive/2026-06-06-lib-finder-phase4-extraction-design.md`
  - `docs/archive/2026-06-06-lib-finder-pydantic-standardization-plan.md`
  - `docs/archive/2026-06-06-lib-finder-phase4-runtime-and-gates.md`

- [x] Add ADRs for the new plan pillars:
  - `docs/adr/ADR-0001-sqlalchemy-core-storage.md`
  - `docs/adr/ADR-0002-haystack-core-pipelines.md`
  - `docs/adr/ADR-0003-langextract-grounded-facts.md`
  - `docs/adr/ADR-0004-ontology-skos-shacl.md`
  - `docs/adr/ADR-0005-bigquery-v0-metrics.md`

- [x] Mark older docs as superseded and move obsolete phase docs into `docs/archive/` with a short pointer back to this plan.

- [x] Update README to describe the V3 architecture planes, top-1,000 mode, and the new plan location.

- [x] Add a test-strategy README that separates unit, integration, property, live, smoke, benchmark, and architecture lanes, with a plan for replacing the temporary import-boundary probe.
- [x] Add repo-local RTK instructions so Codex sessions know when to prefer RTK wrappers for noisy commands while still documenting `uv run` as the canonical project command surface.

- [ ] Commit the documentation consolidation first.

### Task 1: Fix import boundaries and package root

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/lib_finder/__init__.py`
- Modify: `src/lib_finder/__main__.py`
- Modify: `src/lib_finder/cli.py`
- Create: `tests/test_import_boundaries.py`

- [x] Make `lib-finder` entry point point at a CLI function/module that does not import the whole package root.

- [x] Reduce `src/lib_finder/__init__.py` to minimal metadata only.

- [x] Add tests proving `import lib_finder`, `import lib_finder.storage`, and the canonical `lib_finder.sources` submodules do not import LangExtract/Haystack/Ollama.

- [x] Replace the ad hoc import-boundary probe with `import-linter` contracts once the package boundaries are stable, and keep the probe only as a temporary smoke guard.

- [ ] Commit after import boundaries are clean.

### Task 2: Split storage to SQLAlchemy Core + Alembic

**Files:**
- Create: `src/lib_finder/storage/`
- Create: `alembic.ini`
- Create: `src/lib_finder/storage/migrations/`
- Delete: `src/lib_finder/storage.py`
- Update: storage and pipeline tests

- [x] Introduce SQLAlchemy Core metadata, engine, and repository interfaces.
- [x] Add Alembic migration scaffolding and an initial migration.
- [x] Preserve WAL/foreign key/busy timeout semantics.
- [x] Delete the old monolithic storage module once the split is verified.

Status note: the storage package is now SQLAlchemy Core-backed, Alembic is the
bootstrap path for new and legacy SQLite files, and the monolithic
`storage.py` module has been replaced by `src/lib_finder/storage/`.

### Task 3: Split source ingestion and typed stage boundaries

**Files:**
- Create: `src/lib_finder/sources/`
- Create: `src/lib_finder/pipeline/`
- Legacy wrapper modules were removed during this tranche.

- [x] Move PyPI models/client/parser/normalizer into typed submodules.
- [x] Introduce source records and stage input/output records.
- [ ] Make the stage runner resumable and checkpointed.

Status note: `lib_finder.pipeline` is now a package split into config,
discovery, detail, and qualification modules while preserving the public import
surface. `lib_finder.sources` now has canonical `constants.py`,
`factories.py`, `parsing.py`, `status.py`, `client.py`, and `models.py`
modules, and the old wrapper modules have been removed. The typed record models
live in
`src/lib_finder/sources/models.py`.

### Task 4: Haystack pipeline skeleton

**Files:**
- Create: `src/lib_finder/pipeline/haystack_components.py`
- Create: `src/lib_finder/pipeline/discovery_pipeline.py`
- Create: `src/lib_finder/pipeline/detail_pipeline.py`
- Create: `src/lib_finder/pipeline/document_pipeline.py`

- [x] Implement Haystack components for normalization and document conversion.
- [x] Add fake/stub component tests before wiring any local model calls.

Status note: the Haystack skeleton is now implemented as deterministic
component and pipeline scaffolding in `src/lib_finder/pipeline/`. It converts
package records into Haystack `Document` objects without live model calls and
keeps the future LangExtract/Ollama wiring at a separate boundary.

### Task 5: LangExtract/Ollama grounded extraction

**Files:**
- Expand: `src/lib_finder/extraction/`
- Create: `tests/test_extraction_*.py` updates

- [ ] Broaden the fact schema.
- [ ] Add curated few-shot examples.
- [ ] Wrap LangExtract as a Haystack component.
- [ ] Add deterministic validators and persistence for validated facts.

### Task 6: Ontology, retrieval, scoring, and evaluation

**Files:**
- Create: `src/lib_finder/ontology/`
- Create: `src/lib_finder/retrieval/`
- Create: `src/lib_finder/scoring/`
- Create: `src/lib_finder/evaluation/`

- [ ] Add SKOS concept modeling and SHACL validation.
- [ ] Add FTS5/BM25 and hybrid retrieval.
- [ ] Add golden fixtures and evaluation reports.
- [ ] Add top-1,000 validation workflow before any full-index run.

### Task 7: Simplify construction, helpers, and local agent boundaries

**Files:**
- Review: `src/lib_finder/sources/`
- Review: `src/lib_finder/storage/`
- Review: `src/lib_finder/pipeline/`
- Review: `src/lib_finder/extraction/`
- Modify: `.gitignore`
- Modify: `docs/testing/README.md`
- Modify: `README.md`
- Modify: `RTK.md`

- [ ] Inventory repeated object construction and private-helper clusters in the core modules.
- [ ] Audit coercion-heavy code such as `src/lib_finder/sources/parsing.py` for EAFP-style simplification where try/except reduces branching and makes the failure mode clearer.
- [ ] Extract repeated record and validation construction into explicit factory/service objects whenever that removes coupling or flattens a nested helper cluster.
- [ ] Keep private helper functions only where they are true implementation details; prefer narrower, named interfaces for shared creation.
- [ ] Keep local Codex/agent artifacts outside the repo boundary and documented as private-only workspace material.
- [ ] Add benchmark and testmon opt-in lanes if they improve signal without slowing the default hooks.
- [ ] Update docs and hooks so the architectural simplification work stays visible in CI and local workflows.

Execution note: the first simplification tranche is tracked in
`docs/superpowers/plans/2026-06-07-lib-finder-source-factory-and-eafp-simplification.md`.
