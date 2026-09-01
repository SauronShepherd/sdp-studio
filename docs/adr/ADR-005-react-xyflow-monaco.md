# ADR-005: React, TypeScript, XYFlow, and Monaco frontend

Status: Accepted

## Context

The production IDE requires a scalable graph canvas, schema-driven inspector, project editor, semantic navigation, collaboration, accessibility, and rich debugging views. The original dependency-light prototype cannot be the long-term production UI.

## Alternatives considered

- Continue the handwritten HTML/JavaScript prototype.
- Use a full-stack SSR React framework.
- Use React + TypeScript + Vite, XYFlow for the canvas, Monaco for code, and generated API types.

## Decision

The supported frontend is a React/TypeScript SPA built with Vite. XYFlow is a rendering/interaction adapter over the domain graph; it is not the persisted semantic model. Monaco is the code editor. Server DTOs come from generated OpenAPI artifacts.

## Consequences

Canvas state must translate to/from versioned domain documents. Expensive layout/diff work can move to Web Workers. Browser E2E and accessibility tests qualify the production UI. The legacy UI is not maintained as a second product after parity.

## Migration

Reimplement workflows by vertical slice, preserving backend APIs and persisted documents. Remove legacy surfaces only after equivalent React flows pass regression tests.

## Rollback

Individual feature migrations can temporarily fall back to the last working React implementation, but the architecture does not roll back to a permanent dual-frontend model. A replacement frontend stack requires a new ADR and migration plan.
