# ADR-009: Databricks is an optional provider adapter

**Decision:** Databricks support is isolated from the portable core and is never required for authoring or local operation.

**Consequences:** Provider credentials and behavior stay in the adapter package.
