# lib-finder Phase 1 Design

> Superseded by [docs/architecture/LIB_FINDER_AGENT_REALIGNMENT_PLAN_FINAL_V3.md](/home/gxx/projects/lib-finder/docs/architecture/LIB_FINDER_AGENT_REALIGNMENT_PLAN_FINAL_V3.md) and archived in [`docs/archive/README.md`](/home/gxx/projects/lib-finder/docs/archive/README.md). Kept for historical context only.

Date: 2026-06-06
Scope: PyPI Simple discovery core with SQLite persistence

## Goal

Build the first production-shaped ingestion path for `lib-finder`:

- stream the PyPI Simple JSON index without loading it into memory;
- normalize package names and compute suspicion features without filtering anything out;
- persist packages, source records, runs, and checkpoints in SQLite;
- support restart-safe reruns through idempotent upserts and run metadata;
- keep CSV as an optional debug/export artifact, not the canonical store.

This phase intentionally excludes project-detail fetching, release/artifact enrichment, download rollups, embeddings, and downstream recommendation logic.

## Current State

The repository currently contains:

- a placeholder CLI entry point in `src/lib_finder/__init__.py`;
- a prototype CSV-only sync script that streamed the PyPI Simple API into CSV;
- no tests yet;
- a minimal `pyproject.toml` with HTTPX, ijson, packaging, Typer, pytest, ruff, and respx available.

The old CSV-only prototype was not aligned with the target design because it assumed per-project `_last-serial` values in the root listing. The current PyPI JSON Simple API puts the project list serial on the response metadata, not on each project record.

## Design Principles

1. Do not destructively filter discovery records.
2. Keep network streaming and persistence separate.
3. Use a single SQLite writer with batched writes.
4. Make restarts safe by idempotent upserts and durable checkpoints.
5. Prefer standard library primitives where they are sufficient.

## Architecture

### Modules

- `src/lib_finder/pypi.py`
  - HTTPX streaming client for `GET /simple/`.
  - JSON Simple parsing with ijson.
  - Project discovery record construction.
  - Suspicion feature calculation.

- `src/lib_finder/storage.py`
  - SQLite connection setup.
  - Schema creation and migrations.
  - Run lifecycle recording.
  - Package/source record upserts.
  - Checkpoint persistence.

- `src/lib_finder/pipeline.py`
  - Bounded queue orchestration.
  - Producer/consumer coordination.
  - Optional CSV export.
  - Progress accounting and error handling.

- `src/lib_finder/cli.py`
  - CLI options for database path, CSV export, queue size, batch size, and request timeouts.
  - Default command that runs the phase-1 discovery sync.

### Data Flow

1. The producer issues `GET https://pypi.org/simple/` with `Accept: application/vnd.pypi.simple.v1+json`.
2. The response body is streamed through ijson and read project-by-project.
3. For each project:
   - normalize the project name using `packaging.utils.canonicalize_name`;
   - compute suspicion features;
   - build a discovery record;
   - enqueue the record.
4. The writer task dequeues records in batches and performs a single SQLite transaction per batch.
5. The writer updates:
   - `packages` with the latest observed discovery state;
   - `source_records` with immutable observation history;
   - `stage_checkpoints` with the latest durable progress;
   - `index_runs` with counts and final status.
6. If CSV export is enabled, the writer mirrors the same normalized records to a debug snapshot.

## Data Model

### `index_runs`

Tracks each sync execution:

- id
- source
- mode
- started_at
- finished_at
- status
- root_last_serial
- records_seen
- records_written
- error_count
- settings_json

### `packages`

Stores current package discovery state:

- normalized_name primary key
- raw_name
- first_seen_at
- last_seen_at
- root_last_serial
- project_last_serial nullable for later phases
- project_status nullable for later phases
- status_reason nullable for later phases
- suspicion_json
- qualification_state

### `source_records`

Immutable observation history:

- id primary key
- source
- record_type
- identity
- fetched_at
- etag nullable
- last_modified nullable
- serial nullable
- payload_hash
- raw_payload_json
- normalized_name nullable foreign key to `packages`

### `stage_checkpoints`

Stage-level durable progress:

- stage primary key
- checkpoint_json
- updated_at

### `failure_events`

Captures structured sync failures for later diagnosis:

- id primary key
- run_id
- stage
- identity nullable
- error_type
- error_message
- occurred_at
- retryable

## Discovery Record Shape

The discovery record stored in phase 1 should contain:

- `raw_name`
- `normalized_name`
- `root_last_serial`
- `fetched_at`
- `suspicion`
- `raw_payload`
- `payload_hash`

The root response metadata supplies the `root_last_serial`. The project entries themselves are expected to contain `name` only.

## Suspicion Features

The discovery pass should calculate features that help later qualification, but it must not drop records:

- package name length
- digit count and digit ratio
- separator count and separator ratio
- repeated separator detection
- mixed-case detection
- leading/trailing separator detection
- leading/trailing digit detection
- character diversity / entropy

These are stored as JSON for later ranking and analysis.

## Concurrency and Backpressure

Phase 1 uses:

- one HTTP producer
- one SQLite writer
- one bounded `asyncio.Queue`

Suggested defaults:

- queue size: 5,000
- batch size: 1,000
- write interval: flush at batch boundary or on completion

The writer controls disk pressure. The producer waits when the queue is full.

## Restart Semantics

Phase 1 does not depend on seeking into the PyPI root stream. Instead:

- each record is written idempotently;
- package rows are upserted;
- observation rows are keyed by a deterministic hash;
- checkpoints capture the latest durable state;
- rerunning the sync is safe and converges to the latest package state.

This is sufficient for restart safety in phase 1 and creates the foundation for more granular resumability later.

## CLI

The CLI should support:

- database path
- optional CSV export path
- queue size
- batch size
- request timeout / read timeout
- user-agent override
- optional record limit for smoke tests

The default entry point should still be useful with no extra configuration.

## Tests

Phase 1 must include tests for:

1. parsing and normalization of streamed root project lists;
2. suspicion feature generation;
3. SQLite schema initialization;
4. package/source record upserts and checkpoint persistence;
5. end-to-end sync against a mocked PyPI root response;
6. optional CSV export output.

## Non-Goals

Do not add in phase 1:

- project detail fetching
- release/artifact storage
- BigQuery or download rollups
- docs crawling
- embeddings
- advisory enrichment
- recommendation scoring

## Acceptance Criteria

Phase 1 is done when:

- `uv run pytest` passes for the phase-1 tests;
- the sync can ingest a mocked root response into SQLite;
- CSV remains optional and debug-only;
- the old root CSV-only behavior is removed from the primary path;
- the implementation matches the current PyPI JSON Simple API semantics.
