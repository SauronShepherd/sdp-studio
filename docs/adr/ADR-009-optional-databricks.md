# ADR-009: Databricks as an optional provider adapter

Status: Accepted

## Context

Some users need Databricks interoperability, but the product must remain fully useful without Databricks credentials, SDKs, APIs, or provider-specific source constructs.

## Alternatives considered

- Make Databricks the primary runtime/control plane.
- Exclude Databricks entirely.
- Isolate Databricks in an optional adapter with explicit provider capabilities.

## Decision

Databricks is optional. Core/compiler packages do not depend on its SDK. Managed deployment, validation, update lifecycle, provider links, and provider-only capabilities are implemented behind the common runtime contract and optional dependency extra.

## Consequences

Normal CI uses mocked adapter contracts; live qualification is environment-backed and fail-closed for release environments that claim support. Portable OSS graphs remain runnable without source rewrites.

## Migration

Move any provider-specific imports/configuration out of core/server startup paths and map provider lifecycle events to common run states.

## Rollback

Disable or omit the Databricks extra/adapter. Portable project documents and generated OSS source remain valid; provider deployment metadata can be ignored without mutating the graph.
