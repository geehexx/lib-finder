"""lib-finder package metadata."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("lib-finder")
except PackageNotFoundError:  # pragma: no cover - editable/dev install fallback
    __version__ = "0.0.0"

__all__ = ["__version__"]
