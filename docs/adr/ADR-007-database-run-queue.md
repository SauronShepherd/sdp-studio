# ADR-007: Database-backed run queue

**Decision:** Run scheduling and worker claiming use the database; Redis is not mandatory.

**Consequences:** Claim operations must be atomic and recover non-terminal work after restart.
