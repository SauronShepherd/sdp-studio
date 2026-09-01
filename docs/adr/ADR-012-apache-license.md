# ADR-012: Apache License 2.0 single upstream edition

Status: Accepted

## Context

SDP Studio is intended to be a serious open-source engineering product whose core capabilities are not reserved for a proprietary edition.

## Alternatives considered

- Copyleft licensing.
- Open-core licensing with proprietary collaboration/debug/runtime features.
- Apache License 2.0 for project-owned code with automated third-party license governance.

## Decision

Project-owned source is Apache-2.0 and there is one upstream feature-complete edition. Core visual design, compiler, debugging, Git, collaboration, auth, scheduling, runtimes, plugin SDK, CLI, and deployment manifests remain open source.

## Consequences

Dependencies are inventoried and license-gated; incompatible licenses are rejected or isolated as external optional systems. Releases include LICENSE, NOTICE, third-party notices, SBOMs, and provenance evidence.

## Migration

New dependencies require license review and notice updates. Existing dependency inventories are reconciled by CI before release.

## Rollback

Remove or replace an incompatible dependency while preserving public APIs where practical. Changing the project license or moving core features proprietary requires governance approval and a superseding ADR.
