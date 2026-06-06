# lib-finder Pydantic Standardization Plan

> Superseded by [docs/architecture/LIB_FINDER_AGENT_REALIGNMENT_PLAN_FINAL_V3.md](/home/gxx/projects/lib-finder/docs/architecture/LIB_FINDER_AGENT_REALIGNMENT_PLAN_FINAL_V3.md) and archived in [`docs/archive/README.md`](/home/gxx/projects/lib-finder/docs/archive/README.md). Kept for historical context only.

Date: 2026-06-06
Scope: configuration, environment-variable loading, and model standardization

## Goal

Define a deliberate migration path toward `pydantic` and `pydantic-settings`
for configuration and schema-bearing models without forcing a blanket rewrite of
all dataclasses in the codebase.

The target is to make the configuration surface and externally meaningful record
contracts easier to validate, serialize, and document while leaving small internal
row carriers alone when dataclasses remain simpler.

## Current State

The repository already depends on `pydantic` and `pydantic-settings`, and the
implementation now uses Pydantic for the boundary-facing config, result, and
record models. The remaining non-model wrapper is the SQLite resource class.
The `src/lib_finder` package no longer contains dataclass-based models.

Environment variables are now loaded through a single `pydantic-settings`
model with the `LIB_FINDER_` prefix. This migration does not rely on implicit
`.env` file loading.

## Problem Statement

The current mix of dataclasses and ad hoc configuration access is acceptable for
the existing batch pipeline, but it creates three long-term issues:

1. configuration validation is scattered;
2. serialization boundaries are implicit instead of explicit;
3. environment-variable behavior is duplicated across the app surface.

That is fine for a prototype, but it becomes noisy as the pipeline grows and as
more commands or submodules need consistent settings behavior.

## Recommended Direction

### Config and env loading

Use a single `pydantic-settings` model as the source of truth for application
configuration and environment-variable loading.

The settings layer should:

- centralize env var parsing and defaults;
- expose a small, typed config object to the CLI and pipeline;
- keep shell/environment access out of deeper modules unless there is a real need.
- document the supported `LIB_FINDER_*` variables in the operator guide;
- keep `.env` loading explicit rather than automatic.

### Record and schema models

Use `pydantic.BaseModel` for objects that are:

- exchanged across module boundaries;
- serialized to JSON or persisted as structured records;
- worth validating at the boundary before they enter storage.

Keep plain classes or dataclasses only where they are:

- resource wrappers with non-model state;
- simpler than introducing a model with no extra validation value.

## Migration Order

1. Create a dedicated application settings model and move env loading into it.
2. Convert CLI-facing configuration objects to Pydantic models or model-adjacent
   wrappers. This step is already done for the current sync and qualification
   configs and results.
3. Convert external record contracts that cross module boundaries frequently.
   This step is now done for the PyPI parser and storage batch-result models.
4. Reassess remaining dataclasses one by one instead of bulk-rewriting them.

## Non-Goals

Do not:

- replace every dataclass in one sweep;
- introduce an ORM as part of this migration;
- add Pydantic where the existing dataclass is already simpler and stable;
- duplicate config parsing in multiple modules.

## Acceptance Criteria

This migration phase is complete when:

- application settings are centralized in one Pydantic settings object;
- environment-variable parsing is documented and no longer duplicated;
- the roadmap and README point readers to the standardization plan;
- the remaining non-model wrapper is explicitly justified;
- any future model conversions are incremental, tested, and justified by boundary value.
