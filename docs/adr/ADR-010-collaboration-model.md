# ADR-010: Collaboration merge model

**Decision:** The target collaboration model is CRDT-based, while the current MVP uses optimistic revision locking as a transitional compatibility boundary.

**Consequences:** Durable Yjs update replay and browser offline recovery now cover
the MVP reconnect path. Full multi-device offline merge certification still
requires browser acceptance tests and persistence migration coverage before the
optimistic REST revision path can be removed.
