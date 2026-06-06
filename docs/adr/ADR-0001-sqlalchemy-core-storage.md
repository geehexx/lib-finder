# ADR-0001: SQLAlchemy Core Storage

Status: Accepted

## Context

`lib-finder` needs durable SQLite persistence for discovery, detail enrichment,
rollups, checkpoints, and failure tracking. The previous flat sqlite3 wrapper was
too hard to evolve safely as the schema and query surface grew.

## Decision

Use SQLAlchemy Core as the schema and execution layer for repository code.

- Keep SQLite as the local persistence backend.
- Model the schema with `MetaData`, `Table`, `Column`, and indexes.
- Use Alembic for schema bootstrap and future migrations.
- Avoid SQLAlchemy ORM for this project.

## Consequences

- Storage logic gains explicit schema objects and safer SQL composition.
- SQLite pragmas and connection policy stay under application control.
- Future schema changes can be versioned instead of being hidden in ad hoc DDL.
- The repository keeps a small, testable storage boundary without introducing ORM overhead.

