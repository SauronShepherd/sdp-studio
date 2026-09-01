# ADR-014: Trademark-safe product naming

Status: Accepted

## Context

Apache Spark is an ASF trademark. SDP Studio must describe compatibility without implying that the third-party product is an official Apache Spark distribution or endorsed project.

## Alternatives considered

- Include `Spark` directly in the product name.
- Avoid mentioning Apache Spark publicly.
- Keep the product name `SDP Studio` and use `for Apache Spark` / `Apache Spark Declarative Pipelines` descriptively.

## Decision

The product name is **SDP Studio**. Public descriptions may say `SDP Studio — Visual IDE for Apache Spark Declarative Pipelines` and similar factual compatibility language. Do not rename the product to `Spark SDP Studio`, `Spark Visual Pipelines`, or another name that embeds the mark as product branding. `TRADEMARKS.md` is the repository policy for attribution and downstream naming.

## Consequences

Release, website, package, image, chart, screenshots, and documentation naming are reviewed for misleading endorsement. Compatibility claims are tied to qualified runtime versions/capabilities.

## Migration

Legacy names are removed from source, docs, package metadata, remote configuration, and generated artifacts with deterministic audit checks.

## Rollback

Brand rollback may restore a prior trademark-safe SDP Studio presentation, but must not reintroduce a prohibited third-party mark into the product name. Any naming change requires legal/trademark review and a superseding ADR.
