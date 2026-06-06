"""Typer CLI for PyPI discovery, detail sync, and rollup backfills."""

from __future__ import annotations

import json
from importlib import import_module
from pathlib import Path
from typing import Annotated

import typer  # pyright: ignore[reportMissingImports]

from .config import build_qualification_config, build_sync_config
from .pipeline import run_qualification_sync, run_discovery_sync, run_sync
from .settings import LibFinderSettings

LibFinderSettings.model_rebuild(_types_namespace={"Path": Path})

app = typer.Typer(
    add_completion=False,
    help="Synchronize PyPI Simple metadata into SQLite.",
)


def _echo_result(result: object, *, database: Path) -> None:
    if not hasattr(result, "records_written"):
        raise TypeError("Unexpected sync result type")
    qualified_count = getattr(result, "qualified_count", None)
    csv_export_path = getattr(result, "csv_export_path", None)
    if qualified_count is not None:
        typer.echo(
            f"refreshed {getattr(result, 'records_written')} rollups in {database} "
            f"({qualified_count} qualified)"
        )
        return

    message = f"synced {getattr(result, 'records_written')} records into {database}"
    if csv_export_path is not None:
        message += f" and {csv_export_path}"
    typer.echo(message)


def _echo_extraction_result(result: object) -> None:
    typer.echo(
        json.dumps(
            result.model_dump(mode="json"),  # type: ignore[attr-defined]
            sort_keys=True,
            separators=(",", ":"),
        )
    )


@app.callback(invoke_without_command=True)
def _main(
    ctx: typer.Context,
    database: Annotated[
        Path | None,
        typer.Option(
            "--database",
            "-d",
            file_okay=True,
            dir_okay=False,
            writable=True,
            readable=False,
            resolve_path=False,
            help="Path to the SQLite database file.",
        ),
    ] = None,
    csv_export: Annotated[
        Path | None,
        typer.Option(
            "--csv-export",
            help="Optional CSV export path for debug snapshots.",
        ),
    ] = None,
    package_names: Annotated[
        list[str] | None,
        typer.Option(
            "--package-name",
            help="Optional package name to enrich. May be provided multiple times.",
        ),
    ] = None,
    all_packages: Annotated[
        bool | None,
        typer.Option(
            "--all-packages/--unenriched-only",
            help="Select all packages from SQLite instead of only unenriched rows.",
        ),
    ] = None,
    queue_size: Annotated[
        int | None,
        typer.Option(
            "--queue-size", min=1, help="Maximum buffered records between stages."
        ),
    ] = None,
    batch_size: Annotated[
        int | None,
        typer.Option(
            "--batch-size", min=1, help="Number of records written per SQLite batch."
        ),
    ] = None,
    request_timeout: Annotated[
        float | None,
        typer.Option(
            "--request-timeout",
            min=0.1,
            help="Default HTTPX request timeout in seconds.",
        ),
    ] = None,
    read_timeout: Annotated[
        float | None,
        typer.Option(
            "--read-timeout", min=0.1, help="Streaming read timeout in seconds."
        ),
    ] = None,
    detail_concurrency: Annotated[
        int | None,
        typer.Option(
            "--detail-concurrency",
            min=1,
            help="Maximum concurrent project-detail fetches.",
        ),
    ] = None,
    user_agent: Annotated[
        str | None,
        typer.Option("--user-agent", help="HTTP user agent string sent to PyPI."),
    ] = None,
    record_limit: Annotated[
        int | None,
        typer.Option(
            "--record-limit",
            min=1,
            help="Stop after this many records. Useful for smoke tests.",
        ),
    ] = None,
) -> None:
    if ctx.resilient_parsing or ctx.invoked_subcommand is not None:
        return

    settings = LibFinderSettings()
    config = build_sync_config(
        settings,
        db_path=database,
        csv_export_path=csv_export,
        package_names=None if package_names is None else tuple(package_names),
        all_packages=all_packages,
        queue_size=queue_size,
        batch_size=batch_size,
        request_timeout=request_timeout,
        read_timeout=read_timeout,
        detail_concurrency=detail_concurrency,
        user_agent=user_agent,
        record_limit=record_limit,
    )
    result = run_sync(config)
    _echo_result(result, database=config.db_path)


@app.command("discover")
def discover(
    database: Annotated[
        Path | None,
        typer.Option(
            "--database",
            "-d",
            file_okay=True,
            dir_okay=False,
            writable=True,
            readable=False,
            resolve_path=False,
            help="Path to the SQLite database file.",
        ),
    ] = None,
    csv_export: Annotated[
        Path | None,
        typer.Option(
            "--csv-export",
            help="Optional CSV export path for debug snapshots.",
        ),
    ] = None,
    queue_size: Annotated[
        int | None,
        typer.Option(
            "--queue-size", min=1, help="Maximum buffered records between stages."
        ),
    ] = None,
    batch_size: Annotated[
        int | None,
        typer.Option(
            "--batch-size", min=1, help="Number of records written per SQLite batch."
        ),
    ] = None,
    request_timeout: Annotated[
        float | None,
        typer.Option(
            "--request-timeout",
            min=0.1,
            help="Default HTTPX request timeout in seconds.",
        ),
    ] = None,
    read_timeout: Annotated[
        float | None,
        typer.Option(
            "--read-timeout", min=0.1, help="Streaming read timeout in seconds."
        ),
    ] = None,
    user_agent: Annotated[
        str | None,
        typer.Option("--user-agent", help="HTTP user agent string sent to PyPI."),
    ] = None,
    record_limit: Annotated[
        int | None,
        typer.Option(
            "--record-limit",
            min=1,
            help="Stop after this many project records. Useful for smoke tests.",
        ),
    ] = None,
) -> None:
    """Synchronize the PyPI Simple root into SQLite."""

    settings = LibFinderSettings()
    config = build_sync_config(
        settings,
        db_path=database,
        csv_export_path=csv_export,
        queue_size=queue_size,
        batch_size=batch_size,
        request_timeout=request_timeout,
        read_timeout=read_timeout,
        user_agent=user_agent,
        record_limit=record_limit,
    )
    result = run_discovery_sync(config)
    _echo_result(result, database=config.db_path)


@app.command("qualify")
def qualify(
    database: Annotated[
        Path | None,
        typer.Option(
            "--database",
            "-d",
            file_okay=True,
            dir_okay=False,
            writable=True,
            readable=False,
            resolve_path=False,
            help="Path to the SQLite database file.",
        ),
    ] = None,
    package_names: Annotated[
        list[str] | None,
        typer.Option(
            "--package-name",
            help="Optional package name to refresh. May be provided multiple times.",
        ),
    ] = None,
    record_limit: Annotated[
        int | None,
        typer.Option(
            "--record-limit",
            min=1,
            help="Stop after this many SQLite-selected packages.",
        ),
    ] = None,
) -> None:
    """Recompute adoption rollups from the SQLite store."""

    settings = LibFinderSettings()
    config = build_qualification_config(
        settings,
        db_path=database,
        package_names=None if package_names is None else tuple(package_names),
        record_limit=record_limit,
    )
    result = run_qualification_sync(config)
    _echo_result(result, database=config.db_path)


@app.command("extract")
def extract(
    text: Annotated[
        str | None,
        typer.Option("--text", help="Raw text to extract facts from."),
    ] = None,
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
    """Extract grounded package facts from raw text."""

    settings = LibFinderSettings()
    if text is None and text_file is None:
        raise typer.BadParameter("Provide --text or --text-file.")
    if text_file is not None:
        raw_text = text if text is not None else text_file.read_text(encoding="utf-8")
        source_id = text_file.name
    else:
        raw_text = text or ""
        source_id = "stdin"
    extraction = import_module("lib_finder.extraction")

    result = extraction.run_text_extraction(
        extraction.ExtractionSourceDocument(
            source_id=f"cli:{source_id}",
            title=source_id,
            text=raw_text,
        ),
        model_id=settings.extraction_model_id if model_id is None else model_id,
        model_url=settings.extraction_model_url if model_url is None else model_url,
    )
    _echo_extraction_result(result)


def main() -> None:
    """Run the Typer application."""

    app()
