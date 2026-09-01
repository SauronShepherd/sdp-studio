# ADR-004: Python 3.12 and FastAPI backend

Status: Accepted

## Context

The server, compiler, Spark integration, CLI, and debugging services share a Python-heavy data-engineering ecosystem. The API needs typed REST/OpenAPI, async WebSockets, and a local/server deployment model without requiring a separate backend language.

## Alternatives considered

- Node/TypeScript backend colocated with the web client.
- JVM backend colocated with Spark.
- Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy 2, and asyncio boundaries.

## Decision

Use Python 3.12+ for backend/core packages and FastAPI for HTTP/WebSocket delivery. Core/compiler packages remain independent of FastAPI. Blocking subprocess/provider work is isolated from the event loop.

## Consequences

OpenAPI is generated from server contracts and the frontend client is generated from it. Business orchestration belongs in services, not route handlers. Production packages are covered by static typing and tests.

## Migration

Move legacy route-local orchestration into service modules incrementally while keeping endpoint contracts stable. Persistence changes use Alembic migrations.

## Rollback

A service extraction can be reverted behind the same API contract if it introduces regressions. Replacing the backend stack requires a superseding ADR because it affects packaging, plugins, runtimes, and migration tooling.
