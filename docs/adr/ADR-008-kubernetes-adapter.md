# ADR-008: Native Apache Spark on Kubernetes adapter

Status: Accepted

## Context

Kubernetes is a core vendor-neutral production target. Requiring a proprietary control plane or a specific Spark operator would conflict with the run-anywhere goal.

## Alternatives considered

- Require a Kubernetes Spark operator.
- Use a provider-managed Spark service only.
- Submit through native Apache Spark Kubernetes semantics and treat operators as future plugins.

## Decision

The built-in Kubernetes adapter uses native Spark-on-Kubernetes submission, explicit namespace/service-account policy, artifact staging, pod lifecycle/log/event collection, and the common runtime adapter contract. Cluster-admin is not required.

## Consequences

Artifact locations must be reachable from driver/executor pods; local workstation paths cannot be assumed. Profiles are server-validated and secrets/kubeconfig content never reach the browser. Release qualification includes a live `kind` lifecycle gate.

## Migration

Existing command builders are consolidated behind the common adapter and profile validation contracts. Production-safe staging is introduced without changing portable graph semantics.

## Rollback

Disable the Kubernetes profile/adapter while retaining project source and local execution. Resource cleanup and external run reconciliation are required before reverting lifecycle changes.
