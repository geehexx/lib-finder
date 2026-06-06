from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
import ijson
from packaging.utils import canonicalize_name

PYPI_SIMPLE_INDEX_URL = "https://pypi.org/simple/"
PYPI_SIMPLE_ACCEPT = "application/vnd.pypi.simple.v1+json"
DEFAULT_USER_AGENT = "lib-finder/0.1.0"


@dataclass(slots=True, frozen=True)
class ProjectDiscoveryRecord:
    raw_name: str
    normalized_name: str
    root_last_serial: int | None
    fetched_at: str
    suspicion: dict[str, Any]
    raw_payload_json: str
    payload_hash: str

    @property
    def source(self) -> str:
        return "pypi_simple_root"

    @property
    def record_type(self) -> str:
        return "project_discovery"

    @property
    def identity(self) -> str:
        return self.normalized_name


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _parse_last_serial(value: str | None) -> int | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _canonical_payload_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _payload_hash(payload_json: str) -> str:
    return hashlib.sha256(payload_json.encode("utf-8")).hexdigest()


def _shannon_entropy(text: str) -> float:
    if not text:
        return 0.0
    counts = Counter(text.lower())
    total = len(text)
    return -sum((count / total) * math.log2(count / total) for count in counts.values())


def _suspicion_features(raw_name: str, normalized_name: str) -> dict[str, Any]:
    length = len(raw_name)
    digit_count = sum(character.isdigit() for character in raw_name)
    separator_count = sum(character in "-_." for character in raw_name)
    lower_name = raw_name.lower()
    repeated_markers = ("--", "__", "..", "-.", ".-", "_.", "._")

    return {
        "length": length,
        "digit_count": digit_count,
        "digit_ratio": digit_count / length if length else 0.0,
        "separator_count": separator_count,
        "separator_ratio": separator_count / length if length else 0.0,
        "has_repeated_separator": any(marker in raw_name for marker in repeated_markers),
        "has_mixed_case": any(character.islower() for character in raw_name)
        and any(character.isupper() for character in raw_name),
        "starts_with_separator": raw_name[:1] in "-_.",
        "ends_with_separator": raw_name[-1:] in "-_.",
        "starts_with_digit": raw_name[:1].isdigit(),
        "ends_with_digit": raw_name[-1:].isdigit(),
        "unique_char_ratio": len(set(lower_name)) / length if length else 0.0,
        "shannon_entropy": _shannon_entropy(raw_name),
        "normalized_differs": normalized_name != raw_name,
    }


def build_project_discovery_record(
    payload: Mapping[str, Any],
    *,
    root_last_serial: int | None,
    fetched_at: str,
) -> ProjectDiscoveryRecord:
    raw_name = payload.get("name")
    if not isinstance(raw_name, str) or not raw_name.strip():
        raise ValueError("PyPI project entry is missing a valid name")

    normalized_name = canonicalize_name(raw_name)
    raw_payload_json = _canonical_payload_json(payload)
    payload_hash = _payload_hash(raw_payload_json)

    return ProjectDiscoveryRecord(
        raw_name=raw_name,
        normalized_name=normalized_name,
        root_last_serial=root_last_serial,
        fetched_at=fetched_at,
        suspicion=_suspicion_features(raw_name, normalized_name),
        raw_payload_json=raw_payload_json,
        payload_hash=payload_hash,
    )


async def iter_root_project_records(
    client: httpx.AsyncClient,
) -> AsyncIterator[ProjectDiscoveryRecord]:
    async with client.stream(
        "GET",
        PYPI_SIMPLE_INDEX_URL,
        headers={"Accept": PYPI_SIMPLE_ACCEPT},
        follow_redirects=True,
    ) as response:
        response.raise_for_status()
        root_last_serial = _parse_last_serial(response.headers.get("X-PyPI-Last-Serial"))
        async for record in iter_root_project_records_from_response(
            response,
            root_last_serial=root_last_serial,
        ):
            yield record


async def iter_root_project_records_from_response(
    response: httpx.Response,
    *,
    root_last_serial: int | None,
) -> AsyncIterator[ProjectDiscoveryRecord]:
    fetched_at = _iso_now()
    stream = ijson.from_iter(response.aiter_bytes(chunk_size=64 * 1024))

    async for payload in ijson.items(stream, "projects.item"):
        if not isinstance(payload, Mapping):
            raise TypeError("Unexpected PyPI Simple project payload type")
        yield build_project_discovery_record(
            payload,
            root_last_serial=root_last_serial,
            fetched_at=fetched_at,
        )
