# ADR-011: External deterministic source maps

Status: Accepted

## Context

Node-to-code navigation, diagnostic mapping, semantic diffs, and debugging require precise ownership ranges. Polluting generated code with many required comments harms readability and makes markers part of runtime behavior.

## Alternatives considered

- Encode all ownership in generated comments.
- Infer ownership from source text after generation.
- Persist formatter-stable source maps under `.sdpstudio/source-maps` with minimal optional boundary markers.

## Decision

Source maps are external generated artifacts containing visual node id, distinct IR identity, precise line/column ranges, and generated content hash. Minimal region comments are permitted only when needed for robust round-trip ownership and are never semantically required at runtime.

## Consequences

Maps must be computed after final formatting and regenerated deterministically. Stale hash mismatches invalidate navigation/ownership assumptions until reconciliation runs.

## Migration

Existing generated files receive maps during regeneration without changing source when possible. Legacy markers can be retained until equivalent ownership fingerprints are verified.

## Rollback

Delete/regenerate source maps from authoritative graph/source state. Never use an old map against a mismatched file hash.
