# ADR-010: CRDT collaboration with serialized repository mutations

Status: Accepted

## Context

Team users need concurrent graph/text editing, reconnect recovery, presence, and durable updates. Git operations such as checkout/pull can rewrite many files and cannot safely race live collaborative buffers.

## Alternatives considered

- Last-write-wins optimistic saves only.
- Operational transformation implemented in-house.
- Yjs-compatible CRDT document state plus server persistence and explicit Git coordination.

## Decision

Collaborative documents use CRDT semantics for graph/config/text state. Awareness/presence is ephemeral; document updates are durable. Destructive repository mutations acquire a server-side project lock, flush collaborative state, snapshot history, perform Git, reload/reconcile documents, broadcast the result, then release the lock.

## Consequences

Field-level graph updates should avoid replacing whole nodes so concurrent edits merge without data loss. Multi-replica deployment requires shared session/pub-sub state before it is claimed as supported.

## Migration

Existing optimistic documents can initialize CRDT state from their latest durable revision. Git workflows migrate to the coordinated repository-operation service.

## Rollback

Disable collaborative editing and fall back to single-writer optimistic concurrency only after persisting a final snapshot. Never discard unmerged CRDT updates during rollback.
