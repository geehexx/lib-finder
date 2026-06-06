# lib-finder Phase 4 Runtime and Gates Implementation Plan

> Superseded by [docs/architecture/LIB_FINDER_AGENT_REALIGNMENT_PLAN_FINAL_V3.md](/home/gxx/projects/lib-finder/docs/architecture/LIB_FINDER_AGENT_REALIGNMENT_PLAN_FINAL_V3.md) and archived in [`docs/archive/README.md`](/home/gxx/projects/lib-finder/docs/archive/README.md). Kept for historical context only.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a bounded, locally runnable extraction runtime for long-text package documents, then harden the repo’s quality gates and documentation around the real implementation.

**Architecture:** Keep ingestion and extraction separate. Add a focused `src/lib_finder/extraction/` package that owns extraction schemas, source-document normalization, and LangExtract/Ollama adapter code. Expose a small CLI command for local extraction runs, persist only grounded structured results, and keep the pipeline testable with recorded/live fixtures. Use the existing `lefthook`-based gate stack as the single quality surface, but split broad non-live tests from smoke tests when xdist proves unstable. Keep RTK as an agent-side output filter for noisy command sessions while leaving `uv run ...` as the canonical documented command surface.

**Tech Stack:** Python 3.14, `pydantic`, `pydantic-settings`, `httpx`, `typer`, `langextract`, local Ollama, `pytest`, `pytest-recording`/VCR, `pytest-cov`, `interrogate`, `ruff`, `pyright`, `lefthook`.

---

### Task 1: Add a focused extraction runtime package

**Files:**
- Create: `src/lib_finder/extraction/__init__.py`
- Create: `src/lib_finder/extraction/models.py`
- Create: `src/lib_finder/extraction/prompts.py`
- Create: `src/lib_finder/extraction/runner.py`
- Create: `tests/test_extraction_models.py`
- Create: `tests/test_extraction_runner.py`

- [ ] **Step 1: Write the failing tests**

```python
from lib_finder.extraction.models import (
    ExtractionSourceDocument,
    ExtractionSpan,
    ExtractedFact,
)


def test_extracted_fact_requires_grounding():
    span = ExtractionSpan(start=0, end=5, snippet="hello")
    doc = ExtractionSourceDocument(
        source_id="pypi:requests:README.md",
        title="requests README",
        text="hello world",
    )
    fact = ExtractedFact(
        fact_type="supported_python",
        value=">=3.9",
        source_document=doc,
        source_spans=(span,),
    )
    assert fact.source_spans[0].snippet == "hello"
    assert fact.source_document.source_id == "pypi:requests:README.md"
```

- [ ] **Step 2: Run the focused test to confirm it fails**

Run: `uv run pytest tests/test_extraction_models.py -q`
Expected: FAIL because the extraction package does not exist yet.

- [ ] **Step 3: Implement the minimal extraction models and runner helpers**

```python
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ExtractionSpan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    start: int
    end: int
    snippet: str


class ExtractionSourceDocument(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source_id: str
    title: str
    text: str
    uri: str | None = None


class ExtractedFact(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    fact_type: str
    value: str
    source_document: ExtractionSourceDocument
    source_spans: tuple[ExtractionSpan, ...] = Field(default_factory=tuple)
    confidence: float | None = None


class ExtractionRunResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source_document: ExtractionSourceDocument
    facts: tuple[ExtractedFact, ...] = Field(default_factory=tuple)
    model_id: str | None = None
    model_url: str | None = None
```

- [ ] **Step 4: Run the focused test again**

Run: `uv run pytest tests/test_extraction_models.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/lib_finder/extraction tests/test_extraction_models.py
git commit -m "feat: add extraction runtime models"
```

### Task 2: Wire a local extraction command and optional LangExtract/Ollama adapter

**Files:**
- Modify: `src/lib_finder/cli.py`
- Modify: `src/lib_finder/settings.py`
- Modify: `src/lib_finder/__init__.py`
- Create: `tests/test_extraction_runner.py`
- Create: `tests/test_cli_extract.py`

- [ ] **Step 1: Write the failing tests**

```python
from typer.testing import CliRunner

from lib_finder.cli import app


def test_extract_command_requires_text_or_file(tmp_path):
    runner = CliRunner()
    result = runner.invoke(app, ["extract"])
    assert result.exit_code != 0
    assert "text" in result.output.lower()
```

- [ ] **Step 2: Run the focused test to confirm it fails**

Run: `uv run pytest tests/test_cli_extract.py -q`
Expected: FAIL because `extract` does not exist yet.

- [ ] **Step 3: Implement the minimal command and adapter**

```python
import json

@app.command("extract")
def extract(
    text: Annotated[str | None, typer.Option("--text", help="Raw text to extract.")] = None,
    text_file: Annotated[
        Path | None,
        typer.Option(
            "--text-file",
            exists=True,
            dir_okay=False,
            readable=True,
            help="Path to a UTF-8 text file.",
        ),
    ] = None,
    model_id: Annotated[
        str | None,
        typer.Option(
            "--model-id",
            help="LangExtract model identifier, such as gemma2:2b.",
        ),
    ] = None,
    model_url: Annotated[
        str | None,
        typer.Option(
            "--model-url",
            help="Ollama base URL, such as http://localhost:11434.",
        ),
    ] = None,
) -> None:
    if text is None and text_file is None:
        raise typer.BadParameter("Provide --text or --text-file.")
    raw_text = text if text is not None else text_file.read_text(encoding="utf-8")
    source_id = text_file.name if text_file is not None else "stdin"
    document = ExtractionSourceDocument(
        source_id=f"cli:{source_id}",
        title=source_id,
        text=raw_text,
    )
    result = run_text_extraction(
        document=document,
        model_id=model_id,
        model_url=model_url,
    )
    typer.echo(
        json.dumps(
            result.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
        )
    )
```

Implement it so the command:
- loads text from `--text` or `--text-file`;
- validates the document with `ExtractionSourceDocument`;
- calls a small adapter function that can use LangExtract when available;
- prints grounded JSON to stdout.

- [ ] **Step 4: Run the focused test again**

Run: `uv run pytest tests/test_cli_extract.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/lib_finder/cli.py src/lib_finder/settings.py src/lib_finder/__init__.py tests/test_extraction_runner.py tests/test_cli_extract.py
git commit -m "feat: add local extraction command"
```

### Task 3: Harden extraction and repo quality gates together

**Files:**
- Modify: `lefthook.yml`
- Modify: `pyproject.toml`
- Modify: `README.md`
- Modify archived copies in `docs/archive/`:
  - `docs/archive/2026-06-06-lib-finder-phase4-extraction-design.md`
  - `docs/archive/2026-06-06-lib-finder-platform-roadmap.md`
  - `docs/archive/2026-06-06-lib-finder-quality-hygiene-plan.md`
- Modify: `tests/test_pipeline.py`
- Modify: `tests/test_pypi_http.py`
- Create: `tests/test_extraction_live.py`

- [ ] **Step 1: Write the failing tests**

```python
import os

import pytest

from lib_finder.extraction.models import ExtractionSourceDocument
from lib_finder.extraction.runner import run_text_extraction


@pytest.mark.live
@pytest.mark.smoke
def test_live_extraction_smoke_uses_local_ollama() -> None:
    if os.getenv("LIB_FINDER_LIVE") != "1":
        pytest.skip("live extraction requires LIB_FINDER_LIVE=1")

    document = ExtractionSourceDocument(
        source_id="fixture:requests-readme",
        title="requests README",
        text="Requests supports Python >=3.9 and is actively maintained.",
    )
    result = run_text_extraction(
        document=document,
        model_id="gemma2:2b",
        model_url=os.getenv("OLLAMA_HOST", "http://localhost:11434"),
    )
    assert result.source_document.source_id == "fixture:requests-readme"
    assert result.facts
    assert all(fact.source_spans for fact in result.facts)
```

- [ ] **Step 2: Run the relevant gate and confirm the gap**

Run: `uv run pytest -q -m "not live" --cov=lib_finder --cov-report=term-missing`
Expected: PASS once extraction code lands, with coverage staying above the threshold.

- [ ] **Step 3: Add the quality gate integration**

Add or keep:
- branch coverage as a hard gate;
- `interrogate` as the docstring gate;
- Ruff McCabe complexity as the code-complexity gate;
- recorded HTTP smoke tests for discovery and detail;
- live smoke tests behind `LIB_FINDER_LIVE=1`;
- extraction smoke tests that replay local fixtures and, when available, run against local Ollama.

If a second complexity tool is added, use it as a reporting/audit tool first, not as a duplicate enforcement layer.

- [ ] **Step 4: Run the full gate stack**

Run:
- `uv run pytest -q`
- `uv run pytest -q -m "not live" --cov=lib_finder --cov-report=term-missing`
- `uv run pyright`
- `uv run ruff check src tests`
- `uv run interrogate --quiet --fail-under 85 src/lib_finder`
- `lefthook run pre-commit`
- `lefthook run pre-push`

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add lefthook.yml pyproject.toml README.md docs/archive/2026-06-06-lib-finder-phase4-extraction-design.md docs/archive/2026-06-06-lib-finder-platform-roadmap.md docs/archive/2026-06-06-lib-finder-quality-hygiene-plan.md tests/test_pipeline.py tests/test_pypi_http.py tests/test_extraction_live.py
git commit -m "feat: harden phase 4 extraction and gates"
```
