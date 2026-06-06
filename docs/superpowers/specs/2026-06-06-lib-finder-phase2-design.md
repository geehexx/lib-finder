# lib-finder Phase 2 Design

Date: 2026-06-06
Scope: PyPI Simple project-detail ingestion, release rows, and artifact persistence

## Goal

Extend the phase-1 discovery core so `lib-finder` can fetch and persist project-detail data from the PyPI Simple project-detail endpoint:

- select packages to enrich from the SQLite discovery store by default;
- allow an explicit CLI override list for ad hoc runs;
- fetch `/simple/<project>/` with bounded concurrency;
- persist package status, project versions, release rows, and artifact rows;
- store raw detail payloads and source records for auditability;
- keep JSON API enrichment deferred to later phases.

## Current State

Phase 1 is already in place and verified:

- discovery streams the PyPI Simple root JSON;
- normalized package rows and source records are stored in SQLite;
- run metadata, checkpoints, and failure events are recorded;
- CSV exists only as an optional debug export.

The phase-1 implementation does not yet persist per-project detail pages, release/version rows, or artifact rows.

## API Facts That Constrain the Design

The current PyPI Simple project-detail response provides:

- `name`
- `versions`
- `files`
- `meta`
- optional `project-status` with `status` and `reason`

Each file entry can include:

- `filename`
- `url`
- `hashes`
- `requires-python`
- `dist-info-metadata` or `core-metadata`
- `upload-time`
- `size`
- `yanked`
- `provenance`

The phase-2 implementation must treat these as the source of truth for release and artifact metadata.

## Design Principles

1. Select work items from SQLite by default so the second phase naturally continues the first.
2. Keep the detail fetcher bounded and resumable at the batch level.
3. Store raw detail payloads for audit and replay.
4. Normalize file metadata into release/artifact rows instead of keeping it only in JSON blobs.
5. Support ad hoc CLI selection without making it the default path.

## Architecture

### Modules

- `src/lib_finder/pypi.py`
  - detail fetchers for `/simple/<project>/`;
  - parsing and normalization of project-detail payloads;
  - file metadata normalization;
  - filename-to-version derivation where possible.

- `src/lib_finder/storage.py`
  - schema extensions for project-detail snapshots, releases, and artifacts;
  - package status updates;
  - batch upserts for release and artifact records.

- `src/lib_finder/pipeline.py`
  - select package names from SQLite by default;
  - fetch details with bounded concurrency;
  - feed detail records to the SQLite writer.

- `src/lib_finder/cli.py`
  - CLI options for selecting package names from SQLite or an explicit override list;
  - concurrency controls for detail fetches;
  - optional limit for smoke tests.

## Data Model

### `project_details`

One row per fetched project-detail document:

- normalized_name primary key
- raw_name
- fetched_at
- root_last_serial
- project_last_serial
- project_status
- status_reason
- versions_json
- files_count
- payload_hash
- raw_payload_json

### `releases`

One row per observed project version:

- normalized_name
- version
- first_seen_at
- last_seen_at
- is_orderable

### `artifacts`

One row per observed file artifact:

- normalized_name
- filename
- version nullable if derivation fails
- url
- size_bytes
- upload_time
- requires_python
- yanked_json
- hashes_json
- core_metadata_json
- provenance_url
- first_seen_at
- last_seen_at

### Package updates

The `packages` table should be updated with:

- `project_last_serial`
- `project_status`
- `status_reason`

## Version Derivation

Artifact version derivation should use packaging’s filename parsers when possible:

- wheel filenames via `parse_wheel_filename`
- source distribution filenames via `parse_sdist_filename`

If version derivation fails for a file, the artifact row should still be persisted with a null version rather than dropped.

## Concurrency and Backpressure

Phase 2 should keep the same pattern as phase 1:

- bounded queue between fetchers and writer;
- bounded concurrent HTTP fetches;
- one SQLite writer;
- batch flush on size threshold or completion.

Suggested defaults:

- detail fetch concurrency: 8
- queue size: 5,000
- batch size: 500 or 1,000 depending on payload size

## Selection Policy

Default selection:

- read normalized names from the SQLite `packages` table;
- optionally filter to packages that have not yet been enriched in `project_details`.

Override selection:

- allow explicit package names on the CLI for ad hoc runs or smoke testing.

## Tests

Phase 2 must include tests for:

1. parsing project-detail payloads, including status and file metadata;
2. version derivation from wheel and sdist filenames;
3. SQLite persistence for `project_details`, `releases`, and `artifacts`;
4. selecting package names from SQLite by default;
5. fetching detail payloads through a mocked HTTP transport;
6. CLI override selection for explicit package names.

## Non-Goals

Do not add in phase 2:

- PyPI JSON API enrichment;
- download rollups;
- docs crawling;
- embeddings;
- advisory matching;
- recommendation scoring.

## Acceptance Criteria

Phase 2 is done when:

- detail payloads can be fetched for selected packages and stored in SQLite;
- package status fields are updated from the detail response;
- release and artifact rows are persisted with normalized metadata;
- the default selection path comes from SQLite;
- explicit package override works for ad hoc runs;
- the implementation is covered by focused tests and passes verification.
