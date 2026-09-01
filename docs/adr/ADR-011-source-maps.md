# ADR-011: Source maps outside generated code

**Decision:** Source maps are persisted as project metadata where possible, keeping generated source readable and portable.

**Consequences:** Maps must include stable node/object identity and content hashes.
