# lib-finder Quality and Hygiene Plan

> Superseded by [docs/architecture/LIB_FINDER_AGENT_REALIGNMENT_PLAN_FINAL_V3.md](/home/gxx/projects/lib-finder/docs/architecture/LIB_FINDER_AGENT_REALIGNMENT_PLAN_FINAL_V3.md) and archived in [`docs/archive/README.md`](/home/gxx/projects/lib-finder/docs/archive/README.md). Kept for historical context only.

Date: 2026-06-06
Scope: documentation quality, repository hygiene, and quality-gate hardening

## Goal

Make the repository easier to maintain and verify by turning documentation quality
and repository hygiene into explicit, testable conventions:

- update `README.md` into a durable operator guide, not just a launch snippet;
- keep the root `.gitignore` comprehensive and repo-specific;
- add a measurable documentation gate using `interrogate`;
- add branch coverage and complexity gates that fit the repo’s current Python stack;
- keep future work and library evaluation decisions documented in the roadmap.

## Current State

- phase 1 and phase 2 ingestion are implemented;
- quality gates already exist with `lefthook`, recorded HTTP tests, live smoke tests,
  `ruff`, `pyright`, `interrogate`, and branch coverage;
- the repository documentation is still thin outside the phase specs and roadmap;
- the legacy CSV wrapper has been removed in favor of direct CLI entry points;
- the root `.gitignore` is now comprehensive and keeps `uv.lock` tracked.
- the repo now also ships a thin `lib-finder extract` command backed by
  LangExtract and local Ollama, with a dedicated live smoke test.
- repo-local RTK guidance now exists for agent-side command compression, but it
  keeps `uv run ...` as the canonical documented invocation.

## Documentation Policy

### README

`README.md` should answer four questions quickly:

1. What does the project do?
2. What are the entry points and common commands?
3. What is the storage and execution model?
4. How do I verify changes locally?

It should also point readers to the phase specs and roadmap instead of duplicating
their contents.
Now that phase 4 has a runtime slice, it should also document the `extract`
command, the `LIB_FINDER_EXTRACTION_MODEL_ID` / `LIB_FINDER_EXTRACTION_MODEL_URL`
settings, and the live extraction smoke command.

### Code docs

Add docstrings to the public module, class, and function surfaces in `src/lib_finder`.

The intent is not verbose prose. Short, direct docstrings are enough as long as they
make the public API understandable without reading internals.

### Documentation gate

Use `interrogate` as the coverage gate for documentation completeness:

- count docstrings on the public `src/lib_finder` surface;
- ignore private helpers and nested implementation details;
- fail the repo when coverage falls below the configured threshold;
- keep the threshold high enough to matter, but low enough that it does not
  reward busywork.

Ruff remains the style and correctness gate for code quality; `interrogate` is the
coverage gate for documentation presence. Branch coverage and Ruff McCabe
complexity gates complement those checks for the implementation pipeline. Radon
and Xenon were researched as dedicated complexity tools, but the current stack
keeps Ruff as the single complexity gate because it is already enforced, local,
and low-friction for this codebase.

## Repository Hygiene Policy

- keep `uv.lock` tracked, not ignored;
- ignore generated caches, temporary files, build outputs, local databases, and
  virtual environments;
- preserve recorded cassettes and other intentional test fixtures;
- keep generated runtime data out of source control by default.

## Roadmap Decisions

- keep the current `sqlite3` backend for the present batch-ingestion shape;
- revisit SQLAlchemy Core only if the schema and query surface keep expanding;
- do not adopt SQLAlchemy ORM for this pipeline;
- standardize configuration and environment-variable loading on `pydantic`
  and `pydantic-settings`; the CLI-facing settings surface now uses this stack;
- keep resource wrappers as plain classes where they remain simpler than a model
  migration; the current `src/lib_finder` surface no longer uses dataclasses;
- keep LangExtract + local Ollama as the long-term extraction path;
- treat LlamaIndex/LlamaExtract as optional, not the default path.
- the first extraction runtime slice is intentionally thin and local-first; it
  should stay documented as a live Ollama-backed path rather than a cloud-first
  service dependency.

## Tests

The repo should continue to prefer:

1. unit tests for pure functions and tiny deterministic seams;
2. integration tests for local SQLite, recorded HTTP, and local service wiring;
3. property-based tests for pure invariants;
4. live smoke tests for cheap external checks;
5. local SQLite end-to-end tests for pipeline and rollup behavior;
6. benchmark tests that run outside the normal pass/fail gate.

Mocks stay acceptable only for tiny deterministic seams where they clarify the
behavior more than a recorded/live test would.

## Test Layout

Prefer markers and lane-specific directories over a single undifferentiated pile
of tests:

- `tests/test_*.py` remains acceptable during the transition;
- `unit`, `integration`, `property`, `smoke`, `live`, `recorded`, `e2e`, and
  `benchmark` markers define the intended selection lanes;
- `architecture` marks boundary and contract checks;
- future directory splits should keep those same marker semantics.

The first concrete architecture gate in this repo is the import-boundary probe.
The preferred replacement is `import-linter`, because it can express the same
forbidden-module claims as a reusable project rule rather than a bespoke test.
`pytest-archon` and similar pytest-native alternatives are useful to know about,
but they are secondary choices unless the team explicitly wants the boundary
rule encoded as a test only.

## Test Performance Policy

Use the cheapest gate that still proves the behavior under change:

- `pre-commit`: unit + architecture lanes only, with a short timeout;
- `pre-push`: all non-live deterministic tests except the temporary
  architecture probe, parallelized with `pytest-xdist` and grouped by file to
  maximize fixture reuse and reduce scheduling overhead;
- `tests/test_pypi_http.py` can stay in a fast recorded HTTP smoke lane with
  xdist;
- `tests/test_pipeline.py` should run as a dedicated serial smoke lane with a
  longer timeout because the SQLite-backed path is the bottleneck;
- the temporary import-boundary probe should stay in pre-commit only until
  `import-linter` takes over the contract gate;
- long replay tests should remain recorded, but they should be isolated from
  truly unit-level checks so the hot path stays fast;
- `pytest-timeout` should protect every broad lane from hangs;
- `pytest-testmon` is a candidate for local incremental reruns, but only as an
  opt-in dev workflow once the codebase stabilizes further.

## Acceptance Criteria

This plan is complete when:

- `README.md` reflects the actual operator workflow and verification steps;
- `.gitignore` is comprehensive and does not hide tracked lockfiles;
- `interrogate`, branch coverage, and complexity gates are configured and passing
  at the agreed thresholds;
- the import-boundary gate is either enforced by `import-linter` or explicitly
  documented as a transition probe with a removal plan;
- the phase-3 rollup path is implemented and tested;
- the roadmap documents the current library and tooling choices clearly;
- the test-lane README documents unit, integration, property, live, smoke,
  end-to-end, benchmark, and architecture checks;
- the mock-heavy discovery path has been replaced with recorded HTTP coverage;
- the extraction command and live Ollama smoke path are documented and verified.
