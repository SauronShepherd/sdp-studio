# ADR-008: Native Spark-on-Kubernetes adapter

**Decision:** Kubernetes execution is integrated through native command-array lifecycle operations.

**Consequences:** The adapter must report common probe, run, cancellation, status, and artifact contracts.
