# ADR-002: Visual model plus executable source as dual durable representations

Status: Accepted

## Context

A visual-only project format would hide implementation details and create lock-in, while source-only authoring would prevent reliable visual ownership, layout, and operator metadata. Users must be able to review ordinary Python/SQL and the visual graph in Git.

## Alternatives considered

- Persist only a proprietary visual graph and generate source on demand.
- Persist only source and reconstruct the full visual graph on every load.
- Persist versioned `.sdpstudio` documents and ordinary executable source together.

## Decision

Both the visual model and executable Python/SQL are committed by default. Visual-owned regions are authoritative for supported operators; code-owned/custom regions are authoritative for unsupported user code. Source maps and ownership fingerprints connect both representations.

## Consequences

Generation must be deterministic, reconciliation must run before destructive writes, and Git diffs can show semantic graph changes beside source changes. Persisted schemas require explicit versioning and migration.

## Migration

Projects that contain source only can be imported without rewriting source. `.sdpstudio` metadata is added separately and reconstructed graph ownership is conservative.

## Rollback

If a visual schema migration fails, restore the pre-migration backup and keep executable source untouched. If reconciliation becomes ambiguous, downgrade the affected region/file to code-owned rather than discarding source.
