import csv
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import ijson
from tqdm import tqdm


PYPI_SIMPLE_INDEX_URL = "https://pypi.org/simple/"
ACCEPT_SIMPLE_JSON = "application/vnd.pypi.simple.v1+json"


def _iter_pypi_index_projects() -> Iterator[dict[str, Any]]:
    """Stream PyPI Simple API project entries one object at a time."""
    with httpx.stream(
        "GET",
        PYPI_SIMPLE_INDEX_URL,
        headers={"Accept": ACCEPT_SIMPLE_JSON},
        timeout=httpx.Timeout(60.0, read=300.0),
        follow_redirects=True,
    ) as response:
        response.raise_for_status()

        byte_stream = ijson.from_iter(response.iter_bytes(chunk_size=65_536))

        yield from ijson.items(byte_stream, "projects.item")


def main() -> None:
    """Retrieve and cache PyPI project index entries as CSV."""
    cache_file = (
        Path(__file__).resolve().parent
        / "cache"
        / "raw"
        / "pypi"
        / "pypi.simple.trimmed.csv"
    )
    cache_file.parent.mkdir(parents=True, exist_ok=True)

    with cache_file.open(mode="w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")

        writer.writerow(["name", "last_serial"])

        with tqdm(
            unit="packages",
            unit_scale=True,
            desc="Syncing PyPI index",
        ) as progress_bar:
            for project in _iter_pypi_index_projects():
                writer.writerow([project["name"], project.get("_last-serial", "")])
                progress_bar.update(1)


if __name__ == "__main__":
    main()
