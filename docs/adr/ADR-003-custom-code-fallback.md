# ADR-003: Lossless custom-code fallback

Status: Accepted

## Context

Python and SQL are more expressive than any finite visual operator catalog. A reverse compiler cannot safely represent every valid user edit. Silent normalization or source replacement would destroy trust and can change pipeline semantics.

## Alternatives considered

- Reject all unsupported source.
- Best-effort rewrite unsupported code into approximate visual operators.
- Preserve unsupported text exactly and reduce visual ownership at the smallest safe boundary.

## Decision

Unsupported or ambiguously changed code is preserved losslessly as a custom region or code-owned file. The compiler never overwrites code it cannot confidently round-trip. Imported Python is parsed, never executed merely for discovery.

## Consequences

Some graph sections may be navigable but not visually editable. Reconciliation reports ownership changes explicitly. Custom boundaries can limit preview, Row Trace, and schema inference and must surface structured problems rather than guessed behavior.

## Migration

Legacy generated regions receive ownership fingerprints/source maps when safely identifiable. Existing hand-written files default to code-owned until the importer proves a supported representation.

## Rollback

Rollback means restoring the previous ownership metadata while preserving source bytes. A rollback must never regenerate over a custom region unless the user explicitly converts it back to visual ownership.
