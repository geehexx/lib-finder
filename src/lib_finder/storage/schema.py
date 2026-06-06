"""SQLAlchemy Core schema for the `lib-finder` SQLite store."""

from __future__ import annotations

from sqlalchemy import Column, ForeignKey, Index, Integer, MetaData, Text, Table

metadata = MetaData()

index_runs = Table(
    "index_runs",
    metadata,
    Column("id", Text, primary_key=True),
    Column("source", Text, nullable=False),
    Column("mode", Text, nullable=False),
    Column("started_at", Text, nullable=False),
    Column("finished_at", Text),
    Column("status", Text, nullable=False),
    Column("root_last_serial", Integer),
    Column("records_seen", Integer, nullable=False, server_default="0"),
    Column("records_written", Integer, nullable=False, server_default="0"),
    Column("error_count", Integer, nullable=False, server_default="0"),
    Column("settings_json", Text, nullable=False),
)

packages = Table(
    "packages",
    metadata,
    Column("normalized_name", Text, primary_key=True),
    Column("raw_name", Text, nullable=False),
    Column("first_seen_at", Text, nullable=False),
    Column("last_seen_at", Text, nullable=False),
    Column("root_last_serial", Integer),
    Column("project_last_serial", Integer),
    Column("project_status", Text),
    Column("status_reason", Text),
    Column("suspicion_json", Text, nullable=False, server_default="'{}'"),
    Column(
        "qualification_state",
        Text,
        nullable=False,
        server_default="'discovered'",
    ),
    Column("qualification_reason", Text),
)

source_records = Table(
    "source_records",
    metadata,
    Column("id", Text, primary_key=True),
    Column("source", Text, nullable=False),
    Column("record_type", Text, nullable=False),
    Column("identity", Text, nullable=False),
    Column("fetched_at", Text, nullable=False),
    Column("etag", Text),
    Column("last_modified", Text),
    Column("serial", Integer),
    Column("payload_hash", Text, nullable=False),
    Column("raw_payload_json", Text, nullable=False),
    Column("normalized_name", Text, ForeignKey("packages.normalized_name")),
)

project_detail_snapshots = Table(
    "project_detail_snapshots",
    metadata,
    Column("id", Text, primary_key=True),
    Column(
        "normalized_name",
        Text,
        ForeignKey("packages.normalized_name"),
        nullable=False,
    ),
    Column("raw_name", Text, nullable=False),
    Column("fetched_at", Text, nullable=False),
    Column("detail_last_serial", Integer),
    Column("project_status", Text),
    Column("status_reason", Text),
    Column("payload_hash", Text, nullable=False),
    Column("raw_payload_json", Text, nullable=False),
)

project_versions = Table(
    "project_versions",
    metadata,
    Column(
        "normalized_name",
        Text,
        ForeignKey("packages.normalized_name"),
        primary_key=True,
    ),
    Column("version", Text, primary_key=True),
    Column("first_seen_at", Text, nullable=False),
    Column("last_seen_at", Text, nullable=False),
    Column(
        "snapshot_id", Text, ForeignKey("project_detail_snapshots.id"), nullable=False
    ),
)

project_artifacts = Table(
    "project_artifacts",
    metadata,
    Column(
        "normalized_name",
        Text,
        ForeignKey("packages.normalized_name"),
        primary_key=True,
    ),
    Column("filename", Text, primary_key=True),
    Column("version", Text),
    Column("url", Text, nullable=False),
    Column("size", Integer),
    Column("upload_time", Text),
    Column("requires_python", Text),
    Column("yanked", Integer, nullable=False, server_default="0"),
    Column("yanked_reason", Text),
    Column("hashes_json", Text, nullable=False, server_default="'{}'"),
    Column("core_metadata_json", Text, nullable=False, server_default="'null'"),
    Column("provenance", Text),
    Column("first_seen_at", Text, nullable=False),
    Column("last_seen_at", Text, nullable=False),
    Column(
        "snapshot_id", Text, ForeignKey("project_detail_snapshots.id"), nullable=False
    ),
)

package_adoption_rollups = Table(
    "package_adoption_rollups",
    metadata,
    Column(
        "normalized_name",
        Text,
        ForeignKey("packages.normalized_name"),
        primary_key=True,
    ),
    Column("raw_name", Text, nullable=False),
    Column("version_count", Integer, nullable=False),
    Column("artifact_count", Integer, nullable=False),
    Column("wheel_count", Integer, nullable=False),
    Column("sdist_count", Integer, nullable=False),
    Column("yanked_artifact_count", Integer, nullable=False),
    Column("latest_upload_time", Text),
    Column("latest_project_last_serial", Integer),
    Column("project_status", Text),
    Column("qualification_score", Integer, nullable=False),
    Column("qualification_state", Text, nullable=False),
    Column("qualification_reason", Text, nullable=False),
    Column("computed_at", Text, nullable=False),
)

stage_checkpoints = Table(
    "stage_checkpoints",
    metadata,
    Column("stage", Text, primary_key=True),
    Column("checkpoint_json", Text, nullable=False),
    Column("updated_at", Text, nullable=False),
)

failure_events = Table(
    "failure_events",
    metadata,
    Column("id", Text, primary_key=True),
    Column("run_id", Text, nullable=False),
    Column("stage", Text, nullable=False),
    Column("identity", Text),
    Column("error_type", Text, nullable=False),
    Column("error_message", Text, nullable=False),
    Column("occurred_at", Text, nullable=False),
    Column("retryable", Integer, nullable=False),
)

Index("idx_packages_status", packages.c.project_status)
Index("idx_packages_qualification_state", packages.c.qualification_state)
Index("idx_packages_last_serial", packages.c.root_last_serial)
Index("idx_packages_project_last_serial", packages.c.project_last_serial)
Index(
    "idx_source_records_identity",
    source_records.c.source,
    source_records.c.record_type,
    source_records.c.identity,
)
Index("idx_project_detail_snapshots_name", project_detail_snapshots.c.normalized_name)
Index(
    "idx_project_detail_snapshots_serial", project_detail_snapshots.c.detail_last_serial
)
Index("idx_project_versions_snapshot", project_versions.c.snapshot_id)
Index(
    "idx_project_artifacts_version",
    project_artifacts.c.normalized_name,
    project_artifacts.c.version,
)
Index(
    "idx_package_adoption_rollups_score", package_adoption_rollups.c.qualification_score
)
Index(
    "idx_package_adoption_rollups_state", package_adoption_rollups.c.qualification_state
)
