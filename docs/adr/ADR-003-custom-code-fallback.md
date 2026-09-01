# ADR-003: Lossless custom-code fallback

**Decision:** Unsupported user code is preserved losslessly rather than reverse-compiled speculatively.

**Consequences:** Code-owned regions require hashes and explicit reconciliation before overwrite.
