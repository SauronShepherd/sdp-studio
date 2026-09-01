# SDP Studio — Visual Pipelines for Apache Spark

SDP Studio is an Apache-2.0 open-source visual IDE for designing, generating, validating, running, versioning, collaborating on, and debugging Apache Spark Declarative Pipelines (SDP).

SDP Studio is **Spark-first and vendor-neutral**. Databricks is an optional Spark Connect-compatible runtime profile; it is not a server, SDK, metadata, or deployment dependency. The visual graph is the source of truth and deterministically generates ordinary `pyspark.pipelines` Python plus a Spark pipeline specification.

> **Release status:** productive engineering MVP (`0.1.0`). The editor, compiler, local/team server, Git workflows, runtime adapters, previews, run history, and Debug Lab are implemented. Apache Spark 4.2 is optional at editor startup and required only on machines/runtimes that actually execute Spark workloads.

## Canonical engineering documents

- [`docs/spec/SDP_STUDIO_SPEC.md`](docs/spec/SDP_STUDIO_SPEC.md) — full functional and technical specification.
- [`BUILD_PLAN.md`](BUILD_PLAN.md) — dependency-ordered implementation plan, Codex contract, SDPS tasks, and release gates.
- [`BUILD_STATUS.md`](BUILD_STATUS.md) — what the current 0.1.0 engineering MVP has actually verified.

## Product principles

- **No proprietary control plane.** A laptop, VM, container, or your own cluster is enough.
- **Code is a first-class output.** Visual pipelines compile to readable, deterministic Python.
- **Portable by default.** OSS-compatible constructs are preferred; vendor runtime integration is isolated behind adapters.
- **Git-native.** Projects are ordinary directories/repositories, not opaque database objects.
- **Debuggable.** Runs capture source maps, immutable graph/code snapshots, logs, event summaries, and diagnostics that map generated failures back to visual nodes.
- **Safe local-first operation.** Loopback is the default; remote binding requires authentication unless explicitly overridden.

## What works now

### Visual authoring

- Browser-based drag/drop DAG canvas with typed input/output ports.
- Operator search, click-to-connect, node dragging, copy/paste, delete, undo/redo, zoom, fit, and auto-layout.
- Inspector-driven node configuration.
- Dataset chaining for Bronze → Silver → Gold topologies.
- Materialized views, streaming tables, temporary views, and streaming sinks.
- Relational transformations including filter, select, derive, cast, rename, joins, aggregates, explode, union, deduplication, repartition/coalesce, watermarking, and more.
- Deterministic generation of production-readable `pyspark.pipelines` Python and `spark-pipeline.yaml`.
- Source maps from visual node IDs to generated line ranges.

### Validation and preview

- Graph/type/semantic validation with stable problem codes.
- Spark SDP-specific validation for batch/streaming output semantics.
- Secret-literal detection: project configuration uses environment/secret references instead of persisted credentials.
- Bounded per-node Data Preview (1–200 rows) on local Spark or Spark Connect-compatible runtimes.
- Preview programs are ephemeral and separate from SDP definitions, so preview actions do not contaminate generated pipeline code.

### Execution

- Local Spark SDP runtime discovery and capability doctor.
- Incremental runs, selective refresh, selective full refresh, and full-refresh-all.
- Spark Connect runtime profiles.
- Databricks Connect/Spark Connect interoperability profile without a Databricks dependency in SDP Studio itself.
- Kubernetes submission profile using native Spark Kubernetes options.
- Safe subprocess invocation with argument arrays (`shell=False`) and output secret redaction.
- Persistent run records, cancellation, live run-event WebSocket, and debug-bundle export.

### Debug Lab

- Static pipeline plan with risk scoring.
- Upstream Row Trace through the visual transformation graph.
- Immutable run snapshots containing graph, generated code hash/source maps, runtime information, and command metadata.
- Run-to-run semantic graph/code/status comparison (“pipeline time travel”).
- Spark listener event-log parsing with stage/task summaries and skew diagnostics.
- Generated traceback line → visual node mapping using compiler source maps.
- Local-history diff and restore.

### Git and collaboration

- Git init, status, diff, commit, branches, remotes, fetch, fast-forward pull, and push.
- Clone/import an existing SDP Studio Git repository.
- GitHub pull-request and GitLab merge-request creation hooks using environment-provided tokens.
- Remote URL/branch/remote-name validation to prevent option/remote-helper injection.
- Optimistic revision locking: stale browser saves receive HTTP 409 instead of overwriting a teammate.
- Project WebSocket presence/change notifications.
- Optional bearer-token API protection for shared-server deployment.

### Interfaces

- Self-contained professional SPA; no CDN or proprietary service is required.
- REST/OpenAPI API.
- CLI (`sdpstudio`) for projects, runtimes, validation, generation, preview, and execution.
- SQLite/WAL metadata plus human-readable project YAML and generated source on disk.

## Quick start

Requires Python 3.12+.

### Documented local Spark path

For the reference Apache Spark 4.2 environment, the governing specification uses
this installation sequence:

```bash
python -m venv .venv
source .venv/bin/activate
pip install "pyspark[pipelines]==4.2.0" sdpstudio
sdpstudio doctor
sdpstudio serve --open
```

When working from this repository, use the editable install below instead; the
`.[pipelines]` extra provides the same optional Spark/Pipelines dependency.

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
sdpstudio project create retail-demo --from-example retail-etl
sdpstudio serve --open
```

Open `http://127.0.0.1:8787` if the browser does not open automatically.

### Add local Spark execution

```bash
pip install -e '.[pipelines]'
sdpstudio doctor
sdpstudio validate PROJECT_ID
sdpstudio generate PROJECT_ID
sdpstudio run PROJECT_ID
```

For a Spark Connect client, install the additional Connect dependencies:

```bash
pip install -e '.[connect]'
```

For a real Spark-backed preview smoke test under WSL2 (using the installed Spark
runtime and project source), run `make spark-smoke-wsl`. The test reports the
Spark version and emits bounded preview rows. Spark 4.2 Declarative Pipelines
qualification additionally requires the Spark 4.2 `spark-pipelines` tools.

Generated `spark-pipeline.yaml` files use absolute local URIs by default. When
the same project is executed from WSL or another deployment environment, set
`SDPSTUDIO_STORAGE_URI` and `SDPSTUDIO_EVENT_LOG_URI` before generating the
project, for example:

```bash
export SDPSTUDIO_STORAGE_URI=file:///mnt/c/path/to/project/.sdpstudio/runtime/storage
export SDPSTUDIO_EVENT_LOG_URI=file:///mnt/c/path/to/project/.sdpstudio/runtime/event-logs
sdpstudio generate PROJECT_ID
```

This keeps storage and event-log paths valid for the Spark process without
persisting a developer-specific Windows path in a portable deployment.

SDP Studio itself starts and edits projects without Spark installed. This is intentional: the execution runtime may live elsewhere.

## Existing repository

```bash
sdpstudio project clone team-pipeline git@github.com:your-org/team-pipeline.git --branch main
sdpstudio serve --open
```

The cloned repository must contain:

```text
.sdpstudio/project.yaml
.sdpstudio/pipelines/main.sdpstudio.yaml
```

Machine-local runtime/history artifacts are excluded through `.git/info/exclude`, so cloning does not dirty tracked repository files.

## Runtime profiles

List/probe profiles:

```bash
sdpstudio runtime list
sdpstudio runtime probe local
```

Spark Connect using an environment variable rather than a persisted connection secret:

```bash
export SPARK_REMOTE='sc://spark.example.internal:15002'
sdpstudio runtime add shared-connect spark-connect \
  --config '{"remote_env":"SPARK_REMOTE"}'
# With a running endpoint, the bounded client smoke is:
SPARK_REMOTE=sc://127.0.0.1:15002 make spark-connect-smoke
```

Kubernetes:

```bash
sdpstudio runtime add prod-k8s kubernetes --config '{
  "master":"k8s://https://kubernetes.default.svc",
  "image":"registry.example/spark:4.2.0",
  "storage_uri":"s3a://company-sdpstudio/pipelines/customer-etl",
  "namespace":"data",
  "service_account":"spark"
}'
```

Databricks can be used as a Spark Connect-compatible execution target when the environment is configured for it. SDP Studio does not require Databricks for authoring, storage, compilation, Git, history, debugging, local execution, or Kubernetes execution.

## CLI reference

```text
sdpstudio serve [--host HOST] [--port PORT] [--open] [--insecure-allow-remote]
sdpstudio doctor [--json]

sdpstudio project list
sdpstudio project create NAME [--from-example retail-etl]
sdpstudio project clone NAME REMOTE_URL [--branch BRANCH]

sdpstudio runtime list
sdpstudio runtime add NAME {local,spark-connect,kubernetes,databricks-connect} [--config JSON]
sdpstudio runtime probe PROFILE_ID
sdpstudio runtime delete PROFILE_ID

sdpstudio validate PROJECT_ID
sdpstudio generate PROJECT_ID [--check]
sdpstudio preview PROJECT_ID NODE_ID [--runtime PROFILE_ID] [--limit 1..200] [--json]
sdpstudio run PROJECT_ID [--runtime PROFILE_ID]
                   [--refresh DATASET]
                   [--full-refresh DATASET]
                   [--full-refresh-all]
```

## Team/server mode

SDP Studio binds to loopback by default. For a shared server, set a strong bearer token and bind explicitly:

```bash
export SDPSTUDIO_AUTH_TOKEN='replace-with-a-long-random-secret'
sdpstudio serve --host 0.0.0.0 --port 8787
```

Browsers prompt for the token when they first call the protected API. WebSocket collaboration uses the same token. For internet-facing deployments, terminate TLS at a trusted reverse proxy and use network policy/firewall controls as well.

`--insecure-allow-remote` exists only for explicitly trusted development networks and should not be used for an internet-facing deployment.

## Docker

The container intentionally refuses a remote bind when `SDPSTUDIO_AUTH_TOKEN` is absent.

```bash
export SDPSTUDIO_AUTH_TOKEN='replace-with-a-long-random-secret'
docker compose up --build
```

Data is stored in the `sdpstudio-data` volume by default.

## Project layout

```text
project/
├── .sdpstudio/
│   ├── project.yaml
│   ├── pipelines/main.sdpstudio.yaml     # visual model / source of truth
│   ├── generated/                  # source maps and generated metadata
│   ├── history/                    # machine-local snapshots
│   └── runtime/                    # machine-local logs/artifacts/storage
├── transformations/generated.py   # deterministic SDP code
└── spark-pipeline.yaml             # generated Spark pipeline spec
```

The main repository is organized as:

```text
python/sdpstudio_core/       graph model, validation, operators, debug analysis
python/sdpstudio_codegen/    deterministic SDP compiler + preview compiler
python/sdpstudio_runners/    runtime probing, command adapters, execution
python/sdpstudio_server/     FastAPI, persistence, Git, collaboration, provider hooks

Optional Databricks integration is isolated in `sdpstudio_adapters_databricks` and is
not imported by the OSS core. Install its SDK only when needed with
`pip install 'sdpstudio[databricks]'`; portable projects remain usable without it.

Optional operator plugins register a callable through the Python entry-point group
`sdpstudio.operator_definitions`. The callable returns one operator dictionary or a
list of dictionaries; malformed or failing plugins are isolated during discovery.
python/sdpstudio_cli/        command-line interface
web/                   source SPA assets
examples/retail-etl/   productive example
```

## Development

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
pytest
ruff check python tests
node --check web/app.js
```

The CI workflow performs Python and frontend quality gates, builds the wheel,
and runs the local Spark preview smoke test with the optional pipelines
dependencies on Python 3.12.

## Security model

- Localhost-only by default.
- Optional `SDPSTUDIO_AUTH_TOKEN` bearer authentication for API/OpenAPI and collaboration sockets.
- Remote CLI bind is refused without a token unless the operator opts into the explicit insecure override.
- Git subprocesses and Spark subprocesses use `shell=False` and argument arrays.
- Git URLs reject embedded HTTP credentials, local paths, `file://`, and remote-helper/ext transports.
- Provider tokens are read from environment variables and are not persisted in project models or run snapshots.
- Runtime profiles reject obvious token/password literals and support environment-variable references.
- Logs/commands are redacted before persistence where credential-shaped content may appear.

See `SECURITY.md` for reporting and deployment guidance.

## Deliberate MVP boundaries

These are explicit boundaries rather than hidden “supported” features:

- Arbitrary hand-edited generated Python is **not** round-tripped back into the graph in `0.1.0`; the visual model is the source of truth.
- Kubernetes supports full pipeline submission; interactive node preview is local/Spark Connect only.
- Databricks support is execution interoperability, not deployment to the proprietary managed Lakeflow control plane.
- Collaboration currently targets one SDP Studio application process and uses optimistic revisions + presence; OIDC/SAML, granular RBAC, audit sinks, and horizontally distributed collaboration are post-MVP enterprise hardening.
- Microsoft Fabric and Snowflake runtime adapters are future work.
- Actual Spark 4.2 execution must be integration-tested in the target Spark/Kubernetes/Databricks environment; the repository can be built and tested without bundling Spark.

## License and trademark

SDP Studio is licensed under the **Apache License 2.0**. See `LICENSE` and `NOTICE`.

The project is named **SDP Studio**, not “Spark Visual Pipelines”. Apache Spark and Spark are trademarks of the Apache Software Foundation. See `TRADEMARKS.md`.

## Full specification

The product/technical specification and low-level Codex build plan are retained at:

`docs/spec/product-spec.md`
