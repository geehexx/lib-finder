# lib-finder

Tools for collecting and caching package metadata from the Python Package Index.

## Current entry points

- `lib-finder`: enriches package rows from SQLite by default.
- `lib-finder discover`: synchronizes the PyPI Simple JSON root into SQLite.
- `data/sync.py`: compatibility wrapper around the same CLI.

## Usage

```bash
uv run lib-finder
uv run lib-finder --package-name requests --package-name numpy
uv run lib-finder discover --csv-export data/cache/raw/pypi/simple-projects.csv
uv run python data/sync.py --record-limit 100
```

The default database path is `data/cache/lib-finder.sqlite3`. The optional CSV export is a debug snapshot only and is not the canonical store. Detail sync selects unenriched package rows from SQLite by default; pass package names positionally or `--all-packages` when you want a broader run.
