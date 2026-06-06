from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from .pipeline import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_DB_PATH,
    DEFAULT_DETAIL_CONCURRENCY,
    DEFAULT_QUEUE_SIZE,
    DEFAULT_READ_TIMEOUT,
    DEFAULT_REQUEST_TIMEOUT,
    SyncConfig,
    run_discovery_sync,
    run_sync,
)

app = typer.Typer(
    add_completion=False,
    help="Synchronize PyPI Simple metadata into SQLite.",
)


def _echo_result(result: object, *, database: Path) -> None:
    if not hasattr(result, "records_written"):
        raise TypeError("Unexpected sync result type")
    csv_export_path = getattr(result, "csv_export_path", None)
    message = f"synced {getattr(result, 'records_written')} records into {database}"
    if csv_export_path is not None:
        message += f" and {csv_export_path}"
    typer.echo(message)


@app.callback(invoke_without_command=True)
def _main(
    ctx: typer.Context,
    database: Annotated[
        Path,
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
    ] = DEFAULT_DB_PATH,
    csv_export: Annotated[
        Path | None,
        typer.Option(
            "--csv-export",
            help="Optional CSV export path for debug snapshots.",
        ),
    ] = None,
    package_names: Annotated[
        list[str],
        typer.Option(
            "--package-name",
            help="Optional package name to enrich. May be provided multiple times.",
        ),
    ] = [],
    all_packages: Annotated[
        bool,
        typer.Option(
            "--all-packages/--unenriched-only",
            help="Select all packages from SQLite instead of only unenriched rows.",
        ),
    ] = False,
    queue_size: Annotated[
        int,
        typer.Option(
            "--queue-size", min=1, help="Maximum buffered records between stages."
        ),
    ] = DEFAULT_QUEUE_SIZE,
    batch_size: Annotated[
        int,
        typer.Option(
            "--batch-size", min=1, help="Number of records written per SQLite batch."
        ),
    ] = DEFAULT_BATCH_SIZE,
    request_timeout: Annotated[
        float,
        typer.Option(
            "--request-timeout",
            min=0.1,
            help="Default HTTPX request timeout in seconds.",
        ),
    ] = DEFAULT_REQUEST_TIMEOUT,
    read_timeout: Annotated[
        float,
        typer.Option(
            "--read-timeout", min=0.1, help="Streaming read timeout in seconds."
        ),
    ] = DEFAULT_READ_TIMEOUT,
    detail_concurrency: Annotated[
        int,
        typer.Option(
            "--detail-concurrency",
            min=1,
            help="Maximum concurrent project-detail fetches.",
        ),
    ] = DEFAULT_DETAIL_CONCURRENCY,
    user_agent: Annotated[
        str,
        typer.Option("--user-agent", help="HTTP user agent string sent to PyPI."),
    ] = "lib-finder/0.1.0",
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

    config = SyncConfig(
        db_path=database,
        csv_export_path=csv_export,
        queue_size=queue_size,
        batch_size=batch_size,
        request_timeout=request_timeout,
        read_timeout=read_timeout,
        detail_concurrency=detail_concurrency,
        package_names=tuple(package_names),
        all_packages=all_packages,
        user_agent=user_agent,
        record_limit=record_limit,
    )
    result = run_sync(config)
    _echo_result(result, database=config.db_path)


@app.command("discover")
def discover(
    database: Annotated[
        Path,
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
    ] = DEFAULT_DB_PATH,
    csv_export: Annotated[
        Path | None,
        typer.Option(
            "--csv-export",
            help="Optional CSV export path for debug snapshots.",
        ),
    ] = None,
    queue_size: Annotated[
        int,
        typer.Option(
            "--queue-size", min=1, help="Maximum buffered records between stages."
        ),
    ] = DEFAULT_QUEUE_SIZE,
    batch_size: Annotated[
        int,
        typer.Option(
            "--batch-size", min=1, help="Number of records written per SQLite batch."
        ),
    ] = DEFAULT_BATCH_SIZE,
    request_timeout: Annotated[
        float,
        typer.Option(
            "--request-timeout",
            min=0.1,
            help="Default HTTPX request timeout in seconds.",
        ),
    ] = DEFAULT_REQUEST_TIMEOUT,
    read_timeout: Annotated[
        float,
        typer.Option(
            "--read-timeout", min=0.1, help="Streaming read timeout in seconds."
        ),
    ] = DEFAULT_READ_TIMEOUT,
    user_agent: Annotated[
        str,
        typer.Option("--user-agent", help="HTTP user agent string sent to PyPI."),
    ] = "lib-finder/0.1.0",
    record_limit: Annotated[
        int | None,
        typer.Option(
            "--record-limit",
            min=1,
            help="Stop after this many project records. Useful for smoke tests.",
        ),
    ] = None,
) -> None:
    config = SyncConfig(
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


def main() -> None:
    app()
