# lib-finder Task 4 Haystack Skeleton Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the Haystack pipeline skeleton required by the V3 plan, with small typed components for package-document normalization and conversion, while keeping local model calls out of scope.

**Architecture:** Introduce Haystack as the orchestration layer for the next stage of the pipeline, but keep this tranche limited to deterministic component and pipeline scaffolding. The new modules should convert the existing typed source records into Haystack `Document` objects, expose stable factory functions for future pipeline wiring, and stay fully testable without any live service dependencies.

**Tech Stack:** Python 3.14, `haystack-ai`, Haystack `@component` APIs, Haystack `Document` and `Pipeline`, `pydantic`, `pytest`, `ruff`, `pyright`, `import-linter`, `lefthook`.

---

### Task 1: Add Haystack dependency and canonical component scaffolding

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Create: `src/lib_finder/pipeline/haystack_components.py`
- Modify: `src/lib_finder/pipeline/__init__.py`
- Create: `tests/test_haystack_components.py`

- [x] **Step 1: Write the failing test**

```python
from haystack import Document
from lib_finder.pipeline.haystack_components import PackageDocumentNormalizer

def test_package_document_normalizer_converts_a_record_to_a_document() -> None:
    component = PackageDocumentNormalizer()
    result = component.run(
        raw_name="Requests",
        normalized_name="requests",
        source="pypi_simple_root",
        record_type="project_discovery",
        content="Requests is a popular HTTP library.",
        meta={"root_last_serial": 123},
    )
    document = result["documents"][0]
    assert isinstance(document, Document)
    assert document.content == "Requests is a popular HTTP library."
    assert document.meta["normalized_name"] == "requests"
```

- [x] **Step 2: Run the focused test and confirm it fails**

Run: `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_haystack_components.py -q`
Expected: import failure for `haystack` or missing component module before implementation.

- [x] **Step 3: Implement the minimal component layer**

```python
from collections.abc import Mapping
from typing import Any

from haystack import Document, component


def _require_non_empty(value: str, field_name: str) -> str:
    if not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    return value


@component
class PackageDocumentNormalizer:
    def __init__(self, pipeline_stage: str = "document") -> None:
        self.pipeline_stage = _require_non_empty(pipeline_stage, "pipeline_stage")

    @component.output_types(documents=list[Document])
    def run(
        self,
        *,
        raw_name: str,
        normalized_name: str,
        source: str,
        record_type: str,
        content: str,
        meta: Mapping[str, Any] | None = None,
    ) -> dict[str, list[Document]]:
        content = _require_non_empty(content, "content")
        metadata: dict[str, Any] = {}
        if meta is not None:
            metadata.update(meta)
        metadata.update(
            {
                "raw_name": _require_non_empty(raw_name, "raw_name"),
                "normalized_name": _require_non_empty(
                    normalized_name, "normalized_name"
                ),
                "source": _require_non_empty(source, "source"),
                "record_type": _require_non_empty(record_type, "record_type"),
                "pipeline_stage": self.pipeline_stage,
            }
        )
        return {"documents": [Document(content=content, meta=metadata)]}
```

- [x] **Step 4: Run the test and confirm it passes**

Run: `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_haystack_components.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock src/lib_finder/pipeline/haystack_components.py src/lib_finder/pipeline/__init__.py tests/test_haystack_components.py
git commit -m "feat: add haystack component skeleton"
```

### Task 2: Add pipeline factory modules for document conversion

**Files:**
- Create: `src/lib_finder/pipeline/discovery_pipeline.py`
- Create: `src/lib_finder/pipeline/detail_pipeline.py`
- Create: `src/lib_finder/pipeline/document_pipeline.py`
- Modify: `src/lib_finder/pipeline/__init__.py`
- Create: `tests/test_haystack_pipelines.py`

- [x] **Step 1: Write the failing test**

```python
from lib_finder.pipeline.document_pipeline import build_document_pipeline

def test_document_pipeline_wires_normalizer_component() -> None:
    pipeline = build_document_pipeline()
    result = pipeline.run(
        {
            "document_normalizer": {
                "raw_name": "Requests",
                "normalized_name": "requests",
                "source": "pypi_simple_root",
                "record_type": "project_discovery",
                "content": "Requests is a popular HTTP library.",
                "meta": {},
            }
        }
    )
    assert result["document_normalizer"]["documents"][0].meta["normalized_name"] == "requests"
```

- [x] **Step 2: Run the focused test and confirm it fails**

Run: `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_haystack_pipelines.py -q`
Expected: missing factory modules or unimplemented Haystack pipeline behavior.

- [x] **Step 3: Implement the minimal pipeline factories**

```python
from haystack import Pipeline

from .haystack_components import PackageDocumentNormalizer

def build_document_pipeline() -> Pipeline:
    pipeline = Pipeline()
    pipeline.add_component(
        "document_normalizer",
        PackageDocumentNormalizer(pipeline_stage="document"),
    )
    return pipeline

def build_discovery_pipeline() -> Pipeline:
    pipeline = Pipeline()
    pipeline.add_component(
        "discovery_document_normalizer",
        PackageDocumentNormalizer(pipeline_stage="discovery"),
    )
    return pipeline

def build_detail_pipeline() -> Pipeline:
    pipeline = Pipeline()
    pipeline.add_component(
        "detail_document_normalizer",
        PackageDocumentNormalizer(pipeline_stage="detail"),
    )
    return pipeline
```

- [x] **Step 4: Run the test and confirm it passes**

Run: `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_haystack_pipelines.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/lib_finder/pipeline/discovery_pipeline.py src/lib_finder/pipeline/detail_pipeline.py src/lib_finder/pipeline/document_pipeline.py src/lib_finder/pipeline/__init__.py tests/test_haystack_pipelines.py
git commit -m "feat: add haystack pipeline factories"
```

### Task 3: Align docs and verification gates

**Files:**
- Modify: `README.md`
- Modify: `docs/architecture/LIB_FINDER_AGENT_REALIGNMENT_PLAN_FINAL_V3.md`
- Modify: `docs/testing/README.md`
- Modify: `lefthook.yml`
- Modify: `pyproject.toml`

- [x] **Step 1: Update docs to describe the Haystack skeleton**

```md
- The pipeline layer now has Haystack component and factory skeletons for package-document normalization and conversion.
- The skeleton is deterministic and intentionally free of live model calls.
- Later batches will connect LangExtract/Ollama through the same component boundary.
```

- [x] **Step 2: Add or refresh verification gates**

Run:
- `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check src tests`
- `UV_CACHE_DIR=/tmp/uv-cache uv run pyright`
- `UV_CACHE_DIR=/tmp/uv-cache uv run lint-imports`
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_haystack_components.py tests/test_haystack_pipelines.py -q`

Expected: all commands pass with no errors.

- [ ] **Step 3: Commit**

```bash
git add README.md docs/architecture/LIB_FINDER_AGENT_REALIGNMENT_PLAN_FINAL_V3.md docs/testing/README.md lefthook.yml pyproject.toml
git commit -m "docs: align v3 plan with haystack skeleton"
```
