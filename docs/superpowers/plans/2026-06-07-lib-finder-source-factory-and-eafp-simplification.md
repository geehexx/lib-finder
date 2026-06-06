# lib-finder Source Factory and EAFP Simplification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Simplify the PyPI source parsing boundary by centralizing record construction behind an explicit factory object, reducing branching in coercion-heavy code with EAFP-style helpers where it improves clarity, and documenting the local-only Codex workspace boundary.

**Architecture:** Keep the public `lib_finder.sources.parsing` API stable, but move the construction logic into a focused factory object and narrower helper functions so the code is easier to reason about and test. Use EAFP where it reduces nested LBYL checks in payload parsing, but keep the public behavior and validation surface unchanged. Add a repo-local Codex note under a gitignored path so future agent sessions inherit the same repo-local conventions without committing operator notes into the product tree.

**Tech Stack:** Python 3.14, Pydantic, pytest, ruff, pyright, import-linter, lefthook, UV, RTK.

**Priority note:** Treat this as the next refactor lane before broadening later V3 domain layers. When touching `src/lib_finder/sources/parsing.py` or related construction paths, prefer the simplest boundary that removes LBYL guard ladders, makes the failure point obvious, and exposes a small factory/service object only where it actually reduces coupling.

---

### Task 1: Introduce a source-record factory boundary

**Files:**
- Create: `src/lib_finder/sources/factories.py`
- Create: `src/lib_finder/sources/status.py`
- Modify: `src/lib_finder/sources/parsing.py`
- Modify: `tests/test_pypi.py`
- Modify: `tests/test_pypi_edges.py`
- Modify: `tests/test_sources.py`

- [x] **Step 1: Write the failing test**

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

- [x] **Step 2: Run the focused test and confirm it fails**

Run: `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_pypi_edges.py -q`
Expected: import failure for `PyPIRecordFactory` before the factory module exists.

- [x] **Step 3: Implement the factory boundary**

```python
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from packaging.utils import canonicalize_name

from .models import ProjectDetailRecord, ProjectDiscoveryRecord, ProjectFileRecord
from .parsing import (
    _build_project_file_record,
    _canonical_payload_json,
    _parse_files,
    _parse_meta_api_version,
    _parse_serial_from_payload,
    _parse_versions,
    _payload_hash,
    _suspicion_features,
)
from .status import parse_project_status


def _require_project_name(
    payload: Mapping[str, Any],
    *,
    field_name: str,
) -> str:
    try:
        raw_name = payload["name"]
    except KeyError as exc:
        raise ValueError(f"{field_name} is missing a valid name") from exc
    if not isinstance(raw_name, str) or not raw_name.strip():
        raise ValueError(f"{field_name} is missing a valid name")
    return raw_name


def _canonicalized_name(raw_name: str, *, field_name: str) -> str:
    normalized_name = canonicalize_name(raw_name)
    if not normalized_name:
        raise ValueError(f"{field_name} is missing a valid name")
    return normalized_name


@dataclass(slots=True)
class PyPIRecordFactory:
    """Construct normalized record models from PyPI Simple payloads."""

    def build_project_discovery_record(
        self,
        payload: Mapping[str, Any],
        *,
        root_last_serial: int | None,
        fetched_at: str,
    ) -> ProjectDiscoveryRecord:
        """Build a discovery record from a PyPI Simple root payload."""

        raw_name = _require_project_name(payload, field_name="PyPI project entry")
        normalized_name = _canonicalized_name(raw_name, field_name="PyPI project entry")
        raw_payload_json = _canonical_payload_json(payload)
        payload_hash = _payload_hash(raw_payload_json)

        return ProjectDiscoveryRecord(
            raw_name=raw_name,
            normalized_name=normalized_name,
            root_last_serial=root_last_serial,
            project_last_serial=_parse_serial_from_payload(payload),
            fetched_at=fetched_at,
            suspicion=_suspicion_features(raw_name, normalized_name),
            raw_payload_json=raw_payload_json,
            payload_hash=payload_hash,
        )

    def build_project_detail_record(
        self,
        payload: Mapping[str, Any],
        *,
        raw_name: str,
        root_last_serial: int | None,
        fetched_at: str,
        project_last_serial: int | None = None,
    ) -> ProjectDetailRecord:
        """Build a detail record from a PyPI Simple project payload."""

        project_name = _require_project_name(
            payload,
            field_name="PyPI project detail payload",
        )
        normalized_name = _canonicalized_name(
            project_name,
            field_name="PyPI project detail payload",
        )
        if canonicalize_name(raw_name) != normalized_name:
            raise ValueError(
                "PyPI project detail payload name does not match the discovered project"
            )

        raw_payload_json = _canonical_payload_json(payload)
        payload_hash = _payload_hash(raw_payload_json)
        detail_project_last_serial = (
            project_last_serial
            if project_last_serial is not None
            else _parse_serial_from_payload(payload)
        )
        project_status, status_reason = parse_project_status(payload)

        return ProjectDetailRecord(
            raw_name=raw_name,
            normalized_name=normalized_name,
            project_name=project_name,
            root_last_serial=root_last_serial,
            project_last_serial=detail_project_last_serial,
            fetched_at=fetched_at,
            project_status=project_status,
            status_reason=status_reason,
            meta_api_version=_parse_meta_api_version(payload),
            versions=_parse_versions(payload),
            files=tuple(
                _build_project_file_record(file_payload)
                for file_payload in _parse_files(payload)
            ),
            suspicion=_suspicion_features(raw_name, normalized_name),
            raw_payload_json=raw_payload_json,
            payload_hash=payload_hash,
        )


DEFAULT_PYPI_RECORD_FACTORY = PyPIRecordFactory()
```

- [x] **Step 4: Run the test and confirm it passes**

Run: `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_pypi.py tests/test_pypi_edges.py tests/test_sources.py -q`
Expected: PASS

- [x] **Step 5: Commit**

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

- [x] **Step 3: Commit only tracked docs/code changes**

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

- [x] **Step 1: Update docs to describe the new factory boundary**

```md
- The source parsing boundary now exposes a focused factory object behind the public builders.
- Coercion-heavy parsing code uses EAFP where it makes the code flatter and clearer.
- The local Codex guidance file is intentionally gitignored and remains workspace-only.
```

- [x] **Step 2: Re-run the relevant gates**

Run:
- `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check src tests`
- `UV_CACHE_DIR=/tmp/uv-cache uv run pyright`
- `UV_CACHE_DIR=/tmp/uv-cache uv run lint-imports`
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_pypi.py tests/test_pypi_edges.py tests/test_sources.py -q`

Expected: all commands pass.

- [x] **Step 3: Commit**

```bash
git add README.md docs/architecture/LIB_FINDER_AGENT_REALIGNMENT_PLAN_FINAL_V3.md docs/testing/README.md lefthook.yml
git commit -m "docs: align source factory simplification"
```

### Task 4: Prioritize the next EAFP/OO cleanup wave

**Files:**
- Review: `src/lib_finder/sources/parsing.py`
- Review: `src/lib_finder/sources/factories.py`
- Review: `src/lib_finder/storage/store.py`
- Review: `src/lib_finder/pipeline/qualification.py`
- Review: `tests/test_pypi_edges.py`
- Review: `tests/test_storage_edges.py`
- Modify: `docs/architecture/LIB_FINDER_AGENT_REALIGNMENT_PLAN_FINAL_V3.md`
- Modify: `docs/testing/README.md`
- Modify: `.codex/CODEX.md`

- [ ] **Step 1: Audit the coercion-heavy branches**

```python
# Look for repeated pre-checks that only exist to protect a coercion.
# Prefer a single try/except if it makes the failure path clearer.
# Keep only the validation that materially changes the error message or behavior.
```

- [ ] **Step 2: Convert the next simplest cluster into a factory or service object**

```python
# If a helper cluster is constructing the same record or validation output
# in several places, move that construction behind a named object.
# Keep the public module surface thin and preserve compatibility wrappers
# only where external imports still depend on them.
```

- [ ] **Step 3: Rehearse the lane boundaries in docs and local notes**

```md
- Document the EAFP/factory preference in the V3 plan and testing guide.
- Keep `.codex/CODEX.md` as the local memory for this refactor style.
- Keep unit/edge tests closest to the parsing and factory boundaries.
```

- [ ] **Step 4: Verify the focused refactor lane before moving to broader V3 work**

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_pypi.py tests/test_pypi_edges.py tests/test_storage_edges.py -q
UV_CACHE_DIR=/tmp/uv-cache uv run ruff check src tests
UV_CACHE_DIR=/tmp/uv-cache uv run pyright
UV_CACHE_DIR=/tmp/uv-cache uv run lint-imports
```
