# lib-finder Source Factory and EAFP Simplification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Simplify the PyPI source parsing boundary by centralizing record construction behind an explicit factory object, reducing branching in coercion-heavy code with EAFP-style helpers where it improves clarity, and documenting the local-only Codex workspace boundary.

**Architecture:** Keep the public `lib_finder.sources.parsing` API stable, but move the construction logic into a focused factory object and narrower helper functions so the code is easier to reason about and test. Use EAFP where it reduces nested LBYL checks in payload parsing, but keep the public behavior and validation surface unchanged. Add a repo-local Codex note under a gitignored path so future agent sessions inherit the same repo-local conventions without committing operator notes into the product tree.

**Tech Stack:** Python 3.14, Pydantic, pytest, ruff, pyright, import-linter, lefthook, UV, RTK.

---

### Task 1: Introduce a source-record factory boundary

**Files:**
- Create: `src/lib_finder/sources/factories.py`
- Create: `src/lib_finder/sources/status.py`
- Modify: `src/lib_finder/sources/parsing.py`
- Modify: `tests/test_pypi.py`
- Modify: `tests/test_pypi_edges.py`
- Modify: `tests/test_sources.py`

- [ ] **Step 1: Write the failing test**

```python
from lib_finder.sources.factories import PyPIRecordFactory


def test_factory_builds_detail_records_with_meta_status_fallback() -> None:
    factory = PyPIRecordFactory()
    record = factory.build_project_detail_record(
        {
            "name": "requests",
            "meta": {
                "project-status": {
                    "status": "active",
                    "reason": "maintained upstream",
                },
            },
        },
        raw_name="Requests",
        root_last_serial=99,
        fetched_at="2026-06-06T00:00:00+00:00",
    )

    assert record.project_status == "active"
    assert record.status_reason == "maintained upstream"
```

- [ ] **Step 2: Run the focused test and confirm it fails**

Run: `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_pypi_edges.py -q`
Expected: import failure for `PyPIRecordFactory` before the factory module exists.

- [ ] **Step 3: Implement the factory boundary**

```python
from dataclasses import dataclass
from collections.abc import Mapping
from typing import Any

from .models import ProjectDetailRecord, ProjectDiscoveryRecord, ProjectFileRecord


@dataclass(slots=True)
class PyPIRecordFactory:
    def build_project_discovery_record(
        self,
        payload: Mapping[str, Any],
        *,
        root_last_serial: int | None,
        fetched_at: str,
    ) -> ProjectDiscoveryRecord:
        # Discovery construction stays narrow and deterministic.
        raise NotImplementedError

    def build_project_detail_record(
        self,
        payload: Mapping[str, Any],
        *,
        raw_name: str,
        root_last_serial: int | None,
        fetched_at: str,
    ) -> ProjectDetailRecord:
        # EAFP-style coercion should live here instead of scattered branching.
        raise NotImplementedError
```

- [ ] **Step 4: Run the test and confirm it passes**

Run: `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_pypi.py tests/test_pypi_edges.py tests/test_sources.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/lib_finder/sources/factories.py src/lib_finder/sources/parsing.py tests/test_pypi.py tests/test_pypi_edges.py tests/test_sources.py
git commit -m "refactor: centralize source record factory logic"
```

### Task 2: Add a local-only Codex workspace note

**Files:**
- Create: `.codex/CODEX.md`
- Modify: `.gitignore` if the ignore rule needs to be clarified
- Modify: `README.md` if the agent workflow section needs a short pointer

- [x] **Step 1: Write the local note**

```md
# Local Codex Notes for lib-finder

- Treat `docs/architecture/LIB_FINDER_AGENT_REALIGNMENT_PLAN_FINAL_V3.md` as the controlling source of truth.
- Keep `.codex/` and `.agents/` local-only.
- Prefer `uv run ...` in docs and `uv run rtk ...` for noisy agent commands.
- Favor small factories and EAFP-style parsing when they make code simpler.
```

- [x] **Step 2: Verify the file is ignored**

Run: `git status --short --ignored`
Expected: `.codex/CODEX.md` appears only as ignored local state, not as a tracked product file.

- [ ] **Step 3: Commit only tracked docs/code changes**

```bash
git add .gitignore README.md
git commit -m "docs: align local agent workspace notes"
```

### Task 3: Refresh docs and gates after the factory split

**Files:**
- Modify: `README.md`
- Modify: `docs/architecture/LIB_FINDER_AGENT_REALIGNMENT_PLAN_FINAL_V3.md`
- Modify: `docs/testing/README.md`
- Modify: `lefthook.yml` only if the new module split changes the hook selection surface

- [ ] **Step 1: Update docs to describe the new factory boundary**

```md
- The source parsing boundary now exposes a focused factory object behind the public builders.
- Coercion-heavy parsing code uses EAFP where it makes the code flatter and clearer.
- The local Codex guidance file is intentionally gitignored and remains workspace-only.
```

- [ ] **Step 2: Re-run the relevant gates**

Run:
- `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check src tests`
- `UV_CACHE_DIR=/tmp/uv-cache uv run pyright`
- `UV_CACHE_DIR=/tmp/uv-cache uv run lint-imports`
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_pypi.py tests/test_pypi_edges.py tests/test_sources.py -q`

Expected: all commands pass.

- [ ] **Step 3: Commit**

```bash
git add README.md docs/architecture/LIB_FINDER_AGENT_REALIGNMENT_PLAN_FINAL_V3.md docs/testing/README.md lefthook.yml
git commit -m "docs: align source factory simplification"
```
