# SDP Studio — Open Visual IDE for Apache Spark Declarative Pipelines

> Product name: **SDP Studio**  
> Product category: Open-source visual IDE and collaborative server for Apache Spark Declarative Pipelines (SDP)  
> License: Apache License 2.0  
> Specification status: Canonical product + functional + technical specification and implementation blueprint  
> Baseline date: 2026-08-22  
> Intended repository path: `docs/SPEC.md`  
> Reference Apache Spark version: 4.2.0

---

## 1. Executive summary

SDP Studio is a free, open-source, Apache-2.0 licensed visual engineering environment for designing, generating, validating, executing, debugging, versioning, reviewing, and operating Apache Spark Declarative Pipelines (SDP).

SDP Studio should feel like a serious commercial data engineering product, but its core must remain fully open source and usable without Databricks or any other proprietary platform.

The primary experience combines two concepts that are currently separated in many products:

1. A visual drag-and-drop data transformation designer that generates production-quality code.
2. A pipeline engineering IDE with source files, Git integration, execution controls, pipeline graphs, metrics, previews, and advanced debugging.

SDP Studio must generate clean, human-readable Apache Spark SDP code in Python and SQL. Engineers must be able to move between visual design and code without being trapped in a proprietary representation. Databricks is an optional execution/deployment adapter, not the execution core and not a required dependency.

The productive MVP must support:

- Visual batch and streaming pipeline design.
- Production-quality `pyspark.pipelines` and Spark SQL code generation.
- Import of existing SDP projects.
- Lossless preservation of unsupported custom code.
- Local Apache Spark 4.2 execution.
- Spark Connect execution.
- Kubernetes execution using native Spark-on-Kubernetes submission.
- Optional Databricks execution/deployment integration.
- Git repositories and generic Git remotes.
- First-class GitHub and GitLab workflows.
- Local history independent of Git.
- Team collaboration in a remotely hosted SDP Studio server.
- Validation, selective execution, preview, full refresh, incremental refresh, cancellation, logs, metrics, and run history.
- Advanced debugging including plan inspection, plan diff, run diff, skew detection, row tracing for visual operators, schema evolution, graph heatmaps, failure diagnostics, and reproducible debug bundles.
- A plugin architecture for future runtimes, operators, source/sink connectors, catalogs, and code generators.
- No mandatory cloud service, telemetry service, proprietary API, or paid feature.

SDP Studio is not intended to hide Spark from engineers. It should make Spark engineering faster, safer, more observable, and easier to adopt while keeping the generated implementation understandable and portable.

---

## 2. Product identity, trademark, and licensing requirements

### 2.1 Product name

The product name is **SDP Studio**.

Recommended public forms:

- `SDP Studio`
- `SDP Studio — Visual IDE for Apache Spark Declarative Pipelines`
- `SDP Studio, an open-source visual development environment for Apache Spark Declarative Pipelines`

Recommended tagline:

> **Design visually. Own the code. Run anywhere.**

`SDP` refers to Declarative Pipelines in the product context, but the brand itself does not include the Apache Spark trademark. Public materials should use the full name **Apache Spark** in prominent first references and must not imply endorsement by the Apache Software Foundation.

Do not rename the product to `Spark Visual Pipelines`, `Spark SDP Studio`, or another product name containing `Spark`. Apache Spark's published trademark guidance says third-party software products, including open-source products, generally may not use `Spark` in the product name except in permitted descriptive forms such as `for Apache Spark` or `powered by Apache Spark`.

The project website, README, documentation, and release artifacts must include appropriate trademark attribution.

### 2.2 Software identity

Canonical identifiers for the initial implementation:

```text
Product:        SDP Studio
Repository:     sdp-studio
CLI:            sdpstudio
Python dist:    sdpstudio
Server binary:  sdpstudio-server
Project folder: .sdpstudio/
Runtime helper: sdpstudio-runtime
```

If a package identifier is unavailable in a public registry, the distribution identifier may differ, but the user-facing product name remains `SDP Studio`.

### 2.3 License

All project-owned source code is licensed under the **Apache License 2.0**.

Repository root must contain:

- `LICENSE`
- `NOTICE`
- `SECURITY.md`
- `CONTRIBUTING.md`
- `CODE_OF_CONDUCT.md`
- `GOVERNANCE.md`
- `TRADEMARKS.md`
- `THIRD_PARTY_NOTICES.md`

Every dependency must be checked by automated license scanning. Dependencies with licenses incompatible with the intended distribution model must be rejected or isolated as optional external system dependencies.

### 2.4 Open-source guarantee

There is one upstream edition of SDP Studio. No core engineering capability is reserved for a proprietary edition.

The following are open source:

- Visual pipeline designer.
- Intermediate representation and compiler.
- Python and SQL code generators.
- Execution adapters shipped by the project.
- Debugger, profiler, and diagnostic engine.
- Git integration.
- Collaboration server.
- Authentication and authorization.
- Scheduling.
- Plugin SDK.
- CLI.
- Deployment manifests.

Third parties may provide hosted services, enterprise support, or managed distributions without reducing the functionality of the upstream project.

## 3. Product vision

### 3.1 Product statement

SDP Studio is the professional open-source visual engineering environment for Apache Spark Declarative Pipelines.

### 3.2 Primary goal

Make an experienced data engineer faster while making SDP approachable to engineers who do not want to hand-author every pipeline construct.

### 3.3 Core principles

1. **Apache Spark first**: the canonical execution semantics come from open-source Apache Spark SDP.
2. **Generated code is a product output**: generated Python and SQL must be suitable for code review and long-term maintenance.
3. **No vendor lock-in by default**: portable mode emits only Apache Spark-compatible constructs.
4. **Visual and code workflows are equal citizens**: neither workflow is a toy view of the other.
5. **Debugging is a differentiator**: the editor must explain pipeline behavior, not only execute it.
6. **Git is the durable collaboration boundary**: project files and generated source belong in ordinary repositories.
7. **Local-first, server-capable**: one engineer can run SDP Studio on a laptop; a team can run the same product as a shared server.
8. **Explicit capabilities**: runtime-specific features are shown before deployment and never silently introduced.
9. **Reproducibility**: every run is tied to code, graph revision, runtime profile, Spark configuration, and environment metadata.
10. **Safe extensibility**: operators and runtimes are plugins with capability declarations and validation.

---

## 4. Technical baseline and external facts

The MVP is designed around Apache Spark 4.2.0.

Relevant Apache Spark 4.2 capabilities include:

- Spark Declarative Pipelines in Python and SQL.
- Materialized views.
- Streaming tables.
- Temporary views.
- Append flows.
- `spark-pipelines init`, `run`, and `dry-run`.
- Selective refresh and selective full refresh.
- Spark Connect execution through `spark-pipelines run --remote`.
- External streaming sinks through the Python SDP API.
- Native Spark-on-Kubernetes support through `spark-submit` semantics.
- CDC APIs and SDP Auto CDC SCD Type 1 support introduced in Spark 4.2.
- Spark event logging and Spark UI/History Server data that SDP Studio can consume for diagnostics.

The product must not assume that every runtime has every Spark 4.2 feature. Runtime adapters expose a capability document and the editor validates the graph against the selected runtime profile.


### 4.1 Approved technology stack

The following stack is the default architecture unless changed by an accepted ADR.

| Concern | Technology | Decision |
|---|---|---|
| Backend language | Python 3.12+ | Native fit with PySpark and data-engineering ecosystem |
| API server | FastAPI | REST, OpenAPI, async execution, WebSocket support |
| Validation/models | Pydantic v2 | Strict external and domain boundary validation |
| ORM | SQLAlchemy 2 | Shared persistence abstraction for SQLite/PostgreSQL |
| DB migrations | Alembic | Versioned schema migrations |
| Local database | SQLite WAL | Zero-configuration single-engineer mode |
| Team database | PostgreSQL 16+ | Durable shared-server mode |
| Frontend | React + TypeScript | Professional SPA architecture |
| Frontend build | Vite | Fast dev/build cycle without SSR overhead |
| Visual graph | `@xyflow/react` | Node/edge canvas, custom ports, navigation, selection |
| Code editor | Monaco Editor | IDE-grade Python/SQL editing experience |
| UI state | Zustand | Local interaction state |
| Server state | TanStack Query | API caching, invalidation, background refresh |
| Forms | React Hook Form + Zod | Typed operator/property forms |
| UI primitives | Radix UI or equivalent accessible headless primitives | Accessibility and composability |
| Styling | Tailwind CSS | Consistent design system implementation |
| Collaboration | Yjs | CRDT-based graph/text synchronization |
| Realtime transport | WebSocket | Runs, logs, collaboration, presence |
| Python source analysis | LibCST | Syntax-preserving import/round-trip support |
| SQL parsing/codegen | SQLGlot | SQL AST, normalization, dialect-aware processing |
| Git engine | System Git CLI through safe argv wrapper | Full compatibility with Git remotes and credentials |
| Git providers | GitHub + GitLab APIs | PR/MR workflows and provider metadata |
| Spark runtime | Apache Spark 4.2.x baseline | Reference SDP execution semantics |
| Remote Spark | Spark Connect | Preview and interactive remote execution |
| Kubernetes | Native Spark-on-Kubernetes | Vendor-neutral cluster execution |
| Databricks | Optional adapter only | Interoperability without core dependency |
| Testing backend | pytest + pytest-asyncio | Unit/integration coverage |
| Testing frontend | Vitest + Testing Library | Component and state tests |
| E2E | Playwright | Real browser workflows |
| Local K8s CI | kind | Repeatable Kubernetes integration testing |
| Observability | OpenTelemetry + Prometheus-compatible metrics | Product and runtime diagnostics |
| Packaging | Python wheel + Docker/OCI image | Local/server distribution |
| License | Apache-2.0 | Permissive open-source distribution |

Architecture rule: **the visual editor is never the source of execution semantics**. The canonical pipeline model is the SDP Studio IR, and all UIs, CLIs, code generation, validation, debugging, and runtimes consume the same core contracts.

### 4.2 Portability modes

SDP Studio exposes three compatibility levels:

#### Portable OSS mode - default

Only Apache Spark SDP APIs and standard Spark APIs supported by the configured reference runtime may be generated.

#### Portable + SDP Studio runtime mode

Generated projects may use the optional Apache-2.0 `sdpstudio-runtime` Python package for debugging instrumentation, reusable quality helpers, test utilities, and enhanced observability. The project remains deployable anywhere the package is installed.

#### Provider extensions mode

A runtime adapter may expose provider-only capabilities. The canvas marks every provider-specific node or option with a visible badge and compatibility warning. Provider-specific constructs cannot appear silently.

---

## 5. Personas

### 5.1 Individual data engineer

Needs a local visual IDE, code generation, local Spark execution, Git workflows, and serious debugging without provisioning Databricks.

### 5.2 Platform/data infrastructure engineer

Needs centrally managed runtime profiles, Kubernetes execution, secrets, access controls, auditability, and repeatable deployments.

### 5.3 Data engineering team

Needs concurrent editing, review, branches, shared run history, schedules, reusable components, and debugging artifacts.

### 5.4 Engineer migrating existing ETL to SDP

Needs import, graph reconstruction, compatibility diagnostics, refactoring assistance, and code that remains understandable outside SDP Studio.

### 5.5 Databricks user who wants portability

Needs to design in SDP Studio, run locally, validate OSS compatibility, and optionally deploy the same project to Databricks.

---

## 6. MVP definition of done

The project reaches the production-usable MVP milestone only when all of the following are true:

1. A new user can install SDP Studio locally, create a project, visually build a non-trivial batch pipeline, generate Python SDP code, validate it, run it on local Spark 4.2, inspect output, commit it to Git, and reproduce the run.
2. A user can build a streaming pipeline with a streaming table and an append flow, execute it against a supported local or remote source, and inspect streaming-related run information.
3. An existing SDP project containing multiple Python/SQL files can be imported without destructive rewriting.
4. Visual-generated code is deterministic: identical graph + settings produce byte-identical generated files after formatting.
5. Unsupported imported code is preserved as a `Custom Code` artifact rather than discarded.
6. A user can switch between canvas and code and understand which graph node generated which code region.
7. A selected dataset can be refreshed; a selected dataset can be full-refreshed; a pipeline can be dry-run validated.
8. Local Spark, Spark Connect, Kubernetes, and Databricks runtime profiles pass adapter contract tests.
9. A team server can authenticate multiple users, share a project, show presence, persist edits, and enforce viewer/editor/admin roles.
10. Git clone, status, diff, branch, commit, pull, push, and conflict handling work with generic Git remotes.
11. GitHub pull request and GitLab merge request creation work when provider credentials are configured.
12. Local history allows recovering uncommitted visual/code state after browser refresh and server restart.
13. A run record captures graph revision, Git commit/dirty state, generated source hash, runtime profile, Spark config, timestamps, final status, logs, and artifacts.
14. Advanced debug views provide at least: data preview, schema/profile, Spark explain plans, plan diff, run diff, skew diagnostics from event data, graph performance overlays, row trace for supported operators, and exportable debug bundles.
15. All secrets are redacted from logs and encrypted at rest in server mode.
16. Non-loopback server deployments require authentication unless an explicit insecure development flag is supplied.
17. The repo has unit, integration, code-generation golden, adapter contract, and browser end-to-end tests in CI.
18. The project publishes reproducible source distributions, Python packages, container images, SBOMs, and checksums.
19. No mandatory dependency requires Databricks, GitHub, GitLab, a paid SaaS, or a proprietary database.
20. The quick-start tutorial can be completed from a clean machine using only open-source local components.

---

## 7. Explicit non-goals for the MVP

The MVP is deliberately not:

- A replacement for a general-purpose notebook product.
- A general DAG orchestrator for arbitrary shell/Python tasks.
- A complete data catalog product.
- A BI/reporting platform.
- A full IDE replacement for arbitrary Python projects.
- A perfect visual reverse compiler for every possible Python program.
- A proprietary scheduler competing with Airflow/Dagster for arbitrary workflows.
- A managed cloud service.
- A Snowflake-native runtime.

Fabric and Snowflake are future adapters. Snowflake should not be described as an Apache Spark runtime; any future Snowflake integration must define whether it is a sink/source, deployment/export target, or a separate execution model.

---

## 8. User experience specification

### 8.1 Main application layout

Desktop browser layout:

- **Top application bar**: workspace, project, branch, environment/runtime, validation status, run controls, user menu.
- **Left activity rail**: Explorer, Operators, Catalog, Git, Runs, Debug, Extensions, Settings.
- **Left side panel**: selected activity content.
- **Center workspace**: tabbed Canvas / Code / Diff / Run Comparison views.
- **Right inspector**: node configuration, schema, properties, compatibility, documentation.
- **Bottom panel**: Preview, Data Profile, Problems, Logs, Metrics, Spark Plan, Debug Console.
- **Status bar**: Git branch/dirty state, selected runtime, Spark version/capabilities, collaboration state, background jobs.

The layout must support resizable and collapsible panels and remember user layout preferences.

### 8.2 Canvas behavior

Use a professional node editor with:

- Drag/drop operators.
- Typed input/output ports.
- Multi-select.
- Rubber-band selection.
- Copy/paste.
- Duplicate.
- Delete.
- Undo/redo.
- Group/subflow.
- Notes/Markdown annotations.
- Auto-layout.
- Align/distribute.
- Minimap.
- Zoom controls and fit-to-view.
- Context menu.
- Command palette.
- Keyboard navigation.
- Search nodes by name/type/table.
- Collapse groups.
- Pin important datasets.
- Highlight upstream/downstream impact.
- Edge labels for aliases/ports.
- Invalid-edge rejection before save.
- Visual badges for batch, streaming, materialized, provider-specific, warning, failed, running, cached preview.

### 8.3 Canvas overlays

A user can overlay one metric family at a time:

- Execution time.
- Row count.
- Input/output bytes.
- Shuffle read/write.
- Task skew score.
- Data quality status.
- Schema drift.
- Freshness.
- Last successful run.
- Runtime compatibility.

### 8.4 Asset explorer

Project explorer shows:

- Visual pipeline documents.
- Generated transformation files.
- Hand-authored transformation files.
- Utilities.
- Tests.
- Pipeline specification YAML.
- SDP Studio metadata.
- Run/debug artifacts if configured to show them.

The user may create, rename, move, and delete files with Git-aware operations.

### 8.5 Code editor

Monaco-based editor with:

- Python and SQL syntax highlighting.
- YAML/JSON/TOML support.
- Search/replace.
- Multi-cursor.
- Bracket matching.
- Diff editor.
- Problems markers.
- Formatting.
- Quick fixes produced by SDP Studio validators.
- Go-to-generated-node.
- Go-to-source-code from a node.
- Source-map gutter markers.
- Read-only generated mode or editable round-trip mode.
- File tabs and split editor.

Language servers are optional in MVP. The server should expose extension points for Pyright and SQL language services later.

### 8.6 Table of contents

A pipeline table-of-contents view lists:

- Sources.
- Transform groups.
- Materialized views.
- Streaming tables.
- Temporary views.
- Flows.
- Sinks.
- Custom code blocks.

Selecting an item focuses the canvas node and relevant generated code.

### 8.7 Parameters and environments

A pipeline can define typed parameters:

- string
- integer
- float
- boolean
- date
- timestamp
- secret reference
- enum
- JSON

Parameter values can be overridden by environment profile and schedule.

Environments are named sets such as `local`, `dev`, `test`, `prod` containing:

- runtime profile
- catalog/database/schema defaults
- Spark configuration overrides
- parameter overrides
- secret references
- storage/checkpoint path
- deployment settings

No secret value is committed into the SDP Studio project document.

---

## 9. Visual operator catalog

Every operator is described by an `OperatorDefinition` plugin object with typed ports, configuration schema, capability requirements, validator, schema inference handler, code compiler, preview compiler, and documentation metadata.

### 9.1 Source operators

MVP built-ins:

- Table - batch.
- Table - streaming.
- File - CSV.
- File - JSON.
- File - Parquet.
- File - ORC.
- File - text/binary where supported.
- Generic Spark DataSource V2 source.
- Kafka streaming source.
- JDBC source.
- SQL query source.
- Custom PySpark source.
- Pipeline dataset reference.

Source options are represented as key/value configuration with secret values expressed as secret references.

### 9.2 Relational transforms

MVP built-ins:

- Select columns.
- Drop columns.
- Rename columns.
- Reorder columns.
- Cast columns.
- Add/derive column.
- Filter.
- Drop nulls.
- Fill nulls.
- Replace values.
- Distinct.
- Drop duplicates.
- Aggregate/group-by.
- Join: inner/left/right/full/semi/anti/cross with explicit warning for cross.
- Union by name.
- Intersect.
- Except.
- Sort/order.
- Limit - batch/debug only and clearly marked when it changes production semantics.
- Explode/posexplode.
- Flatten struct.
- Parse JSON.
- Build struct/map/array.
- Window expression.
- Deduplicate with event time for streaming where supported.
- Watermark.
- Repartition/coalesce hint node with performance warning.
- SQL expression/project.
- SQL transform block.
- PySpark transform block.

Do not expose a visual PIVOT operator as portable SDP code in contexts where the underlying SDP runtime rejects it. The capability engine should explain the restriction and offer alternatives.

### 9.3 SDP dataset/output operators

- Materialized View.
- Streaming Table.
- Temporary View.
- Create Streaming Table target.
- Append Flow.
- External Sink.
- Auto CDC SCD Type 1 when runtime capability is available.

Provider extensions can add other CDC modes, but they must be visibly provider-specific.

### 9.4 Quality and observability operators

Portable MVP:

- Column rule test.
- Null-rate rule.
- Uniqueness test.
- Row-count range test.
- Referential sample test.
- Schema contract.
- Quarantine split.
- Profile probe.

Quality rules are stored separately from normal SDP dataset-definition actions where an action would violate SDP planning restrictions. The compiler must never insert prohibited actions such as `count()` or writes inside an SDP dataset definition merely to implement a visual quality rule.

### 9.5 Utility operators

- Parameter.
- Constant.
- Note.
- Group/subflow.
- Reusable component input/output.
- Custom code.

### 9.6 Operator capability metadata

Each operator declares, at minimum:

```json
{
  "id": "transform.join",
  "version": 1,
  "inputs": [{"name": "left", "cardinality": 1}, {"name": "right", "cardinality": 1}],
  "outputs": [{"name": "out", "cardinality": "many"}],
  "modes": ["batch", "streaming"],
  "codeTargets": ["python", "sql"],
  "requiredCapabilities": [],
  "forbiddenCapabilities": [],
  "configSchema": {},
  "uiSchema": {}
}
```

Plugins must be versioned. A project records the operator version used when saved.

---

## 10. Code generation and round-trip engineering

### 10.1 Core requirement

SDP Studio must generate production-quality code similar in intent to a commercial visual designer, but it must not hide the generated code or make the project dependent on an opaque binary format.

### 10.2 Canonical representations

An SDP Studio project has two durable representations:

1. **Visual model**: `.sdpstudio/*.sdpstudio.yaml` files.
2. **Executable source**: ordinary `.py`, `.sql`, and `spark-pipeline.yaml` files.

Both are committed to Git by default.

The visual model is authoritative for nodes owned by the visual designer. Hand-authored code is authoritative for code-owned blocks/files.

### 10.3 No-data-loss rule

SDP Studio must never overwrite code it cannot confidently round-trip.

When code changes cannot be represented by an existing visual operator, SDP Studio must do one of:

1. Convert the affected region to a `Custom Code` node while preserving exact source text.
2. Mark the file `code-owned` and rebuild only graph metadata that can be safely inferred.
3. Ask the user to accept a visual rewrite before replacing source.

Silent source loss is a release-blocking defect.

### 10.4 Round-trip levels

#### Level A - fully visual

All code is generated from known operators. Full bidirectional editing through the operator forms is supported.

#### Level B - visual with custom blocks

Most graph structure is visual; selected nodes contain editable SQL/PySpark fragments. The fragment is preserved verbatim except user-requested formatting.

#### Level C - code-owned import

SDP Studio parses dependencies and SDP datasets from existing source, produces a navigable graph, but does not claim every transformation is editable as visual operators.

### 10.5 Internal compiler pipeline

```text
.sdpstudio YAML
  -> parse
  -> schema validation
  -> graph validation
  -> capability validation
  -> canonical IR
  -> optimization/normalization passes
  -> Python/SQL backend
  -> formatter
  -> source map
  -> generated files
  -> spark-pipelines dry-run
```

### 10.6 Canonical IR

The IR is not UI-specific. It contains:

- Project.
- Pipeline.
- Dataset.
- Flow.
- Source.
- Transform expression.
- Sink.
- Parameter reference.
- Secret reference.
- Runtime capability requirement.
- Source location.
- Visual node identity.

The IR package must have no dependency on React or FastAPI.

### 10.7 Python backend

Implementation requirements:

- Use Python AST and/or LibCST to parse imported files and to make safe transformations.
- Emit `from pyspark import pipelines as dp`.
- Emit type hints where they improve clarity.
- Prefer standard DataFrame APIs.
- Use stable import ordering.
- Run Ruff formatting or Black-compatible formatting policy chosen by the project.
- Generate deterministic function names and dataset names.
- Preserve user comments in custom regions.
- Never emit prohibited SDP planning actions inside dataset functions.

Example desired generated style:

```python
from pyspark import pipelines as dp
from pyspark.sql import DataFrame
from pyspark.sql import functions as F


@dp.materialized_view(name="daily_orders")
def daily_orders() -> DataFrame:
    orders = spark.table("raw.orders")
    return (
        orders
        .filter(F.col("status") == F.lit("COMPLETE"))
        .groupBy(F.to_date("order_ts").alias("order_date"))
        .agg(F.sum("amount").alias("revenue"))
    )
```

### 10.8 SQL backend

Use SQLGlot or an equivalent parser/AST layer for supported Spark SQL generation and import.

Requirements:

- Deterministic formatting.
- Identifier quoting only when necessary.
- Explicit `STREAM` semantics for streaming references.
- Preserve custom SQL blocks losslessly.
- Reject or downgrade unsupported syntax with a clear explanation.

### 10.9 Mixed-language pipelines

A project may contain Python and SQL files simultaneously.

The compiler should prefer the user-selected language at the materialization boundary. A subgraph that requires Python-only features is compiled into Python even if other pipeline files are SQL.

### 10.10 Generated source maps

For every generated file, create `.sdpstudio/source-maps/<relative-file>.map.json` mapping:

- graph node id
- IR object id
- start line/column
- end line/column
- generated hash

Source maps power:

- click node -> code
- click code -> node
- error location -> node
- Git graph diff
- debugging annotations

### 10.11 Importer

Python importer detects:

- `@dp.materialized_view`
- `@dp.table`
- `@dp.temporary_view`
- `@dp.append_flow`
- `dp.create_streaming_table`
- `dp.create_sink`
- known Auto CDC API calls when available
- reads through `spark.table`, `spark.read`, `spark.readStream`
- obvious pipeline dataset dependencies

SQL importer detects:

- materialized view declarations
- streaming table declarations
- temporary views
- flows
- `STREAM` references
- standard relational transforms supported by the visual operator set

Unknown expressions remain custom code.

### 10.12 Code ownership markers

Avoid polluting source with dozens of generated comments. Prefer source maps and stable AST fingerprints.

If a marker is needed for robust round-trip, use a minimal unobtrusive comment only at region boundaries, for example:

```python
# sdpstudio:region node=01J...
...
# sdpstudio:endregion
```

Markers must never be semantically required at runtime.

---

## 11. SDP Studio project format

Recommended repository layout:

```text
my-pipeline/
  spark-pipeline.yaml
  pyproject.toml
  README.md
  transformations/
    bronze.py
    silver.py
    gold.sql
  utilities/
  tests/
  .sdpstudio/
    project.yaml
    pipelines/
      main.sdpstudio.yaml
    source-maps/
    environments/
      local.yaml
      dev.yaml
    tests/
      quality.yaml
    ui/
      layout.json
  .gitignore
```

### 11.1 `.sdpstudio/project.yaml`

Contains only portable non-secret metadata:

```yaml
schemaVersion: 1
projectId: 01J...
name: retail-etl
pipelines:
  - id: 01J...
    model: .sdpstudio/pipelines/main.sdpstudio.yaml
sparkSpec: spark-pipeline.yaml
defaultLanguage: python
compatibility:
  baseline: spark-4.2
  mode: portable-oss
```

### 11.2 Pipeline visual document

```yaml
schemaVersion: 1
pipelineId: 01J...
name: retail
nodes:
  - id: 01J...
    type: source.table
    operatorVersion: 1
    position: {x: 120, y: 200}
    config:
      table: raw.orders
      streaming: false
  - id: 01K...
    type: transform.filter
    operatorVersion: 1
    position: {x: 420, y: 200}
    config:
      expression: "status = 'COMPLETE'"
  - id: 01L...
    type: dataset.materialized_view
    operatorVersion: 1
    position: {x: 720, y: 200}
    config:
      name: complete_orders
edges:
  - id: 01M...
    from: {node: 01J..., port: out}
    to: {node: 01K..., port: in}
  - id: 01N...
    from: {node: 01K..., port: out}
    to: {node: 01L..., port: in}
```

Use ULIDs for sortable globally unique object ids.

### 11.3 Migration policy

Every persisted schema has an integer `schemaVersion`.

Migrations must be:

- deterministic
- unit tested
- reversible when practical
- backed up before mutation
- never dependent on network services

---

## 12. Execution model

### 12.1 Runtime profile abstraction

A `RuntimeProfile` selects an adapter and configuration.

```yaml
id: local-420
type: local-spark
capabilities:
  discover: true
config:
  python: .venv/bin/python
  sparkHome: null
  eventLogDir: .sdpstudio-runs/eventlog
```

Runtime adapters implement:

```python
class RuntimeAdapter(Protocol):
    async def probe(self) -> RuntimeCapabilities: ...
    async def validate(self, request: ValidateRequest) -> ValidationResult: ...
    async def preview(self, request: PreviewRequest) -> PreviewResult: ...
    async def submit(self, request: RunRequest) -> RunHandle: ...
    async def cancel(self, run: RunHandle) -> None: ...
    async def status(self, run: RunHandle) -> RunStatus: ...
    async def stream_events(self, run: RunHandle) -> AsyncIterator[RunEvent]: ...
    async def collect_artifacts(self, run: RunHandle) -> list[Artifact]: ...
```

### 12.2 Capability discovery

The adapter returns a structured capability set, not only a version string.

Example:

```json
{
  "sparkVersion": "4.2.0",
  "sdp": true,
  "dryRun": true,
  "selectiveRefresh": true,
  "fullRefresh": true,
  "sparkConnect": true,
  "sinks": true,
  "autoCdcScd1": true,
  "provider": "apache",
  "providerExtensions": []
}
```

### 12.3 Local Spark adapter

The reference adapter.

Execution strategy:

- Run `spark-pipelines` as a subprocess with an argument array, never `shell=True`.
- Set the project working directory explicitly.
- Add run-specific Spark config for event logging.
- Capture stdout/stderr incrementally.
- Parse structured Spark/PySpark error classes where possible.
- Persist the process id and run state.
- Support cancellation with graceful termination then forced kill after policy timeout.
- Detect orphaned processes after server restart.

Commands:

```text
spark-pipelines dry-run --spec <spec>
spark-pipelines run --spec <spec>
spark-pipelines run --spec <spec> --refresh a,b
spark-pipelines run --spec <spec> --full-refresh a
spark-pipelines run --spec <spec> --full-refresh-all
```

The adapter must detect the actual CLI syntax from the installed runtime and reject unsupported options rather than guessing.

### 12.4 Spark Connect adapter

Use the official SDP remote mode where supported.

Primary execution form:

```text
spark-pipelines run --remote sc://host:port ...
```

Secrets such as tokens or TLS material are injected at execution time and never serialized into project files.

### 12.5 Kubernetes adapter

The Kubernetes adapter is provider-neutral and based on native Apache Spark Kubernetes support.

MVP responsibilities:

- Select kubeconfig context or in-cluster service account.
- Validate cluster connectivity and RBAC.
- Configure namespace.
- Configure Spark driver/executor image.
- Configure driver/executor CPU and memory.
- Configure service account.
- Configure image pull secrets by reference.
- Configure Spark properties.
- Stage project artifacts to a configured accessible location when required.
- Submit SDP execution using the `spark-pipelines`/`spark-submit` compatible argument model.
- Track driver pod and executor pods.
- Stream pod logs.
- Cancel application.
- Collect Spark event logs and SDP Studio run metadata.

The adapter must not require a proprietary Kubernetes operator.

A future optional plugin may integrate the Apache Spark Kubernetes Operator or other operator-based deployment systems.

### 12.6 Databricks adapter

Databricks integration is optional and isolated in an extra package, for example `sdpstudio-adapter-databricks`.

It must not be imported by the core server unless configured.

Two modes:

#### Databricks Connect / Spark Connect mode

Use remote Spark for previews and compatible executions where the environment supports the required SDP APIs.

#### Managed pipeline deployment mode

- Authenticate using standard Databricks SDK/CLI-compatible mechanisms.
- Upload or synchronize source code to the configured workspace/Git-backed location.
- Create or update a Lakeflow pipeline configuration.
- Start validation-only or normal updates.
- Support selective refresh/full refresh when provider API supports it.
- Stream update status and events into SDP Studio run history.
- Capture provider pipeline id and update id as external references.

Provider-specific options are kept in environment/runtime configuration, not mixed into the portable graph unless explicitly selected.

### 12.7 Future runtime adapters

Adapter API must allow future implementations for:

- Microsoft Fabric Spark.
- Managed Spark services.
- Remote Spark standalone/YARN gateways.
- Additional Kubernetes submission systems.
- Snowflake as source/sink/export or a separate non-SDP backend if explicitly designed.

---

## 13. Preview and development execution

### 13.1 Node preview

A user can select a node and request a preview.

SDP Studio computes the minimal upstream subgraph needed for that node and compiles it into a debug query that is executed outside the normal SDP materialization contract where appropriate.

Preview controls:

- row limit
- sampling fraction
- deterministic seed
- timeout
- cache TTL
- parameter values

Preview result contains:

- rows
- schema
- null statistics
- approximate distinct counts where enabled
- min/max where meaningful
- numeric summary
- column type information
- query plan
- elapsed time
- bytes/metrics when available

### 13.2 Preview safety

- Preview must be read-only unless the selected operator is explicitly a sink test and the user confirms it.
- Secret values are never returned to the browser.
- Preview sampling settings are not silently written into production generated code.
- The preview compiler marks unsupported custom code and explains why preview cannot be isolated.

### 13.3 Selective development run

For materialized datasets, use native SDP selective refresh controls where possible.

For intermediate visual nodes that are not materialized SDP datasets, use preview/debug execution instead of pretending they are independently refreshable pipeline datasets.

---

## 14. Advanced debugger - primary product differentiator

SDP Studio debugging is graph-aware, data-aware, and Spark-aware.

### 14.1 Debug session snapshot

Each run/debug session records an immutable snapshot:

```text
RunSnapshot
  run_id
  project_id
  pipeline_id
  graph_revision_id
  git_commit
  git_dirty_patch_hash
  generated_source_hash
  runtime_profile_id
  runtime_capabilities
  spark_version
  spark_conf_redacted
  parameters_redacted
  start/end/status
  node_execution_summary[]
  artifacts[]
```

### 14.2 Problems panel

Unifies:

- parser errors
- graph errors
- capability errors
- dry-run errors
- Spark analysis errors
- runtime failures
- quality failures
- Git conflicts that affect generated files

Every problem should include:

- severity
- error class/code when available
- human-readable summary
- source file/line
- graph node
- probable cause
- suggested action
- documentation link if configured

### 14.3 Spark Plan Inspector

For supported previews and queries show:

- logical plan
- analyzed plan
- optimized plan
- physical plan
- formatted explain output

Visualize plan nodes and highlight:

- exchanges/shuffles
- broadcast joins
- sort-merge joins
- Cartesian products
- scans
- filters and pushdown
- aggregations
- Python UDF boundaries
- adaptive plan changes when observable

### 14.4 Plan Diff

Compare two revisions or runs and highlight:

- operators added/removed
- join strategy changes
- new/removed exchanges
- changed partitioning
- changed scans
- changed filters/pushdown
- estimated or observed metric changes

A plan regression warning is advisory, not a correctness error.

### 14.5 Run Diff / Pipeline Time Travel

Select any two run snapshots and compare:

- graph revision
- source diff
- parameters
- Spark config
- runtime version/capabilities
- dataset durations
- row counts
- shuffle bytes
- failures/warnings
- schema changes
- quality changes

The UI should answer: **what changed between the last good run and this bad run?**

### 14.6 Graph performance heatmap

Overlay run metrics on the visual graph.

Node detail shows current, previous, and delta values.

### 14.7 Skew detector

Parse Spark event-log/task metrics and compute, per stage where data exists:

- task duration p50/p95/max
- input bytes p50/p95/max
- shuffle read p50/p95/max
- shuffle write p50/p95/max
- spill
- GC time
- scheduler delay where available

Default skew heuristic should be configurable and documented, for example flagging a stage when max task duration is both materially large and several multiples of median/p50.

Never present a heuristic as certainty. Show the actual distribution behind the warning.

### 14.8 Row Trace

A unique visual debugger for built-in deterministic operators.

Workflow:

1. User selects one or more rows in a source/intermediate preview.
2. SDP Studio creates a debug-only trace identity.
3. SDP Studio replays the supported subgraph with trace metadata carried alongside the data.
4. The UI shows how selected rows were filtered, transformed, joined, duplicated, aggregated, or dropped at each visual operator.

Rules:

- Never modify production generated code merely to support a trace.
- Trace runs are isolated debug compilations.
- Aggregation changes row identity; the UI displays lineage from contributing trace ids instead of pretending one-to-one identity.
- Arbitrary Python UDF/custom code may break traceability; mark trace as `unknown across custom boundary`.
- Streaming row trace in MVP operates on captured/sampled micro-batch input, not an unbounded live stream.

### 14.9 Schema Evolution Timeline

Per dataset/node, record schema fingerprints and display changes across runs:

- added column
- removed column
- type change
- nullability change when observable
- nested field change
- order-only change

Support contract rules that can block or warn on breaking changes.

### 14.10 Data Profile Diff

Compare selected profile metrics across runs to detect large distribution shifts.

MVP profile metrics:

- row count when available
- null percentage
- approximate distinct
- min/max
- mean/stddev for numeric types
- top values with configurable cap

This feature is opt-in for sensitive datasets and can be disabled globally.

### 14.11 Failure diagnostics engine

Implement an open, deterministic rule engine before any AI integration.

Inputs:

- Spark error class
- exception chain
- selected log lines
- plan metadata
- runtime capability metadata
- operator context

Outputs:

- categorized cause
- explanation
- relevant node/file
- recommended checks

Rules are YAML/JSON data files shipped in the repository and are independently testable.

### 14.12 Debug bundle

`Export Debug Bundle` creates a ZIP containing, subject to redaction policy:

- run metadata
- graph snapshot
- source snapshot or diff
- runtime capability document
- redacted Spark config
- logs
- event-log summary or event log if explicitly allowed
- plans
- problem list
- schema fingerprints

Before export, show a redaction preview and scan for registered secrets.

### 14.13 Streaming diagnostics

MVP includes:

- checkpoint path display
- last progress data when available
- input/processed rates when available
- state/operator metrics when exposed by the runtime
- watermark-related metadata when exposed

A deep state-store browser is post-MVP unless a stable portable API is available.

---

## 15. Git and source-control integration

### 15.1 Generic Git support

SDP Studio uses normal Git repositories on disk and invokes Git through a safe argument-array wrapper.

MVP operations:

- initialize
- clone
- status
- diff
- stage/unstage
- commit
- log
- branch list/create/switch/delete
- fetch
- pull
- push
- tag list/create
- stash list/create/apply
- conflict detection

Avoid reimplementing Git semantics in JavaScript.

### 15.2 Credential model

Prefer existing Git credential helpers, SSH agent, and system keychain integration.

Do not store plaintext Git passwords/tokens in project files.

### 15.3 Visual Git diff

For `.sdpstudio` documents, render a semantic graph diff:

- node added/removed
- operator type changed
- configuration changed
- edge added/removed
- materialization changed
- runtime compatibility changed

Show the equivalent generated source diff beside it.

### 15.4 GitHub integration

Optional provider plugin using API credentials or OAuth where deployed.

MVP:

- repository metadata
- current branch remote status
- open pull request list for current project
- create pull request
- link commit/branch to PR
- open PR in provider UI

### 15.5 GitLab integration

Same scope using merge requests.

### 15.6 Compatible Git providers

Generic Git clone/pull/push must work without a provider plugin for any compatible remote.

Provider-specific plugins can later add review APIs for Bitbucket, Azure DevOps, Gitea/Forgejo, and others.

---

## 16. Local history

Git is not enough for every editor action.

SDP Studio keeps local history for graph and code documents.

Requirements:

- Auto-snapshot after debounced meaningful change.
- Snapshot before code generation that may rewrite a file.
- Snapshot before import/migration.
- Snapshot before Git checkout/pull conflict resolution.
- Retention policy by count and age.
- Named checkpoints.
- Restore entire project or selected file/document.
- Diff snapshot against current state.

Local history data is stored outside the Git working tree by default.

---

## 17. Collaboration and team server

### 17.1 Modes

#### Local mode

- SQLite database.
- One user.
- Bind to `127.0.0.1` by default.
- Authentication optional on loopback.
- Embedded worker.
- Filesystem artifact store.

#### Team server mode

- PostgreSQL database.
- Authentication mandatory.
- Multiple users.
- Shared filesystem/PVC for project working copies and artifacts in MVP.
- Dedicated worker process supported.
- Real-time presence and collaborative document updates.

### 17.2 Roles

Workspace roles:

- Admin.
- Editor.
- Viewer.

Project-level overrides may narrow permissions.

Permissions:

| Action | Viewer | Editor | Admin |
|---|---:|---:|---:|
| View graph/code | yes | yes | yes |
| Preview | optional policy | yes | yes |
| Edit | no | yes | yes |
| Git commit/push | no | yes | yes |
| Run non-prod | no | yes | yes |
| Run protected environment | no | policy | yes |
| Manage runtime/secrets | no | no | yes |
| Manage users | no | no | yes |

### 17.3 Real-time editing

Use CRDT collaboration for the visual document and text buffers, preferably Yjs-compatible semantics.

Requirements:

- Presence avatars.
- Selected node/cursor presence.
- Concurrent text editing.
- Concurrent graph editing.
- Offline/reconnect merge where supported.
- Server persistence.
- Awareness updates are ephemeral; document updates are durable.

Git operations remain serialized per working copy. A server-side repository lock prevents simultaneous destructive checkout/rebase operations.

### 17.4 Audit events

Record security-relevant team actions:

- login/logout
- role changes
- secret changes (name only, never value)
- runtime profile changes
- run start/cancel
- schedule changes
- Git push
- protected-environment actions

---

## 18. Scheduling

SDP Studio is not a general workflow orchestrator, but a production-usable pipeline server needs basic scheduling.

MVP scheduler supports:

- cron expression
- timezone
- environment/runtime selection
- parameter overrides
- incremental run
- full refresh all
- selected refresh/full refresh
- enable/disable
- concurrency policy: allow / forbid / replace
- missed-run policy: skip / run once on recovery
- maximum concurrent runs per project/runtime

Schedules are stored in the database and evaluated by a scheduler loop with database locking so one schedule is claimed once.

Local mode schedules only run while SDP Studio is running and the UI must make that limitation explicit.

---

## 19. Server architecture

### 19.1 Logical components

```text
Browser
  |
  | HTTPS / WebSocket
  v
SDP Studio API Server
  |-- Auth / RBAC
  |-- Project service
  |-- Visual document service
  |-- Codegen service
  |-- Git service
  |-- Run service
  |-- Debug service
  |-- Collaboration gateway
  |-- Scheduler
  |
  +---- Database (SQLite local / PostgreSQL team)
  +---- Project workspaces (filesystem)
  +---- Artifact store (filesystem MVP)
  |
  v
SDP Studio Worker / Runner Gateway
  |-- Local Spark adapter
  |-- Spark Connect adapter
  |-- Kubernetes adapter
  +-- Databricks adapter (optional)
```

### 19.2 Process model

Development/local:

```text
sdpstudio serve --open
  -> API server
  -> embedded worker
  -> embedded scheduler
  -> SQLite
```

Team:

```text
sdpstudio-server
sdpstudio-worker
postgres
shared project/artifact volume
```

The first production deployment supports one API server replica. Multi-replica API scaling is post-MVP unless collaboration/event routing is backed by a shared pub/sub layer.

### 19.3 Backend technology

Recommended:

- Python 3.12.
- FastAPI.
- Pydantic v2.
- SQLAlchemy 2 async.
- Alembic.
- Uvicorn.
- PostgreSQL 16+ for team mode.
- SQLite WAL for local mode.
- WebSockets for run events and collaboration transport.
- `asyncio` subprocess APIs.
- LibCST for Python source transformations.
- SQLGlot for SQL parsing/generation.
- Kubernetes Python client for K8s control plane operations.
- Optional Databricks SDK extra.
- OpenTelemetry instrumentation.
- Prometheus-compatible metrics endpoint.

### 19.4 Frontend technology

Recommended:

- TypeScript.
- React.
- Vite.
- `@xyflow/react` for node canvas.
- Monaco Editor.
- TanStack Query.
- Zustand for local UI state.
- React Hook Form + Zod for operator configuration forms.
- Yjs for collaboration state.
- Accessible headless UI primitives.
- Vitest + Testing Library.
- Playwright for end-to-end tests.

Do not adopt a heavy full-stack React framework unless a concrete SSR requirement appears. SDP Studio is an authenticated engineering SPA.

The production frontend MUST migrate away from dependency-light prototype HTML/JavaScript and use React + TypeScript + XYFlow + Monaco as the supported UI architecture. The browser must remain a client of the same backend/core APIs used by the CLI.

### 19.5 API style

- REST/JSON for durable resources and commands.
- WebSocket for live run events and collaboration.
- OpenAPI generated by FastAPI.
- Generate the TypeScript API client from OpenAPI in CI.
- Use ULID ids externally.
- UTC timestamps in RFC3339.
- Optimistic concurrency with `revision`/ETag for non-CRDT resources.

---

## 20. Backend package architecture

```text
python/
  sdpstudio_core/
    domain/
    ir/
    capabilities/
    validation/
    operators/
    migrations/
  sdpstudio_codegen/
    python_backend/
    sql_backend/
    importer/
    source_maps/
  sdpstudio_runtime/
    debug/
    quality/
    instrumentation/
  sdpstudio_runners/
    base/
    local/
    connect/
    kubernetes/
  sdpstudio_adapters_databricks/
  sdpstudio_server/
    api/
    auth/
    db/
    services/
    collaboration/
    scheduling/
    workers/
    security/
  sdpstudio_cli/
```

Rules:

- `sdpstudio_core` cannot import server or provider adapter packages.
- `sdpstudio_codegen` can import `sdpstudio_core`, not FastAPI.
- Runtime adapters depend on `sdpstudio_core` contracts, not UI code.
- Provider-specific packages are optional extras.
- API Pydantic models are not the same classes as persistence ORM models.

---

## 21. Frontend package architecture

```text
web/
  src/
    app/
    api/
    components/
    features/
      canvas/
      code/
      explorer/
      operators/
      inspector/
      preview/
      git/
      runs/
      debug/
      settings/
      collaboration/
    state/
    hooks/
    workers/
    styles/
    test/
```

Important boundary:

The browser never compiles executable Python by concatenating strings. Code generation is a backend/core function so CLI, API, and UI all produce identical output.

---

## 22. Database model

Minimum tables/entities:

### `users`

- id
- email
- display_name
- password_hash nullable
- oidc_subject nullable
- is_active
- created_at
- last_login_at

### `workspaces`

- id
- name
- settings_json
- created_at

### `workspace_members`

- workspace_id
- user_id
- role

### `projects`

- id
- workspace_id
- name
- slug
- root_path
- repository_id nullable
- created_at
- updated_at

### `repositories`

- id
- project_id
- remote_url_redacted
- provider_type
- default_branch
- working_copy_path
- created_at

### `documents`

- id
- project_id
- path
- kind
- revision
- content_hash
- updated_at

CRDT payloads may be stored in a dedicated table/blob store rather than this row.

### `local_revisions`

- id
- project_id
- document_path
- revision_no
- content_blob/path
- content_hash
- reason
- user_id nullable
- created_at

### `runtime_profiles`

- id
- workspace_id
- name
- adapter_type
- config_encrypted_or_redacted_json
- is_protected
- created_at
- updated_at

### `secrets`

- id
- workspace_id
- name
- encrypted_value
- key_version
- created_at
- updated_at

### `runs`

- id
- project_id
- pipeline_id
- user_id nullable
- runtime_profile_id
- run_type
- status
- graph_revision_hash
- git_commit nullable
- git_dirty
- dirty_patch_hash nullable
- source_hash
- external_run_id nullable
- started_at
- ended_at nullable
- error_summary nullable

### `run_events`

- id/bigint sequence
- run_id
- ts
- event_type
- severity
- node_id nullable
- payload_json

### `artifacts`

- id
- run_id
- kind
- path_or_uri
- content_type
- size_bytes
- sha256
- metadata_json

### `node_snapshots`

- id
- run_id
- node_id
- schema_json nullable
- profile_json nullable
- metrics_json nullable
- plan_artifact_id nullable

### `schedules`

- id
- project_id
- pipeline_id
- runtime_profile_id
- cron
- timezone
- parameters_encrypted_or_ref_json
- run_mode_json
- concurrency_policy
- missed_run_policy
- enabled
- next_fire_at
- last_fire_at nullable

### `audit_events`

- id
- workspace_id
- actor_user_id nullable
- event_type
- target_type
- target_id nullable
- metadata_redacted_json
- created_at

---

## 23. REST API surface

All paths versioned under `/api/v1`.

### Projects and documents

```text
GET    /projects
POST   /projects
GET    /projects/{project_id}
PATCH  /projects/{project_id}
DELETE /projects/{project_id}
GET    /projects/{project_id}/tree
GET    /projects/{project_id}/files/{path}
PUT    /projects/{project_id}/files/{path}
POST   /projects/{project_id}/import
POST   /projects/{project_id}/generate
POST   /projects/{project_id}/validate-model
```

### Pipelines/canvas

```text
GET    /projects/{project_id}/pipelines
POST   /projects/{project_id}/pipelines
GET    /pipelines/{pipeline_id}
PUT    /pipelines/{pipeline_id}
POST   /pipelines/{pipeline_id}/validate
POST   /pipelines/{pipeline_id}/preview
GET    /pipelines/{pipeline_id}/compatibility
```

### Runs

```text
POST   /pipelines/{pipeline_id}/runs
GET    /runs/{run_id}
POST   /runs/{run_id}/cancel
GET    /runs/{run_id}/events
GET    /runs/{run_id}/artifacts
GET    /runs/{run_id}/nodes/{node_id}
POST   /runs/compare
POST   /runs/{run_id}/debug-bundle
```

### Runtime profiles

```text
GET    /runtime-profiles
POST   /runtime-profiles
GET    /runtime-profiles/{id}
PATCH  /runtime-profiles/{id}
DELETE /runtime-profiles/{id}
POST   /runtime-profiles/{id}/probe
POST   /runtime-profiles/{id}/test
```

### Git

```text
GET    /projects/{id}/git/status
GET    /projects/{id}/git/diff
GET    /projects/{id}/git/log
POST   /projects/{id}/git/stage
POST   /projects/{id}/git/unstage
POST   /projects/{id}/git/commit
POST   /projects/{id}/git/fetch
POST   /projects/{id}/git/pull
POST   /projects/{id}/git/push
GET    /projects/{id}/git/branches
POST   /projects/{id}/git/branches
POST   /projects/{id}/git/checkout
GET    /projects/{id}/git/conflicts
```

### History

```text
GET    /projects/{id}/history
GET    /projects/{id}/history/{revision_id}
POST   /projects/{id}/history/{revision_id}/restore
```

### Schedules

```text
GET    /schedules
POST   /schedules
PATCH  /schedules/{id}
DELETE /schedules/{id}
POST   /schedules/{id}/run-now
```

### Secrets

```text
GET    /secrets                  # names/metadata only
POST   /secrets
PUT    /secrets/{name}
DELETE /secrets/{name}
```

There is never a `GET` endpoint returning decrypted secret values.

### Provider review APIs

```text
GET    /projects/{id}/reviews
POST   /projects/{id}/reviews
```

Provider plugin handles GitHub PR vs GitLab MR details.

---

## 24. WebSocket protocols

### `/ws/runs/{run_id}`

Server events:

```json
{"type":"run.status","status":"RUNNING"}
{"type":"run.log","stream":"stderr","message":"..."}
{"type":"run.problem","problem":{}}
{"type":"node.metrics","nodeId":"...","metrics":{}}
{"type":"run.status","status":"SUCCEEDED"}
```

### `/ws/collab/{project_id}`

Carries:

- CRDT binary updates.
- Presence/awareness.
- Reconnect state vector exchange.

Run events and CRDT traffic should remain logically separate even if they share infrastructure.

---

## 25. Run state machine

```text
CREATED
  -> QUEUED
  -> PREPARING
  -> VALIDATING (optional)
  -> SUBMITTING
  -> RUNNING
  -> COLLECTING_ARTIFACTS
  -> SUCCEEDED

Terminal alternatives:
  VALIDATION_FAILED
  FAILED
  CANCELED
  LOST
```

State transitions must be idempotent and persisted before emitting final UI events.

On server startup, runs left in non-terminal states are reconciled with their adapter. If the external run cannot be found, mark `LOST` with explanation rather than inventing success/failure.

---

## 26. Security specification

### 26.1 Network defaults

- Local mode binds only to loopback by default.
- Binding to a non-loopback address requires auth configuration or explicit `--insecure-dev`.
- Production docs require TLS termination.

### 26.2 Authentication

MVP team mode:

- Local account bootstrap with Argon2id password hashing.
- Generic OpenID Connect provider support.
- Secure HTTP-only session cookies.
- CSRF protection for cookie-authenticated state-changing requests.
- OIDC state/nonce validation.

### 26.3 Authorization

Every project, run, secret, runtime, schedule, and Git mutation endpoint checks RBAC server-side.

UI hiding is never considered authorization.

### 26.4 Secret storage

- AES-GCM envelope encryption or equivalent authenticated encryption.
- Server master key supplied by environment/file secret, not stored in database.
- Key version recorded for rotation.
- Local mode can use OS keyring when available, with encrypted file fallback.
- Decrypted values exist only in memory for the minimum required execution interval.

### 26.5 Log redaction

Maintain a redaction registry of secret values loaded for a run plus common credential patterns.

Redact before persistence and before WebSocket emission.

### 26.6 Command execution

- Never use shell interpolation for Git/Spark/Kubernetes CLI commands.
- Pass explicit argument arrays.
- Validate paths against the project workspace root.
- Reject path traversal.
- Set execution cwd explicitly.
- Apply process resource/time limits where practical.

### 26.7 Git safety

- Never automatically execute repository hooks from untrusted cloned projects in server mode.
- Configure a safe Git environment.
- Document whether hooks are disabled or sandboxed.
- Treat repository content as untrusted.

### 26.8 Kubernetes safety

- Namespace allowlist.
- Service account is configured by admin.
- Do not require cluster-admin.
- Do not expose kubeconfig content to browser.
- Restrict pod template paths and secret references according to admin policy.

### 26.9 Browser security

- CSP.
- SameSite cookies.
- Secure cookies under HTTPS.
- Frame-ancestors policy.
- Strict MIME handling.
- Sanitize Markdown/HTML previews.
- Never render arbitrary Spark data as trusted HTML.

---

## 27. Observability of SDP Studio itself

The product should be operable like a serious server.

Provide:

- structured JSON logs in server mode
- human logs in local dev mode
- request id
- run id in relevant log context
- OpenTelemetry traces
- Prometheus-compatible metrics
- health endpoints
- readiness endpoint that checks DB and storage

Minimum metrics:

- HTTP request count/latency
- active WebSockets
- queued/running runs
- run duration by adapter/status
- worker heartbeat
- schedule execution count
- code generation duration
- preview duration
- Git operation duration

Never use mandatory remote telemetry. Anonymous telemetry, if ever added, must be opt-in.

---

## 28. Plugin architecture

### 28.1 Plugin types

- Operator plugin.
- Runtime adapter plugin.
- Git provider/review plugin.
- Catalog browser plugin.
- Importer/codegen backend plugin.
- Diagnostic rule pack.

### 28.2 Discovery

Python-side plugins use standard Python package entry points.

Example groups:

```text
sdpstudio.operators
sdpstudio.runtimes
sdpstudio.git_providers
sdpstudio.catalogs
sdpstudio.diagnostics
```

Frontend extensions are not arbitrary remote JavaScript in MVP. UI extension metadata for server-installed plugins is constrained to JSON schemas and known renderer primitives. This avoids turning the server into an unsafe browser extension platform.

### 28.3 Compatibility

Every plugin declares:

- plugin API version
- plugin version
- required SDP Studio version range
- capabilities
- license metadata

An incompatible plugin is disabled with a clear startup warning.

---

## 29. CLI specification

Installable command: `sdpstudio`.

```text
sdpstudio serve [--open] [--host] [--port]
sdpstudio doctor
sdpstudio init <directory>
sdpstudio import <directory>
sdpstudio generate [--check]
sdpstudio validate [--runtime <name>]
sdpstudio run [--runtime <name>] [--refresh ...] [--full-refresh ...]
sdpstudio preview <node-id> [--limit N]
sdpstudio history list
sdpstudio history restore <id>
sdpstudio debug bundle <run-id>
sdpstudio runtime list
sdpstudio runtime probe <name>
sdpstudio version
```

`sdpstudio generate --check` exits non-zero if committed generated code differs from graph output. This is important for CI.

`sdpstudio validate` performs, in order:

1. project schema validation
2. graph validation
3. code generation in memory
4. lint/static checks
5. runtime capability validation
6. `spark-pipelines dry-run` when the selected runtime is available

---

## 30. CI/CD integration for user projects

SDP Studio ships examples for GitHub Actions and GitLab CI.

Reference CI flow:

```text
checkout
setup Python/Java/Spark dependency
install project + SDP Studio CLI
sdpstudio generate --check
sdpstudio validate --runtime ci-local
pytest
```

Optional deployment stage invokes a runtime adapter using environment-provided credentials.

Do not force users to run the SDP Studio web server in CI.

---

## 31. Repository architecture

Recommended monorepo:

```text
sdp-studio/
  AGENTS.md
  LICENSE
  NOTICE
  README.md
  SECURITY.md
  CONTRIBUTING.md
  CODE_OF_CONDUCT.md
  GOVERNANCE.md
  TRADEMARKS.md
  THIRD_PARTY_NOTICES.md
  pyproject.toml
  package.json
  pnpm-workspace.yaml
  Makefile
  docker-compose.yml
  docs/
    architecture/
    concepts/
    guides/
    reference/
    adr/
  python/
    sdpstudio_core/
    sdpstudio_codegen/
    sdpstudio_runtime/
    sdpstudio_runners/
    sdpstudio_server/
    sdpstudio_cli/
    sdpstudio_adapters_databricks/
  web/
  tests/
    fixtures/
    golden/
    integration/
    adapter_contract/
    e2e/
  examples/
    batch-retail/
    streaming-kafka/
    cdc-scd1/
  deploy/
    docker/
    helm/
  scripts/
  .github/
  .gitlab/
```

Use `pnpm` for JS workspace management and a single Python `pyproject.toml` workspace strategy supported by the chosen packaging tooling.

---

## 32. Testing strategy

### 32.1 Unit tests

- graph validation
- IR normalization
- operator config validation
- capability evaluation
- code generators
- import parsers
- source map generation
- Git command construction
- security redaction
- scheduler logic
- diagnostic rules
- event-log metric calculations

### 32.2 Golden code-generation tests

For every operator and representative graph, store expected `.py`/`.sql` output.

A golden change requires explicit review.

Assertions:

- deterministic output
- formatter stability
- parser validity
- expected source-map ranges

### 32.3 Round-trip tests

Scenarios:

- graph -> Python -> import -> equivalent IR
- graph -> SQL -> import -> equivalent supported IR
- imported custom code -> save -> exact custom code preserved
- code edit inside supported expression -> graph update
- unsupported code edit -> safe downgrade to custom code

### 32.4 Spark integration tests

Run against real Apache Spark 4.2 in CI for:

- dry-run
- materialized view
- streaming table smoke test
- selective refresh
- full refresh
- sink smoke test where practical
- Auto CDC SCD1 fixture when stable in test environment

### 32.5 Kubernetes tests

Use `kind` in CI/nightly where feasible.

Contract test:

- create namespace/service account
- submit tiny pipeline
- observe run
- retrieve logs
- cancel a long-running test
- clean resources

### 32.6 Databricks tests

Adapter unit tests use mocked SDK boundaries.

Real Databricks integration tests are optional/nightly and require external secrets. They must never be required for contributors to validate the open-source core.

### 32.7 Browser tests

Playwright covers:

- create project
- add/connect/configure nodes
- generated code visible
- validation problem navigation
- preview
- local run
- Git status/commit flow using local bare remote fixture
- history restore
- run comparison
- collaboration with two browser contexts

### 32.8 Security tests

- path traversal
- command injection payloads
- secret redaction
- permission bypass
- CSRF
- unsafe Markdown/HTML
- untrusted Git repository behavior

---

## 33. Performance requirements

MVP target behavior on a normal engineering workstation:

- Canvas remains interactive with 500 nodes.
- Opening a 1,000-node project must not freeze the main browser thread for prolonged synchronous computation; expensive layout/diff operations use Web Workers where appropriate.
- Debounced graph persistence must not write on every pointer movement.
- Code generation for a 500-node supported graph should be architected as an incremental/cacheable operation even if v1 initially performs full compile.
- Run logs are paged/streamed and not held entirely in browser memory.
- Event logs are parsed incrementally and summarized into database/artifacts.
- Table previews are paged/limited.

Do not invent numeric latency SLAs before profiling. Add benchmark baselines to CI and prevent major regressions.

---

## 34. Accessibility and usability

- Keyboard access for all primary actions.
- Visible focus states.
- ARIA labels for canvas controls.
- High-contrast compatible UI.
- Light/dark/system appearance.
- Color is not the sole signal for run status/errors.
- Screen-reader accessible alternatives to graph-only information through table-of-contents and problems views.

---

## 35. Packaging and distribution

MVP releases:

- Python package(s) on PyPI.
- Source tarball.
- OCI container image for server.
- OCI worker image.
- Optional Spark/Kubernetes runner image recipe.
- Helm chart.
- Checksums.
- SBOM.
- Signed release artifacts if project infrastructure supports it.

Local install path:

```text
pipx install sdpstudio
sdpstudio serve --open
```

If the final PyPI package name `sdpstudio` is unavailable or conflicts with existing software, choose a unique distribution identifier while keeping the CLI command `sdpstudio` if legally and technically practical.

---

## 36. Reference local quick start

A clean quick start must be documented approximately as:

```bash
python -m venv .venv
source .venv/bin/activate
pip install "pyspark[pipelines]==4.2.0" sdpstudio
sdpstudio doctor
sdpstudio serve --open
```

The UI wizard then:

1. Creates a project.
2. Creates a local Spark 4.2 runtime profile.
3. Creates `spark-pipeline.yaml`.
4. Adds a sample table/file source.
5. Adds transformations.
6. Adds a materialized view.
7. Shows generated Python.
8. Runs `dry-run` validation.
9. Runs the pipeline.
10. Opens preview and debug metrics.

---

## 37. Architecture decisions to capture as ADRs

Create Architecture Decision Records for at least:

- ADR-001: Apache Spark SDP as core execution contract.
- ADR-002: Visual YAML + generated source dual representation.
- ADR-003: Lossless fallback to custom code instead of arbitrary full reverse compilation.
- ADR-004: Python/FastAPI backend.
- ADR-005: React + XYFlow + Monaco frontend.
- ADR-006: SQLite local / PostgreSQL team.
- ADR-007: DB-backed run queue instead of mandatory Redis.
- ADR-008: Native Spark-on-Kubernetes adapter.
- ADR-009: Databricks as optional provider adapter.
- ADR-010: CRDT collaboration.
- ADR-011: Source maps outside generated code when possible.
- ADR-012: Apache-2.0 single-edition project.
- ADR-013: No mandatory remote telemetry.
- ADR-014: Public naming avoids Apache Spark trademark in product name.

---

## 38. Codex implementation contract

This section is deliberately prescriptive. A coding agent should implement SDP Studio incrementally, preserving a runnable repository after every task.

### 38.1 Rules for Codex

Create `AGENTS.md` at repository root containing these mandatory rules:

1. Read the relevant specification and ADR before editing architecture-level code.
2. Work on one task id at a time unless a task explicitly groups mechanical changes.
3. Do not add a dependency without documenting why it is needed and checking its license.
4. Do not add provider-specific behavior to `sdpstudio_core`.
5. Do not use `shell=True` for external commands.
6. Do not put secret values into logs, exceptions returned to the browser, Git-tracked files, fixtures, or snapshots.
7. Every behavior change requires tests.
8. Every operator requires schema/config tests and at least one golden code-generation test.
9. Every runtime adapter must pass the common adapter contract suite.
10. Generated source must remain deterministic.
11. Never delete or rewrite unsupported imported user code without a lossless fallback.
12. Run format, lint, type-check, unit tests, and relevant integration tests before marking a task complete.
13. Keep commits/task patches focused. Do not opportunistically refactor unrelated areas.
14. API changes require OpenAPI client regeneration and frontend compile.
15. Database model changes require an Alembic migration.
16. Persisted `.sdpstudio` schema changes require a format migration and fixture migration tests.
17. User-visible errors must be actionable and contain a stable problem code.
18. Do not claim a runtime capability solely from provider name; use capability probing/configured version rules.
19. Do not make network calls in core code-generation tests.
20. Keep the default product fully functional with no Databricks credentials.

### 38.2 Task completion report format

For every task, Codex should report:

```text
Task: <id> <name>
Implemented:
- ...
Files changed:
- ...
Tests added/updated:
- ...
Commands run:
- ...
Acceptance criteria:
- PASS/FAIL ...
Risks/follow-ups:
- ...
```

### 38.3 Master Codex prompt

Use this as the root instruction when implementing the repository:

```text
You are implementing SDP Studio, an Apache-2.0 open-source visual IDE and collaborative server for Apache Spark Declarative Pipelines.

Read AGENTS.md, this specification, and all ADRs relevant to the assigned task before changing code.

Implement only the assigned task and its necessary prerequisites. Keep the repository runnable and tests green. Prefer simple, explicit code over framework magic. Maintain strict boundaries between the Spark/IR core, code generation, server, runtime adapters, and frontend. Never introduce a mandatory Databricks dependency. Never lose imported user code. Never expose secrets. Never execute external commands through a shell string.

For changes to generated code, add or update golden fixtures. For runtime changes, run adapter contract tests. For REST changes, regenerate the TypeScript OpenAPI client. For persisted formats or database schemas, include migrations.

At completion, provide the standard task completion report from AGENTS.md.
```

---

## 39. Build plan overview

Build in this dependency order:

```text
Phase 0  Repository and quality foundations
Phase 1  Domain model, schemas, graph, capability engine
Phase 2  Code generation and import/round-trip
Phase 3  Server persistence and project APIs
Phase 4  Frontend shell, project explorer, canvas, inspector
Phase 5  Operator library and generated-code workflow
Phase 6  Local Spark execution, preview, validation, run history
Phase 7  Advanced debugger
Phase 8  Git and local history
Phase 9  Authentication, collaboration, RBAC, schedules
Phase 10 Spark Connect and Kubernetes adapters
Phase 11 Databricks optional adapter
Phase 12 Packaging, docs, security hardening, release qualification
```

Do not begin provider integrations before the common runtime contract and local adapter are stable.

---

# Phase 0 - Repository and quality foundations

## SDPS-0001 - Create repository skeleton

**Goal**: Create the monorepo layout from section 31.

**Files**:

- root legal/community files
- `python/*`
- `web/`
- `tests/*`
- `docs/*`
- `examples/*`
- `deploy/*`

**Implementation**:

- Add Apache-2.0 license.
- Add placeholder NOTICE and third-party notices process.
- Add Python package namespaces.
- Add pnpm workspace.
- Add root Makefile with discoverable targets.
- Add `.editorconfig`, `.gitignore`, `.gitattributes`.

**Acceptance**:

- `python -c "import ..."` smoke imports work for created packages.
- `pnpm install` and `pnpm -r build` complete for minimal web shell.
- Root README explains project status and trademark-safe naming.

## SDPS-0002 - Python toolchain

**Goal**: Establish deterministic Python development tooling.

**Implementation**:

- Python >=3.12 for SDP Studio application code.
- Configure Ruff lint + format.
- Configure Pyright or mypy; choose one and enforce it.
- Configure pytest, pytest-asyncio, coverage.
- Configure package extras: `server`, `kubernetes`, `databricks`, `dev`.
- Keep `pyspark` test/runtime dependency explicitly versioned in integration environment, not imported at server startup unless needed.

**Acceptance**:

```text
make python-format-check
make python-lint
make python-typecheck
make python-test
```

all pass on clean checkout.

## SDPS-0003 - Frontend toolchain

**Goal**: Establish TypeScript/React application.

**Implementation**:

- Vite + React + TypeScript strict mode.
- ESLint.
- Prettier if retained; avoid formatter conflicts.
- Vitest + Testing Library.
- Playwright project skeleton.
- Basic accessible app shell.

**Acceptance**:

```text
pnpm --filter web lint
pnpm --filter web test
pnpm --filter web build
```

pass.

## SDPS-0004 - CI workflows

**Goal**: Make every pull request enforce baseline quality.

**Implementation**:

GitHub Actions primary reference and equivalent GitLab CI sample.

Jobs:

- Python lint/type/unit.
- Web lint/unit/build.
- Package build.
- License scan.
- Secret scan.
- Dependency vulnerability scan where practical.

Add caching without making CI correctness depend on cache.

**Acceptance**: intentionally broken lint/test causes relevant job to fail.

## SDPS-0005 - Documentation and ADR framework

Create ADR template and ADR-001 through ADR-014 from this spec with concise rationale/decision/consequences.

**Acceptance**: docs build or Markdown link checker passes.

## SDPS-0006 - Stable ids, errors, and result primitives

In `sdpstudio_core` implement:

- ULID generation/validation.
- UTC time helpers.
- `Problem` model with stable code, severity, message, source location, node id, details, remediation.
- `Result[T]`/exception policy for core APIs.

Test serialization and deterministic behavior where applicable.

---

# Phase 1 - Domain model, graph, and capability engine

## SDPS-0101 - Versioned project schemas

Implement Pydantic domain models for:

- project metadata
- pipeline document
- nodes
- ports
- edges
- position/layout
- parameters
- environment references

Use discriminated unions for node config types where appropriate.

Add JSON Schema export for frontend/operator use.

**Acceptance**:

- valid fixtures parse.
- invalid duplicate ids fail.
- unknown future fields follow an explicit policy.
- schema version is required.

## SDPS-0102 - YAML serializer

Implement safe YAML load/save.

Requirements:

- no arbitrary object constructors
- stable key ordering where chosen
- normalized newline
- atomic save through temp + rename
- backup hook before migrations

Golden test emitted YAML.

## SDPS-0103 - Graph index

Build immutable or clearly controlled graph index with:

- node lookup
- incoming/outgoing edge lookup
- topological order
- ancestors
- descendants
- connected components
- materialization boundaries

Use iterative algorithms to avoid recursion failure on large graphs.

## SDPS-0104 - Graph validation pass

Detect:

- duplicate ids
- missing edge endpoints
- unknown ports
- invalid cardinality
- cycles
- disconnected required inputs
- incompatible batch/stream edge semantics
- missing output/materialization requirements

Return a list of `Problem`, not first-error-only.

## SDPS-0105 - Operator registry API

Implement `OperatorDefinition` and registry.

Definition fields:

- id/version/title/category
- input/output port declarations
- config schema
- UI schema metadata
- runtime modes
- code targets
- required capabilities
- validator hooks
- compiler hooks identifiers
- docs key

Core registry can load built-ins and Python entry-point plugins.

## SDPS-0106 - Capability model

Implement `RuntimeCapabilities` with named boolean/versioned features.

Capabilities include at least:

```text
sdp
python
sql
materialized_view
streaming_table
temporary_view
append_flow
sink
selective_refresh
full_refresh
spark_connect
auto_cdc_scd1
kubernetes
provider_extensions.<name>
```

Do not hardcode editor checks to provider names.

## SDPS-0107 - Capability validation

For a pipeline + runtime capability document, return:

- errors for impossible execution
- warnings for downgraded semantics
- portability badges
- list of provider-specific features used

Unit-test mixed graphs.

## SDPS-0108 - Canonical IR base

Create IR dataclasses/models independent from persisted UI position.

Objects:

- IRProject
- IRPipeline
- IRDataset
- IRFlow
- IRSource
- IRTransform
- IRSink
- IRParameterRef
- IRSecretRef
- IRExpression

Every IR object carries `origin_node_id` and optional source location.

## SDPS-0109 - Visual graph to IR lowering

Implement lowering passes for initial source/filter/select/join/aggregate/materialized-view subset.

Pass ordering:

1. resolve graph
2. resolve names
3. propagate mode batch/stream
4. validate operator semantics
5. create transform expression tree/DAG
6. assign output dataset
7. normalize

Golden IR snapshots.

## SDPS-0110 - Persisted schema migration framework

Implement migration registry:

```python
migrate(document, from_version, to_version)
```

Add a synthetic v0 -> v1 fixture to prove backup + migration behavior.

---

# Phase 2 - Code generation, parsing, and round-trip

## SDPS-0201 - Codegen backend interface

Create backend contract:

```python
class CodegenBackend(Protocol):
    target: Literal["python", "sql"]
    def supports(self, ir: IRPipeline) -> SupportReport: ...
    def generate(self, ir: IRPipeline, ctx: CodegenContext) -> GeneratedProject: ...
```

`GeneratedProject` contains files, source mappings, problems, and content hashes.

## SDPS-0202 - Deterministic Python file generator

Generate scaffold/imports and materialized view for table source + simple filter/select.

Use structured AST/LibCST construction where practical; do not make templates the semantic model.

Golden fixtures must include:

- simple batch
- renamed output
- expressions
- deterministic imports

## SDPS-0203 - Python transform compiler

Add operators:

- drop/rename/reorder
- cast
- derive column
- null handling
- distinct/dropDuplicates
- aggregate
- join variants
- union by name
- explode
- JSON parse
- window expressions
- watermark where semantically valid

Each operator receives dedicated unit + golden tests.

## SDPS-0204 - Python SDP constructs

Generate:

- `@dp.materialized_view`
- `@dp.table`
- `@dp.temporary_view`
- `dp.create_streaming_table`
- `@dp.append_flow`
- `dp.create_sink`

Ensure source mode and target mode validation.

## SDPS-0205 - Spark 4.2 Auto CDC SCD1 operator

After verifying the actual Spark 4.2 Python API signature in the installed reference package, implement the operator against that signature.

Do not copy a Databricks-only API by assumption.

Tests must import/probe the reference API in Spark integration CI.

## SDPS-0206 - SQL generator base

Use SQLGlot for supported expressions/query AST.

Generate:

- materialized view
- temporary view
- streaming table
- standard select/filter/join/group
- flow syntax where supported

Golden SQL tests.

## SDPS-0207 - Language selection and mixed output

Implement compiler planner that assigns each materialized dataset to Python or SQL based on:

1. user preference
2. operator backend support
3. existing code ownership
4. portability constraints

Explain why a dataset switched to Python.

## SDPS-0208 - Source map generator

Produce line/column ranges after final formatting.

Tests:

- mapped line contains expected generated expression
- generated node click ranges survive formatter
- source map hash matches file

## SDPS-0209 - Python importer SDP discovery

Using LibCST/Python AST, discover dataset/flow declarations and source locations.

Do not execute imported Python.

Tests include decorators with keyword args and multi-file references.

## SDPS-0210 - Python dependency inference

Infer safe obvious reads from:

- `spark.table("literal")`
- `spark.read.table("literal")`
- `spark.readStream.table("literal")`
- supported source builder literals

Dynamic names become unresolved dependency metadata, not guessed edges.

## SDPS-0211 - SQL importer

Parse supported SDP SQL statements and basic relational expressions.

Unsupported syntax becomes custom SQL region with dependency metadata if detectable.

## SDPS-0212 - Custom code preservation model

Implement exact-text custom blocks/files.

Add hash guard so a generator cannot overwrite a code-owned file unless explicitly requested.

Tests prove byte-level preservation for custom region content.

## SDPS-0213 - Round-trip reconciliation

Implement:

- generated file unchanged -> safe regenerate
- supported editable expression changed -> parse back into visual config
- unsupported change -> convert region ownership to custom code
- externally deleted generated file -> recreate only if visual source still owns it and no ambiguity

Provide detailed reconciliation report before write.

## SDPS-0214 - `sdpstudio generate`

CLI command:

- load project
- validate graph
- lower IR
- generate to memory
- compare hashes
- create history snapshot
- write atomically
- write source maps

`--check` writes nothing and exits 1 on drift.

## SDPS-0215 - Project importer CLI

`sdpstudio import <dir>` detects an SDP project and creates `.sdpstudio` metadata without modifying source by default.

Option `--visualize` creates reconstructed visual documents.

Acceptance fixture contains two Python files and one SQL file.

---

# Phase 3 - Server persistence and APIs

## SDPS-0301 - FastAPI application skeleton

Add:

- application factory
- settings model
- lifespan hooks
- request id middleware
- structured error response
- health/readiness endpoints
- OpenAPI metadata

No business logic in route modules.

## SDPS-0302 - Database abstraction

SQLAlchemy async setup supporting SQLite and PostgreSQL.

- migrations via Alembic
- SQLite WAL initialization
- transaction helper
- test database fixtures

## SDPS-0303 - Core persistence models

Implement tables from section 22 except auth/schedules may be initially dormant.

Create migration `0001_initial`.

## SDPS-0304 - Workspace filesystem service

Responsibilities:

- configured root
- normalized project paths
- traversal prevention
- atomic reads/writes
- per-project async lock for destructive filesystem operations
- safe temporary directory creation

Security tests mandatory.

## SDPS-0305 - Project CRUD service/API

Implement project list/create/get/update/delete with soft/safe deletion policy.

Creating project scaffolds minimal `.sdpstudio/project.yaml` and pipeline spec only after validating target directory.

## SDPS-0306 - File tree and file APIs

Support text files only through editor endpoints initially.

- ETag/content hash
- optimistic update conflict
- max file size config
- binary files shown as metadata and not editable in Monaco

## SDPS-0307 - Pipeline document API

Load/save visual documents through core schema.

Write local history snapshot before mutation.

## SDPS-0308 - Generate API

Endpoint calls exactly the same service used by CLI.

Return:

- files changed
- source maps
- problems
- diff summary

Do not duplicate compiler logic in API route.

## SDPS-0309 - Model validation API

Return structured `Problem[]` without needing Spark.

## SDPS-0310 - OpenAPI TypeScript client generation

Add reproducible script and CI check that generated client is up to date.

Frontend may wrap generated client but must not hand-copy server DTOs.

---

# Phase 4 - Frontend shell, explorer, canvas, inspector

## SDPS-0401 - Application shell

Build layout from section 8.1.

Persist panel sizes and theme locally per user/browser.

Keyboard reachable activity rail.

## SDPS-0402 - Project selector and explorer

- project list/create/open
- file tree
- create/rename/delete file where permitted
- modified/conflict badges
- tab opening

## SDPS-0403 - Monaco editor integration

- load/save with ETag
- conflict banner on stale save
- Python/SQL/YAML modes
- problems markers API
- source-map navigation hooks

## SDPS-0404 - XYFlow canvas base

Implement:

- nodes/edges
- pan/zoom
- minimap
- selection
- delete
- copy/paste
- undo/redo command stack
- keyboard shortcuts
- auto-save debounce

Do not implement operator-specific configuration yet.

## SDPS-0405 - Operator palette

Fetch registry metadata from server.

- categories
- text search
- drag to canvas
- disabled operators show reason under current runtime capability set

## SDPS-0406 - Generic node renderer

Node frame displays:

- icon/category
- title/name
- input/output ports
- mode badge
- warning/error badge
- runtime compatibility badge
- run status overlay hook

## SDPS-0407 - Inspector framework

Render config forms from constrained UI/schema metadata.

Support:

- text
- number
- checkbox
- enum
- expression editor
- list/repeater
- key/value options
- secret reference picker

Validate client-side and server-side.

## SDPS-0408 - Edge validation UX

Prevent illegal edge connection and show concise explanation.

Server remains authoritative after save.

## SDPS-0409 - Graph navigation

- search
- fit
- auto-layout using an OSS layout library with acceptable license
- upstream/downstream highlight
- table-of-contents synchronization

## SDPS-0410 - Command palette and context menus

Commands include add operator, delete, duplicate, group, preview, generate, validate, run, fit, layout, open code.

## SDPS-0411 - Problems panel

Display `Problem[]`, filter severity/category, click to node/file line.

---

# Phase 5 - Operator UX and generated-code workflow

## SDPS-0501 - Source operators UI

Implement forms and validation for table, file, JDBC, Kafka, generic source.

Never put secret literal inputs into normal options when a secret reference field is appropriate.

## SDPS-0502 - Core transform operator UI

Implement inspector forms for all relational transforms in section 9.2.

Expression fields provide column suggestions when schema known.

## SDPS-0503 - Dataset/flow/sink UI

Materialized view, streaming table, temporary view, append flow, sink, Auto CDC SCD1 where capability available.

## SDPS-0504 - Code panel generated view

Selecting a node shows generated code region and file.

Actions:

- open full file
- copy region
- show source map
- switch to editable custom block when supported

## SDPS-0505 - Visual/code synchronization UX

On external code change:

- run reconciliation
- show status: synchronized / visual config updated / converted to custom / conflict
- never silently discard changes

## SDPS-0506 - Semantic graph diff component

Given two visual documents, render changes and side-by-side source diff.

This component will later be reused by Git and run comparison.

## SDPS-0507 - Parameter editor

Typed parameter definitions and environment override indicator.

Secret parameter has only secret reference, never literal display.

## SDPS-0508 - Environment editor

Create/select environments and runtime profiles.

Show effective merged settings without revealing secret values.

---

# Phase 6 - Local Spark execution, preview, validation, run history

## SDPS-0601 - Runtime adapter contract package

Implement protocol, request/response models, common errors, status model, artifact model, event model.

Create reusable contract test suite that any adapter fixture can execute.

## SDPS-0602 - Runtime profile persistence/API

CRUD plus adapter type validation.

Sensitive config fields stored as secret refs or encrypted fields.

## SDPS-0603 - Local adapter probe

Probe:

- Python executable
- Java
- `spark-pipelines`
- Spark version
- SDP import
- optional API features

Return capability document and actionable doctor problems.

## SDPS-0604 - `sdpstudio doctor`

Checks local installation and prints machine-readable JSON with `--json`.

Do not fail because Databricks or Kubernetes is absent unless user asks to probe them.

## SDPS-0605 - Safe subprocess runner

Reusable async component:

- args array
- cwd
- controlled environment
- stdout/stderr line streaming
- pid
- termination
- timeout
- redaction

Unit tests use helper scripts, not Spark.

## SDPS-0606 - Local dry-run validation

Execute `spark-pipelines dry-run` and convert failures into `Problem` objects.

Map known file/line data through source maps to graph nodes.

## SDPS-0607 - Run database service

Implement state machine and immutable initial run snapshot metadata.

Persist every transition transactionally.

## SDPS-0608 - DB-backed worker queue

Use database claim rows / `FOR UPDATE SKIP LOCKED` on PostgreSQL with a correct SQLite local fallback.

Worker heartbeat and stale claim recovery.

Do not require Redis.

## SDPS-0609 - Local run submit/monitor/cancel

Support:

- incremental
- selected refresh
- selected full refresh
- full-refresh-all

Persist command metadata with secrets redacted.

## SDPS-0610 - Run event WebSocket

Stream status/log/problem events.

Reconnect client can fetch historical events then resume live sequence.

## SDPS-0611 - Run history UI

- list/filter runs
- status/duration/runtime/commit
- run detail
- logs with virtualized rendering
- cancel action

## SDPS-0612 - Preview compiler service

Compile minimal supported subgraph into an executable preview query/function separate from production SDP declarations.

Explicitly refuse side-effecting/unsupported previews.

## SDPS-0613 - Local preview executor

Execute batch previews against local Spark.

Return Arrow/JSON-safe rows with schema and hard row cap.

Handle large/binary values with safe truncation metadata.

## SDPS-0614 - Preview UI

Bottom panel:

- table
- schema
- profile placeholder
- limit/sample settings
- refresh
- stale cache indicator

## SDPS-0615 - Spark event logging configuration

For local runs, set a run-specific event log directory without overriding user settings unexpectedly.

Record exact effective setting in run metadata.

## SDPS-0616 - Event-log ingestion base

Incrementally parse required Spark listener events into normalized stage/task summaries.

Store raw event log as artifact according to retention policy and summary in database/artifact JSON.

## SDPS-0617 - Catalog browser local

Using configured Spark session/preview runner, list catalogs/namespaces/tables where APIs allow.

Cache briefly; do not block initial app load.

---

# Phase 7 - Advanced debugger

## SDPS-0701 - Query plan capture

For previewable nodes, capture explain representations available through the runtime.

Persist as artifact linked to node snapshot.

## SDPS-0702 - Plan parser/model

Create normalized plan tree for common Spark textual/JSON plan formats.

Unknown plan lines remain raw nodes; parser must fail soft.

## SDPS-0703 - Plan Inspector UI

Tree + text modes.

Highlight exchanges, joins, scans, filters, aggregates, Python boundaries.

Search within plan.

## SDPS-0704 - Plan Diff engine

Normalize unstable ids before diff.

Produce structural diff operations and advisory findings.

Golden tests on plan fixtures.

## SDPS-0705 - Plan Diff UI

Side-by-side and structural change list.

Click plan node to highlight corresponding visual node when source mapping/dependency mapping exists.

## SDPS-0706 - Stage/task metric summarizer

From normalized event data compute quantiles and totals with numerically robust methods.

Store summary schema version.

## SDPS-0707 - Skew diagnostics rules

Implement configurable heuristics and include evidence values in each finding.

Never hardcode a single magic ratio without config/documentation.

## SDPS-0708 - Debug graph overlays

Apply duration/shuffle/skew/rows/freshness overlays to canvas.

Legend always visible when overlay active.

## SDPS-0709 - Schema snapshot and fingerprint

Canonicalize Spark schema JSON and hash it.

Store per preview/run node when available.

## SDPS-0710 - Schema diff engine/UI

Detect nested changes and classify potential compatibility impact.

Allow user contract policy to decide warn vs error.

## SDPS-0711 - Data profiler

Implement opt-in bounded profile queries.

Avoid calling prohibited actions inside SDP definition functions; profiling executes through debug/preview execution.

Config limits:

- row/sample cap
- max profiled columns
- top-values cap
- timeout

## SDPS-0712 - Profile diff

Compare profile snapshots and report absolute/relative changes with `insufficient_data` where comparisons are unreliable.

## SDPS-0713 - Run compare service

Given two runs, produce one comparison DTO including:

- graph semantic diff
- Git/source diff references
- runtime/config diff
- node metric deltas
- schema diffs
- problems delta
- plan diff availability

## SDPS-0714 - Run comparison UI

Single view answering last-good vs current run.

Provide filters: changed only, regressions only, errors only.

## SDPS-0715 - Row Trace debug compiler

Implement trace IR instrumentation for initial operators:

- source
- select/rename/cast/derive
- filter
- join
- union
- explode
- aggregate

For aggregate, maintain contributing trace-set summary with bounded size and overflow marker.

## SDPS-0716 - Row Trace executor

Accept selected preview row ids/values and execute instrumented debug subgraph.

Protect against leaking trace metadata into output tables by never using production pipeline execution.

## SDPS-0717 - Row Trace UI

Show selected records as they move across nodes:

- survived
- filtered
- duplicated
- joined
- aggregated
- unknown after custom code

This is a P0 differentiator and needs an end-to-end test.

## SDPS-0718 - Diagnostic rules engine

YAML rule structure:

```yaml
id: spark.analysis.unresolved-column
match:
  errorClass: UNRESOLVED_COLUMN.*
message: "A referenced column cannot be resolved."
checks:
  - "Compare the node input schema with the expression."
```

Support regex carefully with bounded inputs.

## SDPS-0719 - Initial diagnostic rule pack

Rules for common categories:

- unresolved column/table
- type mismatch
- ambiguous reference
- streaming/batch mismatch
- checkpoint errors
- unsupported SDP action
- session mutation in declarative pipeline
- OOM hints
- missing connector/class
- Kubernetes RBAC/image pull common errors

## SDPS-0720 - Debug bundle exporter

Implement ZIP export and redaction scanner.

Bundle manifest includes SHA256 for every included file.

Test fixtures deliberately include fake secrets and assert removal.

---

# Phase 8 - Git and local history

## SDPS-0801 - Git process wrapper

Safe wrapper around system Git.

- explicit args
- cwd pinned to repo
- controlled env
- timeout
- output cap
- error mapping

## SDPS-0802 - Git repository service

Implement init/clone/status/diff/log/branches.

Parse porcelain machine formats, not human localized output.

## SDPS-0803 - Git mutations

Stage/unstage/commit/fetch/pull/push/stash/tag/checkout.

Add project-level repository operation lock.

## SDPS-0804 - Git credential integration

Do not create a custom plaintext token store for generic Git.

Document/support:

- SSH agent
- credential helper
- HTTPS helper

Provider API tokens use SDP Studio secrets store only for provider API calls.

## SDPS-0805 - Git UI

Source-control panel:

- changed files
- stage controls
- diff
- commit input
- sync controls
- branch picker

## SDPS-0806 - Visual graph Git diff

Read `.sdpstudio` versions from Git blobs without checkout and feed semantic diff engine.

## SDPS-0807 - Conflict UX

Detect conflicts and open text diff editor.

For `.sdpstudio` YAML conflicts, offer:

- text resolution
- ours/theirs
- semantic preview after resolution

Never attempt automatic graph merge if it cannot prove valid ids/edges.

## SDPS-0808 - Local history storage

Implement snapshots outside Git working tree.

Retention configurable.

## SDPS-0809 - Local history UI

Timeline, diff, restore selected document/project.

Restore itself creates a pre-restore snapshot.

## SDPS-0810 - GitHub provider plugin

API abstraction and PR list/create using credentials from secret/OAuth context.

Provider failures never break generic Git functionality.

## SDPS-0811 - GitLab provider plugin

Equivalent MR list/create.

---

# Phase 9 - Authentication, collaboration, RBAC, schedules

## SDPS-0901 - Local user authentication

Implement admin bootstrap and Argon2id password hashing.

First server startup can create admin through CLI/env bootstrap flow without logging password.

## SDPS-0902 - Session security

- secure HTTP-only cookie
- CSRF token
- session expiry
- logout/revocation
- login rate-limit primitive

## SDPS-0903 - OIDC

Generic OIDC discovery/configuration.

Map subject/email/display name safely; workspace role assignment policy defaults to Viewer unless configured/admin-approved.

## SDPS-0904 - RBAC service

Central authorization functions; route dependencies call service.

Create matrix tests for every protected mutation category.

## SDPS-0905 - Secrets service

Authenticated encryption, key version, create/update/delete, reference resolution.

No read-decrypt endpoint.

## SDPS-0906 - Audit log

Emit events listed in section 17.4.

Viewer cannot access sensitive admin audit metadata unless policy allows.

## SDPS-0907 - CRDT persistence model

Implement project/document collaboration storage and periodic compaction/snapshot.

Ensure crash recovery tests.

## SDPS-0908 - Collaboration WebSocket

Authenticate socket before joining project.

Authorize project read/write separately.

Limit message size and connection rate.

## SDPS-0909 - Frontend collaborative text

Bind Monaco document to CRDT for collaborative files where enabled.

Show remote cursors/presence.

## SDPS-0910 - Frontend collaborative canvas

Represent node/edge/config changes in collaborative document.

Do not broadcast raw pointer movement as persistent state.

## SDPS-0911 - Repository operation coordination

When Git checkout/pull/rebase-like operation changes files:

- acquire repo lock
- notify collaborators
- flush CRDT/doc changes
- snapshot local history
- execute Git
- reload affected docs
- reconcile
- release lock

## SDPS-0912 - Scheduler persistence

Implement schedule CRUD and next-fire calculation with timezone-safe library.

Validate cron before save.

## SDPS-0913 - Scheduler worker

Database-claim due schedules.

Implement missed-run and concurrency policies.

Scheduler creates normal `runs` so all debugging/audit behavior is reused.

## SDPS-0914 - Schedule UI

Create/edit/pause, next run display, run history filter by schedule.

Protected runtime requires permission.

---

# Phase 10 - Spark Connect and Kubernetes

## SDPS-1001 - Spark Connect adapter

Build from common adapter contract.

Probe connection and relevant SDP remote capability.

Use official supported `spark-pipelines --remote` path when present.

## SDPS-1002 - Spark Connect preview

Use Spark Connect DataFrame APIs for preview and plan capture where available.

Clearly mark diagnostics that require server-side event logs and are unavailable.

## SDPS-1003 - Kubernetes profile schema

Fields:

- kube context reference
- API endpoint only if explicitly configured
- namespace
- service account
- Spark image
- pull secret refs
- driver cores/memory
- executor cores/memory/instances
- Spark conf
- artifact staging URI
- pod template refs
- labels/annotations allowlisted map

## SDPS-1004 - Kubernetes probe

Check:

- API connectivity
- namespace exists
- permissions needed for submission/status/logging
- configured image metadata syntactically valid
- staging config present if required

Do not require cluster-admin.

## SDPS-1005 - Kubernetes submission command builder

Generate deterministic argument arrays for native Spark Kubernetes submission through SDP CLI.

Unit tests inspect exact args and ensure no secrets appear in persisted display form.

## SDPS-1006 - Artifact staging strategy

Implement one production-safe MVP strategy chosen during spike, for example configured S3-compatible/shared URI supported by Spark file upload semantics.

Do not silently assume local paths exist in driver pods.

Document the strategy and test it in kind integration environment where possible.

## SDPS-1007 - Kubernetes run lifecycle

Submit, track driver, stream logs, status, cancel, collect artifacts.

Store namespace + driver pod/submission id as external run metadata.

## SDPS-1008 - Kubernetes UI

Runtime editor and run detail shows driver/executors, pod phases, relevant events, logs.

No raw kubeconfig displayed.

## SDPS-1009 - Kind adapter contract CI

Create scripted ephemeral cluster test.

Tag expensive test separately but run on release qualification.

---

# Phase 11 - Optional Databricks adapter

## SDPS-1101 - Isolated package and dependency extra

Create `sdpstudio_adapters_databricks` with no imports from core into Databricks SDK.

Core installation remains free of SDK dependency unless extra selected.

## SDPS-1102 - Databricks authentication/profile probe

Support standard SDK configuration patterns.

Probe workspace and pipeline API access.

Never return token to browser.

## SDPS-1103 - Capability mapping

Return open-source SDP capabilities plus provider extensions discovered/configured.

Do not assume feature parity solely because an API name exists.

## SDPS-1104 - Workspace source synchronization

Implement safe upload/sync strategy for pipeline source files or a configured Git-backed root.

Keep provider deployment metadata outside portable graph.

## SDPS-1105 - Pipeline create/update

Map SDP Studio deployment profile to managed pipeline configuration.

Persist provider pipeline id.

## SDPS-1106 - Validate/start update

Use provider APIs for validation-only and run update.

Support selection/full refresh according to current API capability.

## SDPS-1107 - Event/status mapping

Map provider update lifecycle to common SDP Studio run state/events.

Store raw provider payload only after redaction and only when useful for debugging.

## SDPS-1108 - Databricks run UI extensions

Show provider link/id and provider-only metrics separately from portable metrics.

## SDPS-1109 - Optional integration tests

Mocked contract required in normal CI; live test job only when secrets configured.

---

# Phase 12 - Packaging, security, docs, release qualification

## SDPS-1201 - Container image

Multi-stage build:

- frontend compiled assets
- Python server environment
- non-root runtime user
- minimal OS packages
- healthcheck

Do not bake Git/provider credentials.

## SDPS-1202 - Docker Compose team deployment

Services:

- `sdpstudio-server`
- `sdpstudio-worker`
- `postgres`

Persistent volumes for DB and project/artifact storage.

TLS expected at reverse proxy; document local test path.

## SDPS-1203 - Helm chart

Resources:

- server Deployment
- worker Deployment
- Service
- PVC references
- ConfigMap
- Secret references
- optional Ingress
- NetworkPolicy example

PostgreSQL is external/by-reference by default rather than bundling a production DB chart.

## SDPS-1204 - SBOM and release metadata

Generate SPDX or CycloneDX SBOM for Python/JS/container artifacts.

Publish checksums.

## SDPS-1205 - License compliance gate

Automated inventory and denylist/review list.

Update `THIRD_PARTY_NOTICES.md` generation/documentation.

## SDPS-1206 - Security hardening review

Run threat-model checklist for:

- malicious project source
- malicious Git repo
- command injection
- path traversal
- secrets in logs
- multi-user authorization
- WebSocket authorization
- CSRF/XSS
- Kubernetes privilege escalation
- artifact download path attacks

Fix all Critical/High findings before v1 tag.

## SDPS-1207 - Example batch project

Retail bronze/silver/gold pipeline with:

- table/file input
- filter/derive
- join
- aggregation
- materialized views
- profile/tests

Must run on open-source local Spark.

## SDPS-1208 - Example streaming Kafka project

Include local Docker Compose Kafka only as example dependency, not core requirement.

Streaming table + transform + sink/target.

## SDPS-1209 - Example CDC project

Apache Spark 4.2 Auto CDC SCD1 reference example when verified by integration test.

## SDPS-1210 - User documentation

Write:

- install
- local quick start
- visual designer
- code synchronization
- SDP concepts
- runtime profiles
- local execution
- Kubernetes
- Databricks optional integration
- Git
- collaboration
- debugging
- scheduling
- plugin development
- security/admin

## SDPS-1211 - API and plugin reference

Generate OpenAPI docs and typed plugin SDK reference.

## SDPS-1212 - Upgrade/migration docs

Explain DB migration, `.sdpstudio` schema migration, backups, rollback limitations.

## SDPS-1213 - Release qualification suite

A release candidate passes:

```text
format/lint/type/unit
web unit/build
codegen golden
round-trip suite
local Spark integration
browser E2E
security tests
Git integration
collaboration E2E
scheduler tests
Kubernetes contract/release test
Databricks mocked adapter contract
package install smoke
container smoke
license/SBOM gates
```

## SDPS-1214 - v1 definition-of-done audit

Walk every item in section 6 and attach evidence link/test for it.

No v1 tag while an item is merely documented but not implemented, unless scope is explicitly revised in the spec and release notes.

---

## 40. Detailed implementation notes for difficult areas

### 40.1 Avoiding the visual/code source-of-truth trap

The hardest product problem is not drawing nodes; it is preserving trust when both code and canvas can change.

Use these rules:

1. Every visual-owned code region has an AST fingerprint and source-map ownership record.
2. Before regeneration, parse current disk source.
3. If the owned region still matches last generated fingerprint, it is safe to replace.
4. If it changed but remains representable, reconcile into the node config and regenerate.
5. If it changed and is not representable, stop replacement and change ownership to custom code after user-visible reconciliation.
6. A file can contain both visual-owned and custom-owned regions.
7. Full code-owned files are never rewritten by graph save.

This is more important than achieving perfect reverse compilation.

### 40.2 Preview compilation model

Do not run the complete SDP pipeline to preview every intermediate visual node.

A visual pipeline may have many transformations inside one SDP dataset function. The preview compiler therefore reconstructs the DataFrame expression up to the selected node as a debug program.

Example generated preview script conceptually:

```python
def __svp_preview(spark):
    n1 = spark.table("raw.orders")
    n2 = n1.filter(...)
    n3 = n2.select(...)
    return n3.limit(PREVIEW_LIMIT)
```

Execute outside SDP dataset-definition evaluation. This permits safe actions needed to fetch preview data without placing them in production declarations.

### 40.3 Event-log to visual-node correlation

Spark stages do not naturally know SDP Studio visual node ids.

Use multiple correlation methods:

- source-map query code locations where Spark exposes them
- dataset/materialized-view names
- query plan subtree fingerprints
- debug preview id tags/local properties where safe

Do not claim exact per-node execution time for a transform if Spark fused several transforms into one stage and no exact attribution exists. Mark metrics as dataset/stage-level or estimated attribution.

### 40.4 Row Trace technical strategy

For built-in operators, compile a parallel debug lineage representation.

A trace row contains hidden debug metadata similar to:

```text
__svp_trace = {
  ids: [binary/string trace ids],
  events: bounded metadata
}
```

Implementation should prefer compact hidden columns over Python objects so Catalyst can process them.

Operator handling:

- select/derive: preserve ids
- filter: record dropped rows in a side debug query
- join: combine left/right ids
- union: preserve ids
- explode: duplicate id + child ordinal
- aggregate: aggregate bounded set/list of contributing ids; mark overflow
- custom code: attempt preservation only if output still contains instrumentation; otherwise lineage becomes unknown

Never expose hidden debug fields to production code or persisted user data.

### 40.5 Local run reproducibility

Before run:

- flush editor state
- generate code
- validate
- calculate hashes
- record Git HEAD + dirty state
- snapshot effective runtime config redacted
- create immutable run row

If working tree is dirty, save a redacted patch artifact or patch hash according to user setting. Default should store the patch locally for reproducibility unless it contains files configured as secret/sensitive.

### 40.6 Runtime adapter compatibility

All adapters must implement exactly the same semantic run requests:

```text
VALIDATE
INCREMENTAL
REFRESH_SELECTION
FULL_REFRESH_SELECTION
FULL_REFRESH_ALL
PREVIEW
```

An adapter may return `unsupported` for a semantic request. UI disables action based on capabilities.

Provider adapters must not reinterpret an unsupported operation into a materially different one without explicit user confirmation.

### 40.7 Scheduler and Git revisions

A schedule should be able to choose source policy:

- working-copy current state - local/dev only, warning
- branch head after fetch
- exact commit/tag

For team/prod schedules, default to an exact resolved Git commit per run for reproducibility.

MVP can implement `current working copy` and `branch head`; record resolved commit on every run.

---

## 41. Product acceptance scenarios

### Scenario A - Visual batch ETL from zero

1. Start local SDP Studio.
2. Create project `orders`.
3. Select local Spark 4.2 runtime.
4. Drag a Parquet/Table source.
5. Add Filter, Derive Column, Join, Aggregate.
6. Add Materialized View `daily_revenue`.
7. Open generated Python and verify understandable `pyspark.pipelines` code.
8. Validate.
9. Preview aggregate.
10. Run pipeline.
11. Inspect result and plan.
12. Commit generated source + `.sdpstudio` model.

Pass: no proprietary service used.

### Scenario B - Existing code import

1. Clone a Git repo containing `spark-pipeline.yaml`, Python, and SQL.
2. Import to SDP Studio.
3. Graph shows known SDP datasets/dependencies.
4. Unsupported complex Python appears as custom code, unchanged.
5. Add a new visual downstream materialized view.
6. Generate.

Pass: original custom source hashes remain unchanged except files explicitly edited.

### Scenario C - Debug a regression

1. Run revision A successfully.
2. Change join/filter configuration.
3. Run revision B and observe slowdown/wrong row behavior.
4. Open Run Compare A vs B.
5. See source/graph diff, plan diff, metric delta, schema/profile delta.
6. Use Row Trace on a sample record.

Pass: engineer can identify where the record was dropped/duplicated for supported operators and see evidence for performance changes.

### Scenario D - Team Git workflow

1. Two users open same project.
2. Presence appears.
3. Both edit different nodes.
4. CRDT merges changes.
5. User creates branch, commits, pushes.
6. Create GitHub PR or GitLab MR.
7. Reviewer sees visual semantic diff.

Pass: no lost edits and generic Git still works if provider plugin is disabled.

### Scenario E - Kubernetes production-like run

1. Admin configures K8s profile.
2. Probe verifies namespace/RBAC.
3. Engineer selects profile.
4. Capability check passes.
5. Run pipeline.
6. SDP Studio tracks driver/executors, streams logs, collects event data.
7. Debug overlay shows available stage metrics.

Pass: no Databricks component is involved.

### Scenario F - Optional Databricks portability

1. Pipeline built in Portable OSS mode.
2. Run locally.
3. Select Databricks profile.
4. Compatibility view shows no provider-only constructs.
5. Deploy/validate/run through adapter.
6. Later switch back to local runtime without source rewrite.

Pass: same portable transformation source remains usable.

---

## 42. API problem codes - initial registry

Use stable machine-readable codes such as:

```text
SDPS-PROJECT-001 invalid_project_schema
SDPS-PROJECT-002 unsupported_schema_version
SDPS-GRAPH-001 cycle_detected
SDPS-GRAPH-002 missing_input
SDPS-GRAPH-003 invalid_edge
SDPS-GRAPH-004 duplicate_name
SDPS-CAP-001 runtime_capability_missing
SDPS-CAP-002 provider_extension_required
SDPS-CODEGEN-001 unsupported_operator_backend
SDPS-CODEGEN-002 source_ownership_conflict
SDPS-CODEGEN-003 reconciliation_required
SDPS-IMPORT-001 dynamic_dependency_unresolved
SDPS-RUN-001 runtime_unavailable
SDPS-RUN-002 submission_failed
SDPS-RUN-003 run_lost
SDPS-PREVIEW-001 side_effect_not_allowed
SDPS-PREVIEW-002 custom_boundary_unsupported
SDPS-GIT-001 repository_locked
SDPS-GIT-002 merge_conflict
SDPS-AUTH-001 forbidden
SDPS-SECRET-001 secret_not_found
SDPS-K8S-001 insufficient_rbac
SDPS-K8S-002 artifact_staging_required
SDPS-DBX-001 provider_api_error
```

Do not expose provider credentials/raw internal exception strings by default.

---

## 43. Initial runtime capability matrix

This matrix is illustrative; actual availability is discovered/probed.

| Capability | Local Apache Spark 4.2 | Spark Connect | Kubernetes Apache Spark 4.2 | Databricks adapter |
|---|---:|---:|---:|---:|
| Python SDP | Yes | Probe | Yes | Probe |
| SQL SDP | Yes | Probe | Yes | Probe |
| Materialized views | Yes | Probe | Yes | Probe |
| Streaming tables | Yes | Probe | Yes | Probe |
| Temporary views | Yes | Probe | Yes | Probe |
| Append flows | Yes | Probe | Yes | Probe |
| Sinks | Yes on supported API | Probe | Yes on supported API | Probe |
| Selective refresh | Yes | Probe | Yes | Provider API/Probe |
| Full refresh | Yes | Probe | Yes | Provider API/Probe |
| Auto CDC SCD1 | Spark 4.2 capability | Probe | Spark 4.2 capability | Probe/provider |
| Event log deep debug | Yes | Depends on access | Yes if configured | Provider-specific |
| Provider-only features | No | No | No | Explicit only |

`Probe` is intentional: do not imply support until verified against the selected environment.

---

## 44. Data quality model

SDP Studio quality checks are separate first-class assets rather than pretending Apache Spark SDP has all provider-specific expectation semantics.

Example `.sdpstudio/tests/quality.yaml`:

```yaml
schemaVersion: 1
suites:
  - id: orders-quality
    dataset: daily_orders
    checks:
      - id: order-date-not-null
        type: not_null
        column: order_date
        severity: error
      - id: revenue-nonnegative
        type: expression
        expression: revenue >= 0
        severity: error
```

Execution modes:

- preview test
- post-run validation
- scheduled validation

Future adapters may compile compatible checks to native provider expectations, but the portable definition remains SDPS-owned and explicit.

---

## 45. Retention defaults and admin controls

Provide configurable retention for:

- run rows
- logs
- event logs
- preview caches
- data profiles
- debug bundles
- local history

Sensitive data features such as sample rows and profiles can be disabled workspace-wide.

Artifact deletion must remove metadata and file content transactionally/best-effort with retry tracking.

---

## 46. Extension roadmap after MVP

High-value post-MVP work, in rough priority order:

1. Reusable visual components/subflows published as packages.
2. OpenLineage export/import.
3. Deeper Structured Streaming state/checkpoint inspector.
4. Pyright language server integration.
5. SQL language server/catalog-aware completion.
6. Visual test-data generator and fixtures.
7. Data contracts integrated with schema registries.
8. Apache Iceberg/Delta/Hudi specialized catalog/table UX without hard dependency.
9. Fabric Spark adapter after validating SDP/runtime compatibility.
10. Azure DevOps, Bitbucket, Forgejo/Gitea review plugins.
11. Optional local/private LLM assistant plugin with no core dependency.
12. OpenAI/other model provider plugins only as optional user-configured extensions.
13. Historical cost/resource efficiency views.
14. Remote object-store artifact backend.
15. Multi-replica server with shared event bus.
16. Policy-as-code for protected production runs.
17. Snowflake source/sink or export adapter after a precise execution model is defined.

---

## 47. Things SDP Studio must never do

- Require a Databricks workspace to start.
- Generate Databricks-only syntax in Portable OSS mode.
- Hide generated pipeline code.
- Store tokens in `.sdpstudio` YAML.
- Send project metadata to a telemetry service by default.
- Execute imported Python merely to understand its graph.
- Rewrite custom code that cannot be round-tripped.
- Claim exact operator-level Spark timing when only stage-level evidence exists.
- Pretend a preview is a production run.
- Use a visual-only binary project file as the sole durable representation.
- Require Kubernetes cluster-admin.
- Require Redis for a single-user or basic team deployment.
- Make GitHub/GitLab mandatory for Git.
- Brand the public third-party software product in a way that violates Apache Spark trademark policy.

---

## 48. Research basis and reference documentation

The technical baseline should be revalidated before major releases. As of the specification date, useful primary references include:

- Apache Spark 4.2.0 release notes: `https://spark.apache.org/releases/spark-release-4-2-0.html`
- Apache Spark 4.2.0 Declarative Pipelines Programming Guide: `https://spark.apache.org/docs/4.2.0/declarative-pipelines-programming-guide.html`
- Apache Spark 4.2.0 Kubernetes guide: `https://spark.apache.org/docs/4.2.0/running-on-kubernetes.html`
- Apache Spark trademark guidance: `https://spark.apache.org/trademarks.html`
- Apache Spark powered-by/naming guidance: `https://spark.apache.org/powered-by.html`
- Databricks Lakeflow Designer overview, used only as product/UX reference: `https://docs.databricks.com/aws/en/designer/what-is-lakeflow-designer`
- Databricks Lakeflow Pipelines Editor documentation, used only as product/UX reference: `https://docs.databricks.com/aws/en/ldp/multi-file-editor`
- Databricks local SDP development documentation: `https://docs.databricks.com/aws/en/ldp/develop-locally`
- Databricks Pipelines API documentation for the optional adapter: `https://docs.databricks.com/api/workspace/pipelines/startupdate`

These references do not create a runtime dependency on Databricks.

---

## 49. Final recommended product positioning

Use wording similar to:

> **SDP Studio** is a free and open-source visual engineering environment for Apache Spark Declarative Pipelines. Design batch and streaming ETL on a professional canvas, generate readable Python or SQL, run on open-source Spark locally or on Kubernetes, collaborate through Git, and debug pipelines with graph-aware plans, metrics, run comparisons, schema history, and row tracing. Databricks is supported as an optional target, not a dependency.

The shortest strategic statement is:

> **The open visual IDE for portable Apache Spark Declarative Pipelines.**

The strongest technical differentiation should be:

> **Visual code generation without lock-in, plus engineering-grade pipeline debugging.**

---

# Appendix A - Example generated project

`transformations/orders.py`:

```python
from pyspark import pipelines as dp
from pyspark.sql import DataFrame
from pyspark.sql import functions as F


@dp.materialized_view(name="complete_orders")
def complete_orders() -> DataFrame:
    return (
        spark.table("raw.orders")
        .filter(F.col("status") == F.lit("COMPLETE"))
        .select(
            "order_id",
            "customer_id",
            F.to_date("order_ts").alias("order_date"),
            F.col("amount").cast("decimal(18,2)").alias("amount"),
        )
    )


@dp.materialized_view(name="daily_revenue")
def daily_revenue() -> DataFrame:
    return (
        spark.table("complete_orders")
        .groupBy("order_date")
        .agg(F.sum("amount").alias("revenue"))
    )
```

`spark-pipeline.yaml`:

```yaml
name: orders
libraries:
  - glob:
      include: transformations/**
storage: file:///absolute/path/set-by-environment
catalog: local
schema: analytics
configuration:
  spark.sql.shuffle.partitions: "8"
```

Environment-specific storage should be generated/resolved through deployment configuration when the durable Spark spec cannot contain a portable fixed absolute path. The project must document the chosen substitution mechanism rather than committing one developer's machine path.

---

# Appendix B - Example plugin skeleton

```python
from sdpstudio_core.operators import OperatorDefinition, PortDefinition


def get_operator() -> OperatorDefinition:
    return OperatorDefinition(
        id="acme.normalize_phone",
        version=1,
        title="Normalize Phone",
        category="Custom",
        inputs=[PortDefinition(name="in", data_kind="dataframe")],
        outputs=[PortDefinition(name="out", data_kind="dataframe")],
        modes={"batch", "streaming"},
        code_targets={"python"},
        config_schema={
            "type": "object",
            "properties": {
                "column": {"type": "string"},
            },
            "required": ["column"],
        },
        required_capabilities=set(),
        compiler="acme_svp.compiler:compile_normalize_phone",
    )
```

Plugin compiler returns IR/codegen constructs; it must not directly mutate files.

---

# Appendix C - Recommended first vertical slice

Before implementing all operators, prove the architecture end-to-end with this exact slice:

1. Local server starts.
2. Create project.
3. Canvas supports Table Source -> Filter -> Select -> Materialized View.
4. Save `.sdpstudio` YAML.
5. Generate Python SDP.
6. Show generated source in Monaco.
7. `spark-pipelines dry-run` local.
8. Preview Filter/Select.
9. Run pipeline local.
10. Stream logs.
11. Capture event log.
12. Show run history.
13. Show physical plan for preview.
14. Commit to a local Git repo.
15. Restart SDP Studio and recover all state.

Do not build collaboration, Databricks, or dozens of operators before this slice works. It is the architectural proof that the product is real rather than a collection of disconnected UI screens.

---

# Appendix D - Recommended second vertical slice

Prove the product differentiation:

1. Add Join and Aggregate.
2. Run revision A.
3. Modify join configuration and run revision B.
4. Display semantic graph diff.
5. Display source diff.
6. Capture/compare Spark plans.
7. Parse task metrics and show skew warning with evidence.
8. Show graph heatmap.
9. Implement Row Trace through source/filter/join/aggregate.
10. Export a sanitized debug bundle.

Only after this slice is trustworthy should the team expand into remote runtimes and collaboration.

---

# Appendix E - Release checklist

- [ ] Apache-2.0 headers/legal files correct.
- [ ] Public naming reviewed against Apache Spark trademark policy.
- [ ] Third-party dependency licenses inventoried.
- [ ] No critical/high known vulnerabilities without documented exception.
- [ ] All section 6 MVP criteria pass.
- [ ] `sdpstudio doctor` passes on documented local environment.
- [ ] Local quick start passes from clean environment.
- [ ] Golden code generation stable.
- [ ] No source-loss round-trip tests failing.
- [ ] Local Spark 4.2 integration green.
- [ ] Kubernetes release test green.
- [ ] Databricks optional mocked contract green.
- [ ] Browser E2E green.
- [ ] Collaboration E2E green.
- [ ] RBAC/security suite green.
- [ ] Secret redaction suite green.
- [ ] Git generic remote test green.
- [ ] GitHub/GitLab provider contract tests green.
- [ ] Scheduler recovery/concurrency tests green.
- [ ] Debug run compare/plan diff/skew tests green.
- [ ] Row Trace E2E green.
- [ ] Documentation links valid.
- [ ] Database migration from previous release tested.
- [ ] `.sdpstudio` schema migration tested.
- [ ] Container runs as non-root.
- [ ] SBOM generated.
- [ ] Checksums generated.
- [ ] Release notes include compatibility/runtime matrix.

---

# End of specification


---

## Authoritative external references

The implementation should continuously verify behavior against upstream documentation rather than hard-coding assumptions from this specification.

- Apache Spark downloads and releases: https://spark.apache.org/downloads/
- Apache Spark news/release announcements: https://spark.apache.org/news/
- Apache Spark documentation: https://spark.apache.org/docs/latest/
- Apache Spark Python API: https://spark.apache.org/docs/latest/api/python/
- Apache Spark trademark guidelines: https://spark.apache.org/trademarks.html
- Apache Spark powered-by / naming guidance: https://spark.apache.org/powered-by.html
- Apache License 2.0: https://www.apache.org/licenses/LICENSE-2.0

Reference baseline for this document: **Apache Spark 4.2.0**, released July 14, 2026. Runtime adapters MUST use capability probing/version gating because users may run later patch releases or different supported Spark streams.
