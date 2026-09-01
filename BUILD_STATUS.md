# SDP Studio 0.1.0 Engineering MVP — Build Status

Build date: 2026-08-22

## Verified for the rebranded SDP Studio source package

- The complete Python test suite and web unit suite pass.
- Python modules and tests compile successfully.
- Browser JavaScript passes Node syntax validation in this environment.
- CLI entry point is `sdpstudio` / `python -m sdpstudio_cli.main`.
- Persisted projects use `.sdpstudio/` and `main.sdpstudio.yaml`.
- Environment variables use the `SDPSTUDIO_*` prefix.
- Stable diagnostic codes use the `SDPS-*` prefix.
- The retail example can be created from the installed wheel and generates the expected project/source-map structure.
- A rebranded `sdpstudio-0.1.0-py3-none-any.whl` builds successfully with local build tooling.
- The Docker image builds from a clean context, and the Compose server/worker/PostgreSQL stack has passed live health, readiness, and non-root smoke checks.
- The Helm chart renders successfully with Helm 3.17 in a container, including server/worker Deployments, ConfigMap, PVC, Service, and non-root security contexts.
- A kind v0.32.0 / Kubernetes v1.36.1 cluster passed live pod create, Ready, status, logs, and cancellation/deletion checks using the Kubernetes lifecycle contract.
- Local Spark capability probing fails gracefully when the Spark SDP tools are not installed.
- React/TypeScript/Vite/XYFlow/Monaco shell type-checks, builds, and is served alongside the more feature-complete dependency-light SPA during the parity migration.

## Implemented runtime paths

- Local Spark SDP
- Spark Connect
- Databricks Connect / Spark Connect interoperability
- Native Spark-on-Kubernetes submission

These are adapter/runtime paths in the engineering MVP. Real-cluster certification remains part of the build plan and must not be inferred from unit tests alone.

## Implemented engineering/debugging features

- Typed visual DAG authoring in the current lightweight SPA
- Deterministic visual-to-code compiler
- Source maps from visual nodes to generated Python
- Bounded node Data Preview
- Local history + history diff/restore
- Immutable run snapshots
- Run comparison / semantic graph diff
- Static performance-risk diagnostics
- Upstream Row Trace
- Spark event-log stage/task/skew analysis
- Generated traceback line → visual node diagnostics
- Run debug-bundle export
- Git + GitHub/GitLab review integration
- Durable Yjs collaboration updates with browser offline/reconnect recovery and WebSocket presence
- Optional shared-server bearer authentication

## Environment limitations of this verification run

Java is available, but the Apache Spark 4.2 `spark-pipelines`, `spark-submit`, and `pyspark.pipelines` runtime components are not installed in this container. Therefore this verification pass did not execute a real Spark job. Compiler semantics, runtime probing, command construction, failure behavior, API/CLI integration, project migration, and packaging are covered by tests; the target deployment should additionally run the Spark integration matrix in `BUILD_PLAN.md`.

Network package installation is unavailable in this environment. The wheel was therefore built with the already-installed build toolchain using `--no-build-isolation`; CI should perform a normal isolated build with pinned build dependencies.

## WSL verification

On 2026-08-22, WSL2 executed the generated preview and Spark smoke paths against real local Spark sessions. The current WSL installation also reran `tests/spark_preview_smoke.py` successfully on Spark 4.1.0, producing filtered rows and a clean SparkContext shutdown. The specification-baseline Spark 4.2.0 package was installed into an isolated WSL target directory:

```text
spark-submit --master local[2] tests/spark_preview_smoke.py
Spark 4.2.0
SDP_SPARK_SMOKE sum=13.0 version=4.2.0
```

WSL also started the bundled Spark Connect server on Spark 4.1.0 and a real Python Connect client executed a remote aggregation successfully:

```text
SPARK_CONNECT_SUM 10
```

The reproducible client dependencies are exposed through `pip install -e '.[connect]'`.

The WSL environment does not currently provide the `spark-pipelines` executable, so this validates ordinary Spark 4.2 execution. Declarative Pipeline CLI qualification remains dependent on installing the optional `pyspark[pipelines]` tooling.

## Explicit 0.1.0 boundaries

- The React/TypeScript/XYFlow/Monaco application is the served UI; the dependency-light static application is retained as a fallback.
- The visual model remains authoritative for unsupported edits, while the Level-B reconciliation path safely imports supported Python/SQL edits, emits ownership regions, and preserves unsupported/custom code with structured `SDPS-RECON-*` problems. See `tests/test_reconcile.py` and the project reconciliation routes.
- Kubernetes supports deterministic native submission commands and status/log/cancel lifecycle integration; kind contract certification is verified, while interactive node preview remains intentionally unsupported for Kubernetes submissions.
- Databricks is an optional execution interoperability target, not a required control plane.
- Fabric and Snowflake adapters are future work.
- Shared-server authentication, OIDC discovery, Argon2id passwords, RBAC, encrypted secrets, audit events, durable Yjs collaboration replay/offline recovery, and scheduler worker paths are implemented and covered by tests. The local two-browser Playwright collaboration qualification passes; deployment-scale coordination and full offline-merge acceptance across distributed replicas remain release-environment follow-up work.
