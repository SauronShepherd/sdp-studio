# ADR-001: Apache Spark Declarative Pipelines as the execution contract

Status: Accepted

## Context

SDP Studio needs one portable semantic baseline for code generation, validation, runtime capability checks, and debugging. Provider-specific pipeline products can expose useful extensions, but making any provider the semantic authority would create lock-in and make local OSS execution secondary.

## Alternatives considered

- Treat a managed provider API as the primary execution model.
- Treat generic Spark DataFrame jobs as the primary model and emulate SDP features.
- Use Apache Spark Declarative Pipelines (SDP) as the normative execution contract and layer provider extensions behind capabilities.

## Decision

Apache Spark SDP is the core execution contract. The canonical IR, compiler, runtime requests, and compatibility engine model Apache Spark SDP semantics first. Provider-only behavior is optional, capability-gated, visibly marked, and isolated from `sdpstudio_core`.

## Consequences

Local Apache Spark must remain a first-class path. Runtime adapters must probe capabilities instead of inferring support from provider names. Portable mode must never silently emit provider-only syntax.

## Migration

Existing direct command/code paths are migrated behind the canonical IR and common runtime adapter contracts without changing generated output unless a semantic defect is fixed. Provider integrations are moved to optional packages or adapter modules.

## Rollback

If Apache Spark changes or removes an SDP surface, retain the last supported compatibility profile while introducing a new versioned capability mapping. Do not switch the product wholesale to a proprietary execution contract; any such change requires a superseding ADR and specification revision.
