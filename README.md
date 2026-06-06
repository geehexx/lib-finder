# lib-finder

Tools for collecting and caching package metadata from the Python Package Index.

## Current entry points

- `lib-finder`: synchronizes the PyPI Simple JSON index into SQLite by default.
- `data/sync.py`: compatibility wrapper around the same CLI.

## Usage

```bash
uv run lib-finder
uv run lib-finder --csv-export data/cache/raw/pypi/simple-projects.csv
uv run python data/sync.py --record-limit 100
```

The default database path is `data/cache/lib-finder.sqlite3`. The optional CSV export is a debug snapshot only and is not the canonical store.
