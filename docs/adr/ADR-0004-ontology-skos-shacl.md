# ADR-0004: Ontology, SKOS, and SHACL

Status: Accepted

## Context

The project will eventually need machine-checkable semantics for package
features, evidence, and quality signals so retrieval and evaluation can operate
on stable concepts rather than informal labels.

## Decision

Model the ontology layer with SKOS concepts and validate structured outputs with
SHACL.

- Keep the ontology and validation layers separate from ingestion.
- Use RDFLib for RDF handling and pySHACL for validation.
- Treat ontology expansion as a later batch after the source, storage, and
  extraction boundaries are stable.

## Consequences

- Semantic labels become explicit and versionable.
- Validation can reject malformed structured facts before they contaminate the
  retrieval and scoring layers.
- The ontology work stays decoupled from the primary ingestion path.

