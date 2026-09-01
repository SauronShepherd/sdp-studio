# Trademarks and product naming

SDP Studio is independent open-source software. It is not sponsored by, endorsed by, or affiliated with the Apache Software Foundation (ASF), Databricks, or any other runtime or provider vendor unless a specific written statement says otherwise.

## Apache Spark

Apache Spark, Spark, and the Apache Spark project marks are trademarks of the Apache Software Foundation. Contributors, documentation authors, distributors, and downstream packagers must follow the ASF trademark policy and the Apache Spark project trademark guidance.

The product name is **SDP Studio**. Do not rename the product, a distribution, or a hosted edition so that `Spark` or `Apache Spark` becomes part of the product name. Use Apache Spark only descriptively, for example:

- `SDP Studio — Visual IDE for Apache Spark Declarative Pipelines`
- `SDP Studio for Apache Spark`
- `Runs on Apache Spark 4.2`
- `Apache Spark-compatible runtime profile`

Do not use names such as `Spark SDP Studio`, `Spark Visual Pipelines`, or other wording that could imply that SDP Studio is an ASF project or an officially endorsed Apache Spark product.

Prominent first references should use **Apache Spark** rather than only `Spark` when practical. Public pages and release materials that prominently reference Apache Spark should include an attribution such as:

> Apache Spark and Spark are trademarks of the Apache Software Foundation. SDP Studio is independent software and is not sponsored by, endorsed by, or affiliated with the Apache Software Foundation.

Do not use Apache Spark logos, project graphics, or other ASF marks as SDP Studio branding, application icons, favicons, package artwork, or social avatars without permission under the applicable ASF policy.

## Describing compatibility

Compatibility claims must be factual and scoped to a tested runtime/version. Prefer wording such as `tested with Apache Spark 4.2.x` or `supports Apache Spark Declarative Pipelines when the selected runtime reports the required capabilities` rather than broad certification-style claims.

Provider-specific capabilities must be described as optional integrations. A provider name or trademark must not be used to imply ownership, certification, sponsorship, or endorsement of SDP Studio.

## Databricks and other providers

Databricks and related product names are trademarks of their respective owners. References to Databricks in this repository describe an optional adapter or interoperability target. Databricks is not required for SDP Studio's core authoring, compilation, Git, or local Apache Spark workflows.

The same descriptive-use rule applies to GitHub, GitLab, Kubernetes, PostgreSQL, Kafka, and other third-party names: use them only to identify compatibility, integration, or dependencies, and preserve the trademark notices required by their owners.

## Forks and downstream distributions

Forks may state that they are based on SDP Studio subject to the Apache-2.0 license and applicable trademark law. A fork should not present itself as an official SDP Studio release unless it is distributed by the project maintainers under the project's release process. Downstream branding must also comply with ASF and other third-party trademark policies.

## Documentation and release review

Before a public release, maintainers should review:

1. Product, package, image, chart, website, and social names for prohibited or misleading third-party marks.
2. README, documentation, screenshots, examples, release notes, and generated metadata for endorsement implications.
3. Apache Spark compatibility statements against the versions actually qualified by CI/release gates.
4. Required attribution and third-party notices.

Upstream references used by project maintainers include the Apache Spark trademark guidance and ASF trademark policy. When those policies change, the current upstream policy controls over this summary.
