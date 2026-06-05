# lib-finder

Tools for collecting and caching package metadata from the Python Package Index.

## Current entry points

- `lib-finder`: placeholder CLI entry point for the package.
- `data/sync.py`: streams the PyPI Simple API into `data/cache/raw/pypi/pypi.simple.trimmed.csv`.

## Usage

```bash
uv run lib-finder
uv run python data/sync.py
```
