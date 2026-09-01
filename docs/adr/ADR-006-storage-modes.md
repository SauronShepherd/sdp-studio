# ADR-006: SQLite local and PostgreSQL team storage

**Decision:** SQLite is the zero-configuration local store; PostgreSQL is the shared deployment store.

**Consequences:** Schema changes require migrations and authentication is mandatory for remote deployment.
