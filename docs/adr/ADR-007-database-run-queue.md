# ADR-007: Database-backed run queue

Status: Accepted

## Context

SDP Studio needs durable run claiming, heartbeats, stale-claim recovery, scheduling, and restart reconciliation without making Redis a mandatory dependency.

## Alternatives considered

- In-memory worker queues.
- Mandatory Redis/Celery or another broker.
- Transactional database claims using PostgreSQL locking with a correct SQLite local fallback.

## Decision

Persist run state and worker claims in the application database. PostgreSQL uses transactional locking semantics suitable for concurrent workers; local SQLite uses a serialized fallback. Every state transition is persisted before terminal UI events are emitted.

## Consequences

Queue throughput is bounded by database design but operational complexity stays low. Stale claims and lost external runs must be reconciled explicitly rather than inferred as success/failure.

## Migration

Legacy in-process execution paths are wrapped by the durable run service and common runtime adapter boundary. Existing run rows are migrated before worker claims are enabled.

## Rollback

A worker release can be rolled back while preserving queued run records if schema compatibility is maintained. Never downgrade by deleting active claims; stop workers, reconcile runs, then restore compatible code/schema.
