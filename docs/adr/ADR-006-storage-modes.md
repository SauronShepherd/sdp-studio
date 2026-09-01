# ADR-006: SQLite local mode and PostgreSQL team mode

Status: Accepted

## Context

Local use should require no external database, while team mode needs transactional multi-user persistence and durable worker/scheduler claims. Maintaining unrelated schema implementations would create drift.

## Alternatives considered

- PostgreSQL for every installation.
- SQLite for every installation.
- SQLAlchemy 2 async with Alembic-managed schemas for SQLite and PostgreSQL.

## Decision

Use SQLite WAL for local mode and PostgreSQL 16+ for team mode behind the same SQLAlchemy models/services. Alembic is authoritative for persistent schema evolution.

## Consequences

Database behavior must be tested on migration boundaries and concurrency-sensitive code must have explicit SQLite fallbacks. Application startup must not create a divergent production schema outside migration policy.

## Migration

Existing local databases are upgraded by ordered Alembic revisions. Team deployments back up PostgreSQL before upgrades and run migrations as an explicit deployment step.

## Rollback

Prefer restore-from-backup for destructive or non-reversible migrations. Reversible Alembic downgrades may be supplied when safe, but rollback procedures must document data-loss limits.
