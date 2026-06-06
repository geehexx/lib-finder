from __future__ import annotations

import json
from types import SimpleNamespace

from typer.testing import CliRunner

from lib_finder.cli import app


def test_extract_command_requires_text_or_file() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["extract"])

    assert result.exit_code != 0
    assert "text" in result.output.lower()


def test_extract_command_emits_grounded_json_for_text(monkeypatch) -> None:
    runner = CliRunner()

    def fake_run_text_extraction(document, *, model_id=None, model_url=None):
        return SimpleNamespace(
            model_dump=lambda mode="json": {
                "source_document": {
                    "source_id": document.source_id,
                    "title": document.title,
                    "text": document.text,
                    "uri": document.uri,
                },
                "facts": [],
                "model_id": model_id,
                "model_url": model_url,
            }
        )

    monkeypatch.setattr(
        "lib_finder.extraction.run_text_extraction", fake_run_text_extraction
    )

    result = runner.invoke(
        app,
        [
            "extract",
            "--text",
            "Requests supports Python >=3.9 and is actively maintained.",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["source_document"]["source_id"] == "cli:stdin"
    assert payload["facts"] == []
    assert payload["model_id"] is None
    assert payload["model_url"] is None


def test_extract_command_uses_env_defaults_and_text_file(monkeypatch, tmp_path) -> None:
    runner = CliRunner()
    text_path = tmp_path / "requests.txt"
    text_path.write_text(
        "Requests supports Python >=3.9 and is actively maintained.",
        encoding="utf-8",
    )
    monkeypatch.setenv("LIB_FINDER_EXTRACTION_MODEL_ID", "gemma2:2b")
    monkeypatch.setenv("LIB_FINDER_EXTRACTION_MODEL_URL", "http://localhost:11434")

    captured: dict[str, str | None] = {}

    def fake_run_text_extraction(document, *, model_id=None, model_url=None):
        captured["model_id"] = model_id
        captured["model_url"] = model_url
        return SimpleNamespace(
            model_dump=lambda mode="json": {
                "source_document": {
                    "source_id": document.source_id,
                    "title": document.title,
                    "text": document.text,
                    "uri": document.uri,
                },
                "facts": [],
                "model_id": model_id,
                "model_url": model_url,
            }
        )

    monkeypatch.setattr(
        "lib_finder.extraction.run_text_extraction", fake_run_text_extraction
    )

    result = runner.invoke(
        app,
        [
            "extract",
            "--text-file",
            str(text_path),
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["source_document"]["source_id"] == f"cli:{text_path.name}"
    assert payload["model_id"] == "gemma2:2b"
    assert payload["model_url"] == "http://localhost:11434"
    assert payload["facts"] == []
    assert captured["model_id"] == "gemma2:2b"
    assert captured["model_url"] == "http://localhost:11434"
