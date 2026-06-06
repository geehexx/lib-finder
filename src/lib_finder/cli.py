from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from .pipeline import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_DB_PATH,
    DEFAULT_QUEUE_SIZE,
    DEFAULT_READ_TIMEOUT,
    DEFAULT_REQUEST_TIMEOUT,
    SyncConfig,
    run_sync,
)

app = typer.Typer(add_completion=False, help="Synchronize PyPI Simple metadata into SQLite.")


@app.callback(invoke_without_command=True)
def _main(
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
        typer.Option("--queue-size", min=1, help="Maximum buffered records between stages."),
    ] = DEFAULT_QUEUE_SIZE,
    batch_size: Annotated[
        int,
        typer.Option("--batch-size", min=1, help="Number of records written per SQLite batch."),
    ] = DEFAULT_BATCH_SIZE,
    request_timeout: Annotated[
        float,
        typer.Option("--request-timeout", min=0.1, help="Default HTTPX request timeout in seconds."),
    ] = DEFAULT_REQUEST_TIMEOUT,
    read_timeout: Annotated[
        float,
        typer.Option("--read-timeout", min=0.1, help="Streaming read timeout in seconds."),
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
    result = run_sync(config)
    typer.echo(
        f"synced {result.records_written} records into {config.db_path}"
        + (f" and {result.csv_export_path}" if result.csv_export_path else "")
    )


def main() -> None:
    app()
