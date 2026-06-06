# lib-finder Phase 3 Design

> Superseded by [docs/architecture/LIB_FINDER_AGENT_REALIGNMENT_PLAN_FINAL_V3.md](/home/gxx/projects/lib-finder/docs/architecture/LIB_FINDER_AGENT_REALIGNMENT_PLAN_FINAL_V3.md) and archived in [`docs/archive/README.md`](/home/gxx/projects/lib-finder/docs/archive/README.md). Kept for historical context only.

Date: 2026-06-06
Scope: adoption rollups, qualification state, and ranking signals

## Goal

Extend the phase-2 detail store so `lib-finder` can summarize package adoption and convert those summaries into explicit qualification signals:

- persist a compact adoption rollup per package;
- compute a stable qualification state and reason from observable release/artifact data;
- keep the qualification state on the `packages` table current;
- expose a CLI backfill path so rollups can be recomputed from SQLite alone;
- keep ranking signals simple enough to explain and test.

## Current State

Phase 2 is already in place and verified:

- root discovery and project-detail ingestion both work;
- SQLite stores discovery rows, detail snapshots, versions, artifacts, and source audit rows;
- the default CLI enriches from SQLite and `discover` remains available for root sync;
- quality gates now include lefthook, strict markers, recorded HTTP coverage,
  branch coverage, complexity checks, and live smoke coverage.

The current schema already has a `qualification_state` column on `packages`, but it is not yet driven by adoption data.

## Design Principles

1. Keep the rollup model explicit and compact, not a hidden scoring side effect.
2. Use the data already persisted in SQLite as the sole source of truth.
3. Make qualification explainable in the database, not just in code.
4. Prefer one current rollup row per package over a historical explosion of summaries.
5. Keep scoring deterministic and simple enough to test with fixtures.

## Architecture

### Modules

- `src/lib_finder/storage.py`
  - adoption rollup table and schema migration for `packages.qualification_reason`;
  - package summary computation;
  - qualification-state updates.

- `src/lib_finder/pipeline.py`
  - optional CLI-facing backfill for recomputing rollups from SQLite.

- `src/lib_finder/cli.py`
  - new `qualify` command for rollup backfills and manual recomputation.

## Data Model

### `package_adoption_rollups`

One row per package, representing the current computed adoption summary:

- `normalized_name` primary key
- `raw_name`
- `version_count`
- `artifact_count`
- `wheel_count`
- `sdist_count`
- `yanked_artifact_count`
- `latest_upload_time`
- `latest_project_last_serial`
- `project_status`
- `qualification_score`
- `qualification_state`
- `qualification_reason`
- `computed_at`

### `packages` updates

The `packages` table should continue to hold the current coarse qualification state, and gain a reason field:

- `qualification_state`
- `qualification_reason`

## Qualification Model

Use a deterministic staged score with a small set of explainable thresholds.

### Base signals

- start with `version_count`, `artifact_count`, `wheel_count`, and `sdist_count`;
- subtract for yanked artifacts;
- bump the score for having both wheels and sdists;
- zero out qualification if the project status is explicitly disqualifying.

### States

- `discovered`: no meaningful adoption data yet;
- `candidate`: some package structure exists, but the score is still below the qualified threshold;
- `qualified`: the package has enough versions/artifacts and the score clears the threshold;
- `excluded`: the project status or artifact state is explicitly disqualifying.

### Reason strings

Reason strings should be short, deterministic, and machine-readable enough to inspect in SQL:

- `score=42; versions=3; artifacts=5; status=active`
- `excluded: project_status=deprecated`

## Backfill Behavior

### Default selection

- recompute rollups for all packages that have been discovered or enriched;
- allow an explicit package-name override for ad hoc backfills;
- keep the command idempotent.

### When rollups update

- after a detail batch is written, refresh rollups for the packages touched by that batch;
- the explicit CLI backfill remains available for historical recomputation.

## Tests

Phase 3 must include tests for:

1. rollup computation from existing versions and artifacts;
2. qualification-state transitions from the rollup score and project status;
3. persistence of `package_adoption_rollups` rows;
4. updates to `packages.qualification_state` and `packages.qualification_reason`;
5. CLI backfill behavior over SQLite data;
6. idempotence of repeated rollup recomputation.

## Non-Goals

Do not add in phase 3:

- SQLAlchemy migration;
- embeddings or document extraction;
- external ranking models;
- recommendation scoring across multiple signals;
- LLM-backed classification.

## Acceptance Criteria

Phase 3 is done when:

- adoption rollups are persisted per package;
- qualification state and reason are updated from rollup data;
- the state is recomputable from SQLite alone;
- the implementation is covered by focused tests and passes verification.
