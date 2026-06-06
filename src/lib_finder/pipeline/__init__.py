"""Async sync pipelines for discovery, detail enrichment, and qualification."""

from __future__ import annotations

import asyncio

from .config import QualificationConfig, QualificationResult, SyncConfig, SyncResult
from .detail import run_detail_sync
from .discovery import run_discovery_sync
from .qualification import run_qualification_sync

__all__ = [
    "SyncConfig",
    "SyncResult",
    "QualificationConfig",
    "QualificationResult",
    "run_detail_sync",
    "run_discovery_sync",
    "run_qualification_sync",
    "run_sync",
]


def run_sync(config: SyncConfig) -> SyncResult:
    """Run the default detail-enrichment pipeline."""

    return asyncio.run(run_detail_sync(config))
