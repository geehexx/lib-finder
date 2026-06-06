"""PyPI Simple payload parsers and normalized record builders."""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from collections.abc import Mapping
from typing import Any

from .models import ProjectDetailRecord, ProjectDiscoveryRecord, ProjectFileRecord


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
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )


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
        "has_repeated_separator": any(
            marker in raw_name for marker in repeated_markers
        ),
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


def _require_string(value: Any, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"PyPI Simple payload field '{field_name}' must be a string")
    return value


def _require_nonempty_string(value: Any, *, field_name: str) -> str:
    string_value = _require_string(value, field_name=field_name)
    if not string_value.strip():
        raise ValueError(f"PyPI Simple payload field '{field_name}' must not be empty")
    return string_value


def _parse_optional_serial(value: Any, *, field_name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        serial = _parse_last_serial(value)
        if serial is not None:
            return serial
    raise TypeError(
        f"PyPI Simple payload field '{field_name}' must be an integer serial"
    )


def _parse_serial_from_payload(payload: Mapping[str, Any]) -> int | None:
    serial = _parse_optional_serial(
        payload.get("_last-serial"), field_name="_last-serial"
    )
    if serial is not None:
        return serial
    meta = payload.get("meta")
    if isinstance(meta, Mapping):
        serial = _parse_optional_serial(
            meta.get("_last-serial"), field_name="meta._last-serial"
        )
        if serial is not None:
            return serial
    return None


def _normalize_string_mapping(
    value: Mapping[str, Any],
    *,
    field_name: str,
    lower_keys: bool = True,
) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for key, raw_value in value.items():
        if not isinstance(key, str) or not key.strip():
            raise TypeError(
                f"PyPI Simple payload field '{field_name}' must map string keys to strings"
            )
        string_value = _require_string(raw_value, field_name=f"{field_name}.{key}")
        parsed[key.lower() if lower_keys else key] = string_value
    return parsed


def _parse_optional_string(value: Any, *, field_name: str) -> str | None:
    if value is None:
        return None
    return _require_string(value, field_name=field_name)


def _parse_optional_string_or_bool_or_mapping(
    value: Any,
    *,
    field_name: str,
) -> bool | dict[str, str] | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, Mapping):
        return _normalize_string_mapping(value, field_name=field_name)
    raise TypeError(
        f"PyPI Simple payload field '{field_name}' must be a bool or mapping of strings"
    )


def _parse_yanked(value: Any) -> bool | str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        if not value:
            raise ValueError(
                "PyPI Simple payload field 'yanked' must not be empty when present"
            )
        return value
    raise TypeError("PyPI Simple payload field 'yanked' must be a bool or string")


def _build_project_file_record(payload: Mapping[str, Any]) -> ProjectFileRecord:
    filename = _require_nonempty_string(payload.get("filename"), field_name="filename")
    url = _require_nonempty_string(payload.get("url"), field_name="url")
    hashes_value = payload.get("hashes")
    if not isinstance(hashes_value, Mapping):
        raise TypeError("PyPI Simple payload field 'hashes' must be a mapping")

    core_metadata = _parse_optional_string_or_bool_or_mapping(
        payload.get("core-metadata"),
        field_name="core-metadata",
    )
    dist_info_metadata = _parse_optional_string_or_bool_or_mapping(
        payload.get("dist-info-metadata"),
        field_name="dist-info-metadata",
    )
    if core_metadata is None and dist_info_metadata is not None:
        core_metadata = dist_info_metadata

    return ProjectFileRecord(
        filename=filename,
        url=url,
        hashes=_normalize_string_mapping(hashes_value, field_name="hashes"),
        size=_parse_int(payload.get("size"), field_name="size"),
        upload_time=_parse_optional_string(
            payload.get("upload-time"), field_name="upload-time"
        ),
        requires_python=_parse_optional_string(
            payload.get("requires-python"),
            field_name="requires-python",
        ),
        core_metadata=core_metadata,
        dist_info_metadata=dist_info_metadata,
        provenance=_parse_optional_string(
            payload.get("provenance"), field_name="provenance"
        ),
        yanked=_parse_yanked(payload.get("yanked")),
    )


def _parse_int(value: Any, *, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"PyPI Simple payload field '{field_name}' must be an integer")
    return value


def _parse_versions(payload: Mapping[str, Any]) -> tuple[str, ...]:
    versions_value = payload.get("versions")
    if versions_value is None:
        return ()
    if not isinstance(versions_value, list):
        raise TypeError("PyPI Simple payload field 'versions' must be a list")
    versions: list[str] = []
    seen: set[str] = set()
    for index, version in enumerate(versions_value):
        string_version = _require_string(version, field_name=f"versions[{index}]")
        if string_version not in seen:
            seen.add(string_version)
            versions.append(string_version)
    return tuple(versions)


def _parse_meta_api_version(payload: Mapping[str, Any]) -> str | None:
    meta_value = payload.get("meta")
    if not isinstance(meta_value, Mapping):
        return None
    api_version = meta_value.get("api-version")
    if api_version is None:
        return None
    return _require_string(api_version, field_name="meta.api-version")


def build_project_discovery_record(
    payload: Mapping[str, Any],
    *,
    root_last_serial: int | None,
    fetched_at: str,
) -> ProjectDiscoveryRecord:
    """Build a discovery record from a PyPI Simple root payload."""

    from .factories import DEFAULT_PYPI_RECORD_FACTORY

    return DEFAULT_PYPI_RECORD_FACTORY.build_project_discovery_record(
        payload,
        root_last_serial=root_last_serial,
        fetched_at=fetched_at,
    )


def build_project_detail_record(
    payload: Mapping[str, Any],
    *,
    raw_name: str,
    root_last_serial: int | None,
    fetched_at: str,
    project_last_serial: int | None = None,
) -> ProjectDetailRecord:
    """Build a detail record from a PyPI Simple project payload."""

    from .factories import DEFAULT_PYPI_RECORD_FACTORY

    return DEFAULT_PYPI_RECORD_FACTORY.build_project_detail_record(
        payload,
        raw_name=raw_name,
        root_last_serial=root_last_serial,
        fetched_at=fetched_at,
        project_last_serial=project_last_serial,
    )


def _parse_files(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    files_value = payload.get("files")
    if files_value is None:
        return []
    if not isinstance(files_value, list):
        raise TypeError("PyPI Simple payload field 'files' must be a list")
    parsed_files: list[Mapping[str, Any]] = []
    for index, file_payload in enumerate(files_value):
        if not isinstance(file_payload, Mapping):
            raise TypeError(
                f"PyPI Simple payload field 'files[{index}]' must be a mapping"
            )
        parsed_files.append(file_payload)
    return parsed_files


__all__ = [
    "build_project_discovery_record",
    "build_project_detail_record",
]
