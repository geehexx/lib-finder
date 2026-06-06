# lib-finder

`lib-finder` collects, normalizes, and caches PyPI metadata in SQLite.

The controlling architecture and execution source of truth is
[docs/architecture/LIB_FINDER_AGENT_REALIGNMENT_PLAN_FINAL_V3.md](docs/architecture/LIB_FINDER_AGENT_REALIGNMENT_PLAN_FINAL_V3.md).
Older phase specs are archived in [docs/archive/README.md](docs/archive/README.md)
and are retained only as historical context.

It is built around a few explicit stages:

1. discover packages from the PyPI Simple root;
2. fetch project-detail pages for selected packages;
3. persist snapshots, versions, artifacts, and audit rows;
4. recompute adoption rollups and qualification state from SQLite alone.

The optional CSV export path is a debug snapshot only. SQLite is the canonical
store.

## Entry Points

- `lib-finder`: default detail-enrichment pipeline driven by SQLite package selection.
- `lib-finder discover`: synchronize the PyPI Simple root into SQLite.
- `lib-finder qualify`: recompute adoption rollups and qualification state from SQLite.
- `lib-finder extract`: run the local grounded extraction adapter on raw text.

## Common Commands

```bash
uv run lib-finder discover --record-limit 100
uv run lib-finder
uv run lib-finder --package-name requests --package-name numpy
uv run lib-finder qualify
uv run lib-finder qualify --package-name requests
uv run lib-finder extract --text "Requests supports Python >=3.9 and is actively maintained."
uv run lib-finder extract --text-file README.md
```

The default database path is `data/cache/lib-finder.sqlite3`.

## Configuration

`lib-finder` reads process environment variables with the `LIB_FINDER_` prefix
through the `LibFinderSettings` model.

The supported environment surface includes the same knobs exposed by the CLI:

- `LIB_FINDER_DB_PATH`
- `LIB_FINDER_CSV_EXPORT_PATH`
- `LIB_FINDER_PACKAGE_NAMES`
- `LIB_FINDER_ALL_PACKAGES`
- `LIB_FINDER_QUEUE_SIZE`
- `LIB_FINDER_BATCH_SIZE`
- `LIB_FINDER_REQUEST_TIMEOUT`
- `LIB_FINDER_READ_TIMEOUT`
- `LIB_FINDER_DETAIL_CONCURRENCY`
- `LIB_FINDER_USER_AGENT`
- `LIB_FINDER_RECORD_LIMIT`
- `LIB_FINDER_EXTRACTION_MODEL_ID`
- `LIB_FINDER_EXTRACTION_MODEL_URL`

CLI flags still override env defaults when they are provided explicitly. The
settings layer does not auto-load `.env` files; export the variables in your
shell, launcher, or CI environment if you want them applied automatically.

## Agent Workflow

RTK is available locally for token-efficient agent sessions. Use it when command
output is noisy or repetitive, especially for `git`, `pytest`, `ruff`, and
summary-style inspection commands.

- Canonical documentation and CI examples stay on plain `uv run ...`.
- Agent sessions should use `uv run rtk pytest` and `uv run rtk ruff` for
  Python tooling so the wrapper runs inside the project environment.
- Agent sessions can use `rtk git`, `rtk summary`, `rtk read`, and `rtk find`
  to reduce context churn for non-Python commands.
- Repo-local RTK policy lives in [RTK.md](RTK.md) and is included through
  [AGENTS.md](AGENTS.md).
- Repo-local Codex and agent scratch directories (`.codex/` and `.agents/`)
  are ignored on purpose; keep durable product notes in `docs/` instead of
  committing local agent workspace artifacts here.

## Verification

Local checks are designed to be cheap and layered:

```bash
lefthook install
lefthook run pre-commit
LIB_FINDER_LIVE=1 uv run pytest -q -m smoke
LIB_FINDER_LIVE=1 LIB_FINDER_EXTRACTION_MODEL_ID=qwen3.5:0.8b LIB_FINDER_EXTRACTION_MODEL_URL=http://localhost:11434 uv run pytest tests/test_extraction_live.py -q
uv run ruff check src tests
uv run lint-imports
uv run pyright
uv run interrogate --quiet --fail-under 85 src/lib_finder
uv run pytest -q -m "not live" --cov=lib_finder --cov-report=term-missing
```

The test suite includes:

- property-based checks for normalization invariants;
- recorded HTTP smoke coverage for both discovery and detail replay;
- live smoke coverage behind `LIB_FINDER_LIVE=1`;
- local Ollama-backed extraction smoke coverage behind `LIB_FINDER_LIVE=1`;
- local SQLite integration tests for discovery, detail enrichment, and rollups.
- branch coverage gating on the `src/lib_finder` package;
- complexity gating through Ruff McCabe checks.
- import-boundary gating through `import-linter`.

Hook policy:

- `pre-commit` now runs only the fast `unit` + `architecture` lane plus lint,
  formatting, type checking, doc coverage, and the import-boundary contract.
- `pre-push` now runs the broad non-live deterministic lane in parallel with
  `pytest-xdist`, runs the CLI smoke lane, runs the recorded HTTP smoke file in
  parallel, and runs the pipeline smoke file serially with a longer timeout so
  the SQLite-backed smoke path stays reliable.
- `pytest-testmon` is a candidate for optional local incremental reruns, but it
  is not part of the default hook path yet.

## Documentation

Current operator and architecture docs live in:

- [V3 realignment plan](docs/architecture/LIB_FINDER_AGENT_REALIGNMENT_PLAN_FINAL_V3.md)
- [ADRs](docs/adr/)
- [testing strategy](docs/testing/README.md)
- [archive index](docs/archive/README.md)

The V3 plan supersedes the older phase specs and roadmap. Those files are kept
only as archived context and should not be treated as the controlling source.

## Storage Strategy

The current implementation is a transitional SQLite-backed layer aligned to the
V3 storage architecture. The storage package already uses SQLAlchemy Core plus
Alembic-managed migrations, with SQLite remaining the local persistence
backend.

`SQLiteStore.open()` runs the Alembic `head` migration against the target
database before handing back the connection, so new and legacy SQLite files
share the same schema bootstrap path.

The parser and storage record models are Pydantic-based. The source adapter is
split across `src/lib_finder/sources/constants.py`,
`src/lib_finder/sources/factories.py`, `src/lib_finder/sources/parsing.py`,
`src/lib_finder/sources/status.py`, `src/lib_finder/sources/client.py`, and
`src/lib_finder/sources/models.py`. The old wrapper modules are gone;
canonical source imports point directly at these submodules. The remaining work
is the later Haystack/LangExtract pipeline batches.

SQLAlchemy ORM is intentionally out of scope for this pipeline.

## Long-Term Extraction

The V3 plan keeps long-text extraction separate from ingestion, and the current
runtime slice is intentionally thin:

- LangExtract + local Ollama is the preferred long-term extraction path;
- LlamaIndex/LlamaExtract is a possible future option, but not the default path;
- the ingestion pipeline should continue to work without LLM infrastructure;
- a deterministic Haystack skeleton now exists for package-document
  normalization and pipeline wiring, but it does not make live model calls yet;
- the live smoke test uses a small local Ollama model and can be redirected
  with `LIB_FINDER_EXTRACTION_MODEL_ID` and `LIB_FINDER_EXTRACTION_MODEL_URL`.
