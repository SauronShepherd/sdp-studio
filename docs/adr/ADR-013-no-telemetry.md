# ADR-013: No mandatory remote telemetry

Status: Accepted

## Context

SDP Studio handles source code, schemas, runtime metadata, logs, and potentially sensitive data profiles. Mandatory analytics would create privacy and offline-use concerns and contradict the local-first product model.

## Alternatives considered

- Mandatory product analytics.
- Remote telemetry enabled by default with opt-out.
- Local observability by default; any future anonymous telemetry is explicit opt-in.

## Decision

The product makes no mandatory telemetry calls. OpenTelemetry and Prometheus instrumentation describe the SDP Studio service/runtime locally or to an operator-configured collector. Any future product analytics must be separately specified, off by default, documented, and consented to.

## Consequences

Operational metrics cannot depend on an OpenAI/vendor SaaS. Tests must ensure local/core workflows do not require network analytics endpoints.

## Migration

If an optional telemetry plugin is introduced, existing installations remain disabled unless an administrator opts in after upgrade.

## Rollback

Disable/remove the optional telemetry configuration/plugin; no project migration is required because telemetry state is not part of portable project documents.
