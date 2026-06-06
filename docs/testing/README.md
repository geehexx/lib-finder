# Testing Strategy

This repository uses explicit test lanes so the suite can grow without mixing
concerns or turning every test run into a full-system exercise.

The controlling architecture plan is
[docs/architecture/LIB_FINDER_AGENT_REALIGNMENT_PLAN_FINAL_V3.md](../architecture/LIB_FINDER_AGENT_REALIGNMENT_PLAN_FINAL_V3.md).
Older phase specs live in [docs/archive/README.md](../archive/README.md) and are
not the source of truth anymore.

## Lanes

- `unit`: fast, deterministic checks for pure functions and small boundary logic.
- `integration`: tests that exercise real SQLite, recorded HTTP, or local services.
- `e2e`: tests that traverse multiple layers of the application in one flow.
- `smoke`: short end-to-end checks that confirm the main path still works.
- `live`: tests that require live external services and are gated by opt-in env vars.
- `recorded` and `vcr`: replayed HTTP tests for stable external API behavior.
- `property`: Hypothesis-based invariant tests.
- `haystack`: deterministic Haystack skeleton checks; these currently run as
  part of the `unit` lane rather than a separate hook lane.
- `benchmark`: performance checks that should run separately from normal CI gates.
- `architecture`: import boundary and module-contract checks.

## Current Layout

The suite is still mostly flat, but the marker taxonomy is already in place.
That means the repository can move tests into subdirectories later without
changing how they are selected.

## Selection

Run the smallest useful lane first, then widen only when the behavior being
checked crosses a boundary.

```bash
uv run pytest -m unit
uv run pytest -m integration
uv run pytest -m property
uv run pytest -m smoke
LIB_FINDER_LIVE=1 uv run pytest -m live
uv run pytest -m architecture
```

Agent sessions may route the same commands through `rtk` to compact verbose
output, but the canonical examples stay on plain `uv run`. For Python tooling,
prefer `uv run rtk pytest ...` and `uv run rtk ruff ...` so the wrapper runs
inside the project environment. Avoid bare `rtk pytest ...` here; the wrapper
is only reliable for project Python tools when it is launched under `uv run`.

## Benchmark Policy

Benchmarks are not part of the normal pass/fail gate.

- keep benchmark tests isolated with `@pytest.mark.benchmark`;
- avoid mixing benchmark assertions with correctness assertions;
- record performance changes separately from functional regressions;
- only compare benchmark history when the code path is stable enough to be meaningful.

## Local Acceleration

The default acceleration strategy is xdist plus file-level batching:

- use `-n auto --dist=loadfile` for broad non-live runs;
- keep session-scoped fixtures isolated or file-local when they are expensive;
- use `pytest-timeout` to terminate hung subprocess or HTTP replay tests;
- keep the broad deterministic lane behind `pre-push`, not `pre-commit`;
- run `tests/test_pypi_http.py` in the smoke lane with xdist when it stays fast;
- run the CLI module-entrypoint subprocess check as its own smoke lane because
  it is the slowest remaining test and does not benefit from xdist;
- run `tests/test_pipeline.py` as its own serial smoke lane when the SQLite
  pipeline path is the bottleneck.
- keep the Haystack skeleton tests in the fast unit lane because they are
  deterministic component/pipeline checks with no live model calls.
- keep `architecture` checks in the pre-commit lane until `import-linter`
  replaces the temporary probe; they do not need to run in the broad push lane
  once the import boundary contract is stable.

Optional incremental selection:

- `pytest-testmon` is a good fit for local edit/run loops when the test graph is
  stable enough to benefit from coverage-based test selection;
- it is not wired into hooks yet because it adds state and is more brittle during
  large refactors;
- if adopted later, it should live as an opt-in local command rather than the
  primary CI gate.

## Profiling Notes

Use timings to guide lane design and code changes instead of guessing.

- `uv run pytest tests/test_pipeline.py -q --durations=10 --maxfail=1` now
  shows the SQLite-backed smoke path completes in a few seconds.
- `uv run pytest -q -m "not live and not smoke" -n auto --dist=loadfile --durations=10 --maxfail=1`
  is the broad deterministic lane and currently completes in the mid-teens of
  seconds on this machine.
- `uv run pytest tests/test_cli.py -m smoke --timeout=60 --maxfail=1` is the
  CLI smoke lane and isolates the subprocess module-entrypoint check.
- if the pipeline lane slows down again, profile that file first before widening
  the hook or adding more mocking; the biggest regressions have come from
  unnecessary executor offloading around SQLite writes.
- the broad coverage lane relies on the exact pytest-cov sqlite warning filter
  string (`unclosed database in <sqlite3.Connection object at`) documented by
  pytest-cov; keep that message text aligned with upstream if it changes.

When refactoring parsing or construction code, keep the smallest possible
unit/edge tests around the branch that is being flattened. That usually means:

- add or update one or two focused unit tests before changing the coercion path;
- keep a companion edge test for the exceptional branch you are simplifying;
- prefer a tiny factory/service object over an extra layer of private helpers if
  the new boundary makes the tests easier to read and maintain.
- the same rule now applies to storage row preparation in
  `src/lib_finder/storage/factories.py`, where the persistence layer should
  stay focused on writes and transactions rather than data shaping.
- `SQLiteStore.get_stage_checkpoint()` exposes the last durable stage checkpoint
  when you need to inspect restart state during a debugging session.
- the detail and qualification runners resume from the last recorded
  `normalized_name` checkpoint when no explicit package override is supplied;
  discovery remains restart-safe through idempotent writes instead of stream
  rewinding.

## RTK Policy

RTK is the agent-side wrapper for reducing command noise in long sessions.

- prefer `uv run rtk pytest` and `uv run rtk ruff` for Python tools, plus plain
  `rtk git`, `rtk summary`, `rtk read`, and `rtk find` for non-Python tools;
- keep the documentation examples on plain `uv run ...` so the repo commands
  remain copy-pastable outside the agent loop;
- use `rtk hook check git status` and `rtk gain` when checking the local
  operator setup.

## Import Boundary Policy

The current import-boundary gate is contract-based, with `import-linter`
enforcing the lightweight-module rule for the package root, settings, CLI,
storage, and source adapters. It replaces the old probe-style test.

Planned transition path:

- keep the contract focused on modules that must stay lightweight;
- expand the contract set if future refactors introduce new boundary modules;
- keep `pre-commit` as the cheapest place to catch import regressions early.
