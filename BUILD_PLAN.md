# SDP Studio — Engineering Build Plan

**Project:** SDP Studio  
**Positioning:** Open-source visual IDE for Apache Spark Declarative Pipelines  
**License:** Apache-2.0  
**Primary runtime baseline:** Apache Spark 4.2.x  
**Document purpose:** Execution plan for maintainers and coding agents (including Codex)  
**Companion specification:** [`docs/spec/SDP_STUDIO_SPEC.md`](docs/spec/SDP_STUDIO_SPEC.md)

---

## 1. Purpose

This document is the implementation playbook for turning SDP Studio from the current productive engineering MVP into the mature v1 described by `SDP_STUDIO_SPEC.md`.

The plan is intentionally dependency-ordered. A task is complete only when its code, tests, documentation, migration impact, and acceptance criteria are complete. Do not mark UI-only mockups or provider-logo placeholders as implemented runtime integrations.

## 2. Current source baseline

The accompanying `sdp-studio-0.1.0-source.zip` is the starting baseline. It has been normalized to the SDP Studio naming scheme and already provides a dependency-light working vertical slice:

- Python 3.12+ backend and CLI.
- FastAPI REST/OpenAPI server and WebSockets.
- Versioned `.sdpstudio/` project documents.
- Deterministic `pyspark.pipelines` code generation.
- A registry-driven visual operator catalog shared by the React shell and code generators.
- Local Spark, Spark Connect, Databricks Connect interoperability, and Kubernetes runtime-profile command paths.
- Project validation and bounded node preview.
- Run persistence, event streaming, cancellation, snapshots, and debug bundles.
- Initial Debug Lab: semantic run diff, upstream row trace, source-map diagnostics, Spark event summary, skew scoring.
- Git repository workflows and GitHub/GitLab review hooks.
- Local history and optimistic collaboration conflict detection.
- Optional bearer-token protection for remotely bound servers.
- Docker/Compose and CI foundations.

The target architecture deliberately evolves the current browser UI to **React + TypeScript + XYFlow + Monaco**, introduces the canonical IR/compiler layering, SQL and import/round-trip support, production database/auth/collaboration services, deeper debugging, and release-grade runtime adapters.

## 3. Non-negotiable build rules

1. Apache Spark OSS is the reference platform. Databricks is optional and isolated.
2. The visual graph must never depend on XYFlow serialization as the domain model.
3. `.sdpstudio/` documents are versioned, human-readable project source.
4. Generated Python/SQL must be deterministic, readable, and Git-friendly.
5. Provider-specific capabilities never leak into `sdpstudio_core`.
6. Runtime execution never uses shell-string interpolation.
7. Secret values are never persisted in project YAML, source maps, logs, run snapshots, or debug bundles.
8. Every persisted-schema change ships with migration and fixture tests.
9. Every compiler change ships with golden-output tests.
10. Every new visual operator must define ports, schema/config validation, compiler behavior, runtime capability requirements, source mapping, and tests.
11. Every runtime adapter must expose capability probing instead of assuming feature parity.
12. A task is not complete while tests are red or documentation contradicts behavior.
13. No proprietary service is required for local authoring, compilation, Git use, or local Spark execution.
14. Remote team deployment fails closed unless authentication is configured.
15. Preserve backwards migration from the 0.1.0 `.sdpstudio/` format for all v1 releases.

## 4. Recommended delivery milestones

| Milestone | Outcome | Required phases |
|---|---|---|
| M0 — Baseline | Rebranded, reproducible 0.1.x source and tests | Existing baseline + Phase 0 gaps |
| M1 — Compiler Core | Stable schemas, graph, capabilities, IR, deterministic Python | Phases 1–2 core |
| M2 — Professional IDE | React/TypeScript shell, XYFlow canvas, Monaco, inspector, problems | Phases 3–5 |
| M3 — Local Productive MVP | Local Spark validate/run/preview/history works end-to-end | Phase 6 |
| M4 — Debugger Differentiation | Plan inspector/diff, metrics, skew, schemas, profiler, Row Trace | Phase 7 |
| M5 — Git-Native Team Tool | Git UX, semantic diffs, local history, authentication/RBAC/collaboration | Phases 8–9 |
| M6 — Run Anywhere | Spark Connect + production Kubernetes support | Phase 10 |
| M7 — Optional Databricks | Provider adapter without core dependency | Phase 11 |
| M8 — v1 GA | Packaging, Helm, security, docs, examples, qualification | Phase 12 |

## 5. First implementation sequence from the current repository

Before broad feature work, execute these steps in order:

1. Freeze the current 0.1.0 behavior with regression fixtures and migration tests.
2. Introduce `sdpstudio_core` domain schemas and a versioned canonical IR without changing generated output.
3. Route the existing compiler through the IR and verify byte-stable golden output.
4. Split FastAPI services from filesystem/storage implementation behind interfaces.
5. Add SQLAlchemy/Alembic and PostgreSQL compatibility while preserving SQLite local mode.
6. Bootstrap `web/` as React + TypeScript + Vite and generate a typed API client from OpenAPI.
7. Reimplement one complete vertical slice in XYFlow + Monaco: Table Source → Filter → Select → Materialized View.
8. Keep the existing lightweight SPA available only until the React slice reaches parity; then remove it rather than maintaining two products.
9. Expand the React UI operator-by-operator using the registry metadata, not hardcoded forms.
10. Only after local validate/run/preview is stable, implement the advanced debugger and remote adapters.

## 6. Definition of done for every task

A task is complete when all applicable items are true:

- Production code is implemented in the intended package boundary.
- Unit tests cover success, failure, and boundary behavior.
- Golden tests are updated only when the intended compiler contract changes.
- API changes update OpenAPI and the generated TypeScript client.
- Persisted-format changes include migrations and old-fixture loading tests.
- UI changes include keyboard/accessibility behavior where applicable.
- Security-sensitive changes include negative/adversarial tests.
- Documentation and examples are current.
- `pytest`, frontend unit tests, type checks, lint, and relevant E2E/integration tests pass.
- No secret is present in fixtures, snapshots, logs, or generated artifacts.
- Acceptance criteria in the task are demonstrated.

---

## 7. Codex implementation contract

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

## 8. Build plan overview

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


---

# Release execution gates

## Gate A — Core/Compiler

- All graph and IR schemas versioned.
- Invalid graphs fail deterministically with stable problem codes.
- Golden Python generation is byte-stable across repeated runs.
- Source maps point to the most-specific visual node.
- Import/round-trip tests preserve supported constructs and explicitly fence unsupported custom code.

## Gate B — IDE

- React application builds without proprietary/CDN runtime dependencies.
- XYFlow model is an adapter over the domain model, not the persisted source of truth.
- Monaco code navigation works both node → code and diagnostic → node.
- Undo/redo, copy/paste, selection, keyboard navigation, zoom/fit, inspector, Problems panel, and semantic diff pass Playwright tests.

## Gate C — Local Runtime

- `sdpstudio doctor` correctly reports capability availability.
- Local validate/run/cancel/preview pass against the pinned Spark integration image/runtime.
- Missing Spark/Java degrades gracefully without preventing the IDE from opening.
- Run snapshots and event summaries are reproducible and secret-safe.

## Gate D — Debugger

- Logical/physical plans can be captured and visualized.
- Plan diff correctly identifies meaningful structural changes.
- Stage/task metrics and skew rules have deterministic fixtures.
- Schema/profile/run diffs work on stored run snapshots.
- Row Trace has strict sampling/side-effect limits and clear unsupported-boundary behavior.

## Gate E — Team/Git

- Git operations cannot inject command-line options or unsafe remote helpers.
- GitHub/GitLab tokens are host-bound and never serialized into projects.
- OIDC/RBAC permission tests cover read/write/run/admin boundaries.
- Simultaneous editors do not silently overwrite graph or code changes.
- Repository mutations are coordinated and auditable.

## Gate F — Remote Runtimes

- Spark Connect preview/run capability negotiation is explicit.
- Kubernetes tests run on `kind` in CI for submit/status/cancel/log/event lifecycle.
- Artifact staging is explicit and reproducible.
- Optional Databricks package can be omitted while all OSS tests and packaging remain green.

## Gate G — v1 GA

- Clean source checkout builds all artifacts.
- Wheel/container/Helm install smoke tests pass.
- SBOM and license notices are generated.
- Security review has no unresolved critical/high findings.
- Examples cover batch, streaming, and CDC.
- Upgrade from the 0.1.x project format is tested.
- Full product acceptance scenarios from `SDP_STUDIO_SPEC.md` pass.

# Suggested Codex batching

Codex should normally work in batches of **one to three closely related SDPS tasks**. Never ask it to implement an entire phase in one prompt. A useful batch should fit one reviewable pull request and have a single architectural theme.

Recommended early batches:

```text
Batch 01: SDPS-0001 + SDPS-0002 + SDPS-0005
Batch 02: SDPS-0101 + SDPS-0102 + SDPS-0110
Batch 03: SDPS-0103 + SDPS-0104 + SDPS-0105
Batch 04: SDPS-0106 + SDPS-0107 + SDPS-0108
Batch 05: SDPS-0109 + compiler parity fixtures
Batch 06: SDPS-0201 + SDPS-0202 + SDPS-0208
Batch 07: SDPS-0203 + SDPS-0204
Batch 08: SDPS-0301 + SDPS-0304 + SDPS-0305
Batch 09: SDPS-0003 + SDPS-0310 + SDPS-0401
Batch 10: SDPS-0403 + SDPS-0404 + SDPS-0405
Batch 11: SDPS-0406 + SDPS-0407 + SDPS-0408
Batch 12: SDPS-0501 + SDPS-0502 + SDPS-0503
Batch 13: SDPS-0504 + SDPS-0505 + SDPS-0506
Batch 14: SDPS-0601 + SDPS-0602 + SDPS-0603
Batch 15: SDPS-0605 + SDPS-0606 + SDPS-0609
Batch 16: SDPS-0612 + SDPS-0613 + SDPS-0614
```

After Batch 16, schedule work by milestone and risk rather than task number alone. Advanced debugger tasks should use captured real Spark fixtures early, while Kubernetes/provider work should remain behind adapter contracts.

# Final target

SDP Studio v1 is complete when an engineer can install the product on a laptop or deploy it as a team server, visually design a portable Apache Spark Declarative Pipeline, own and review the generated code in Git, validate/preview/run it locally or on supported remote Spark runtimes, diagnose regressions with source-mapped plans/metrics/Row Trace/run diffs, and do all of that without requiring Databricks or another proprietary control plane.
