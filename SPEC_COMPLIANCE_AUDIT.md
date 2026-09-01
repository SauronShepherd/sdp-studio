# SDP Studio — Spec/Build-Plan Compliance Audit

**Audit date:** 2026-08-23
**Compared against:** `SDP_STUDIO_SPEC.md` (4,601 lines, also mirrored byte-identical at `docs/spec/SDP_STUDIO_SPEC.md`) and `BUILD_PLAN.md` (root of repo)
**Method:** Direct reading of the two governing documents plus 7 parallel code-reading passes over the full `python/` and `web/` trees, `tests/`, `.github/`, `deploy/`, `docs/`, `migrations/`, `scripts/`, and root legal/community files. Every finding below is backed by a file:line citation gathered by the auditing passes; nothing here is inferred from documentation claims alone — every BUILD_STATUS.md claim was independently re-verified against source.

**Legend:** 🔴 Missing · 🟡 Partial · 🟢 Present · ⚠️ Inconsistent (code contradicts spec or one doc contradicts another)

> **Re-audit addendum (2026-08-23):** This report was written before the current
> remediation pass and its historical findings must be checked against the
> worktree. The following findings are now implemented and covered by tests:
> canonical IR lowering and backend entry-point use, SQLGlot validation, source
> maps plus generated-source drift protection, ADR-001 through ADR-014, the
> expanded Alembic schema migration, run-state transitions and startup
> reconciliation, non-loopback/team authentication enforcement, runtime secret
> resolution and key rotation, Git stage/unstage/conflict/branch/tag/stash and
> provider-review endpoints, streaming diagnostics, OpenAPI client generation,
> React component tests, browser visual/E2E coverage, GitLab CI, security scans,
> and the feature-oriented frontend extraction. The original status table is
> retained as historical audit evidence; current verification is authoritative.
> Subsequent remediation also persists SQL source maps, makes skew thresholds
> runtime-configurable, and includes registered-secret redaction plus schema
> fingerprints in debug bundles. Remaining non-green boundaries are explicit:
> Databricks managed-pipeline transport is now implemented as an optional,
> credential-safe REST client but still requires a configured provider account,
> the collaboration ADR documents optimistic locking as the MVP transition
> before full offline CRDT merge semantics, and synchronous DataStore/service
> extraction remains a post-MVP architecture migration.
> Git tag creation and stash list/create/apply are also now exposed through
> role-protected REST endpoints and included in the generated OpenAPI surface.
> An `AsyncStore` boundary now moves project, pipeline, schedule, and run read
> persistence off the event loop through `asyncio.to_thread`; write-heavy and
> diagnostic routes will be migrated incrementally as the DB-backed service
> layer replaces the compatibility store.
> Runtime-profile reads, secret listing, run-event retrieval, and node-snapshot
> reads now use the same boundary as well.
> Project/profile/schedule/secret mutations and pipeline/collaboration saves now
> use the asynchronous boundary too, with audit-event ordering preserved.
> Validation, capability checks, Python/SQL generation, code reads, preview
> profile reads, dry-run generation, and run-submission generation now also
> offload blocking store/compiler work through the same boundary.
> Debug-bundle export, plan inspection, row-trace execution, and redaction
> preview now use the boundary and thread offload for CPU-heavy analysis.
> Run-event polling, history reads/restores, project collaboration replay and
> update persistence, node-snapshot writes, immediate schedule execution, and
> run comparison diagnostics now use the same asynchronous storage boundary.
> Verification after this slice: backend lint and tests pass; frontend Vitest
> (18 tests), TypeScript, production build, and Playwright E2E (6 tests) pass.
> A further route-boundary pass moved login/logout/OIDC-user persistence,
> user/audit reads and writes, run cancellation/start audit writes, readiness
> database checks, and scheduled profile reads off the event loop. The current
> remaining direct store calls are startup/lifespan operations, filesystem
> project-path resolution, and legacy Git/file/catalog handlers; these are
> blocking-I/O service extraction work rather than hidden persistence writes.
> Git subprocess-backed route operations and provider HTTP calls have now also
> been moved to `asyncio.to_thread` via the route-local Git boundary. Focused
> storage/provider integration tests and Ruff checks pass after this change.
> The previously undocumented run-artifact contract is now exposed through
> `GET /api/runs/{run_id}/artifacts` with SHA-256 metadata and a constrained
> download route; process markers are never listed or downloadable. Coverage
> includes listing, download, and traversal safety.
> The React activity rail now exposes accessible, stateful navigation for the
> spec's editor, Explorer, Operators, Catalog, Git, Runs, Debug, and Settings
> sections, with component-level assertions for every entry. Frontend unit
> tests, strict typechecking, and the production build pass.
> Kubernetes runtime observability now includes a role/access preflight at
> `GET /api/runs/{run_id}/kubernetes/probe`, using a validated argument-array
> `kubectl auth can-i get pods` command. The command contract, local-run
> fail-soft behavior, and OpenAPI regeneration are covered by tests.
> Run comparison now includes persisted node-level quality/profile diffs in
> addition to schema fingerprints and stage metric deltas; the endpoint test
> verifies row-count/profile changes across two runs.
> The Alembic chain now includes the runtime run lifecycle columns
> (`started_at`, `finished_at`, `exit_code`, `error`, and `run_type`) alongside
> the provenance fields already present in the live store. Migration tests
> assert the expanded contract on a clean SQLite upgrade.
> Runtime profile REST coverage now includes the spec-required individual GET
> operation in addition to list/create/PATCH/delete/probe/test, with an API
> regression test and regenerated OpenAPI catalog.
> Canonical pipeline resource routes are now available alongside the legacy
> project-scoped document route: collection GET/POST, resource GET/PUT,
> validation, and capability compatibility. Integration coverage verifies the
> collection/resource round trip.
> The canonical pipeline resource now also exposes the required preview
> operation, delegating to the existing safe, bounded preview implementation;
> the integration contract test verifies the route even when local Spark is
> unavailable.
> Pipeline-scoped run submission is now available at
> `POST /api/pipelines/{pipeline_id}/runs`, reusing the existing guarded run
> generation/state/audit path and covered by the canonical pipeline flow test.
> Schema evolution now has an explicit deterministic contract policy evaluator
> supporting `warn` and `block` modes plus configurable added-column handling;
> the schema-diff debug endpoint returns the policy result and unit tests cover
> both outcomes.
> Documentation structure and ADR coverage are present in the current tree;
> `BUILD_PLAN.md` now links to the actual companion spec path and no longer
> repeats the obsolete 28-operator baseline claim.
> The async persistence boundary now has a real SQLAlchemy/aiosqlite path for
> project listing and project-row reads, with engine disposal in application
> lifespan and integration coverage; other operations retain the compatibility
> fallback while migration proceeds incrementally.
> The same SQLAlchemy path now covers run retrieval/listing, run-event reads,
> and node-snapshot reads, including JSON field decoding and not-found
> behavior. AsyncStore, run-state, and comparison tests pass against the
> migrated read path.
> Audit-event and node-snapshot writes now use async SQLAlchemy transactions
> on the SQLite path, with compatibility fallback retained for other backends;
> AsyncStore integration tests cover both inserts and decoded results.
> Runtime-profile list/get/create/update/delete operations now also use the
> async SQLAlchemy path, preserving profile validation and the last-local-profile
> deletion guard. Runtime-profile and AsyncStore tests cover the migrated rules.
> Schedule list/get/create/update/delete operations now use async SQLAlchemy
> transactions and preserve cron, mode, concurrency, missed-run, and project
> validation. Atomic cross-worker schedule claiming was subsequently migrated
> through the async worker callback described below.
> Schedule claiming is now migrated: `ScheduleWorker` accepts an awaitable
> claim callback and the application uses an async SQLAlchemy conditional
> update, preserving claim-once semantics across workers. Sync claim callbacks
> remain supported for compatibility tests.
> Secret create/update and delete persistence now use async SQLAlchemy
> transactions while encryption remains inside `SecretVault`; plaintext values
> are never inserted into the database. Secret metadata and redaction tests
> pass against the migrated path.
> The async engine uses `NullPool` so short-lived app/test lifecycles close
> aiosqlite worker connections cleanly instead of leaking event-loop callbacks.
> Collaboration event append/replay, snapshot persistence, and compaction now
> use async SQLAlchemy on the SQLite path. WebSocket replay and AsyncStore
> sequence/snapshot tests pass against the migrated implementation.
> User and audit-event list/upsert reads/writes now use async SQLAlchemy as
> well, preserving password-hash storage, bounded audit ordering, and admin
> access behavior. Authentication/OIDC/audit tests pass.
> Route-level project path resolution now uses the async project-row query and
> centralized workspace-root validation before filesystem/catalog/Git access;
> remaining direct store calls are limited to startup/lifespan health and
> scheduler enumeration lifecycle work.

---

> Async collaboration persistence now preserves the synchronous store's bounded
> replay behavior: every 100th event creates a deterministic Yjs update-bundle
> snapshot and removes covered events in the same SQL transaction. A regression
> test exercises the snapshot/compaction boundary. The scheduler claim callback
> type now explicitly supports both synchronous and awaitable implementations.
> Full backend verification after this change: Ruff format/check passed and the
> complete pytest suite passed.
> The scheduler's schedule enumeration and startup run reconciliation now also
> use the async storage boundary; `ScheduleWorker` accepts an awaitable list
> callback and has regression coverage. Frontend package tests now disable file
> parallelism for deterministic Windows execution; all 18 Vitest tests pass.
> The SQLite async boundary now disposes its NullPool engine after each database
> operation as well as during application shutdown. This prevents short-lived
> TestClient instances from leaving aiosqlite worker callbacks attached to a
> closed event loop. The full backend suite passes with unhandled-thread
> warnings promoted to errors.
> The optional Databricks source synchronizer now validates the source root and
> excludes Git/SDP metadata, dependency trees, environment files, and
> secret-like filenames before upload. The mocked adapter contract verifies
> sensitive files are not sent.
> The Helm chart now includes an opt-in `networking.k8s.io/v1` Ingress template
> with configurable hosts, TLS, annotations, and service port; the default
> remains disabled and deployment tests cover the contract.
> A fresh Alembic upgrade was re-verified against the live persistence contract:
> all required entity tables and run/schedule provenance columns are present in
> the current `0002_spec_entities` revision. Migration and deployment tests,
> plus repository Ruff checks, pass.
> Run-comparison duration, stage-metric, schema, and quality-diff calculations
> now live in `sdpstudio_server.run_comparison` rather than being defined
> inline in the FastAPI handler. Direct service tests and the API comparison
> contract test pass.
> Provider review creation is now similarly delegated to the tested
> `sdpstudio_server.review_service` boundary; the FastAPI route performs role,
> remote, and async execution orchestration only.
> Debug-bundle entry assembly, schema-fingerprint generation, artifact inclusion,
> and registered-secret redaction now live in the tested
> `sdpstudio_server.debug_bundle_service` boundary; the route retains only
> persistence, path, ZIP, and HTTP orchestration.
> Project file-tree/read/write and local-catalog operations now pass through the
> `ProjectResourceService` boundary and execute off the event loop; its safe
> path, ETag, and catalog behavior has direct regression coverage.
> Optional Databricks qualification now has a manual GitHub Actions workflow
> and a credential-gated live probe test. Default CI remains credential-free;
> the live job activates only when both workspace URL and token secrets exist.
> The web test script now fixes Vitest to a single worker in addition to
> disabling file parallelism, making the frontend gate deterministic in the
> Windows desktop runner and CI.
> Collaboration now exposes a tested capabilities contract documenting durable
> Yjs update replay, offline recovery, and the current client-side CRDT boundary;
> `server_merge: false` makes the remaining full multi-device merge work explicit
> instead of overstating MVP behavior.
> AsyncStore now detects event-loop changes and avoids reusing a loop-bound
> aiosqlite engine across short-lived TestClient loops, while retaining the
> SQLAlchemy path for a stable application loop. The previously intermittent
> unhandled-thread failure now passes repeatedly with warnings promoted to errors.
> The repository now contains the prescribed `tests/fixtures`, `tests/golden`,
> `tests/integration`, `tests/adapter_contract`, and `tests/e2e` taxonomy with
> ownership and credential-safety guidance; the existing Playwright tests remain
> under `web/e2e` because they are package-local browser tests.
> The root `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, and `GOVERNANCE.md` files
> are substantive current process documents covering review gates, reporting,
> enforcement, ADR decisions, releases, and maintainer stewardship; the
> historical placeholder-depth finding is no longer current.
> React accessibility now includes a consistent high-contrast `:focus-visible`
> treatment for interactive controls and reduced-motion handling in the shell
> stylesheet; frontend tests and the production build cover the current React
> surface.
> The spec-named React feature taxonomy now exists explicitly under
> `web/src/features` for canvas, code, explorer, operators, inspector, preview,
> Git, runs, settings, and collaboration. Each boundary documents ownership;
> the staged extraction intentionally keeps shared orchestration in `main.tsx`
> until the corresponding component is moved with behavior tests.
> Release-gate verification also confirms the README quick-start sequence,
> GitHub/GitLab CI security jobs, and required documentation directories are
> present in the current tree; the corresponding historical red/yellow rows are
> retained only as provenance.
> A current-tree correction pass also confirms that the historical rows for
> ADRs, the docs subdirectories, GitLab CI, secret/dependency scanning, the
> async runtime-adapter protocol, source maps, SQLGlot, endpoint coverage,
> authentication bind enforcement, and several Git/scheduling operations are
> stale: those artifacts and implementations exist in the present worktree and
> are covered by the corresponding tests. The release SBOM workflow now installs
> the locked web dependencies before generating license metadata, and the
> GitLab package job follows the same contract. The historical table remains
> intentionally preserved as audit provenance; this addendum is authoritative
> for current status.

> Frontend lint had one current regression in `web/src/main.tsx`: undo/redo
> controls read mutable refs during render and `restoreGraph` referenced
> `saveGraph` before declaration. The implementation now exposes state-backed
> history depths and declares the save callback before its consumers. ESLint,
> TypeScript typechecking, and the production Vite build pass. Vitest was
> started in this Windows workspace but remained queued without executing a
> test file; it was stopped after bounded diagnosis and remains a verification
> follow-up rather than being reported as passing.

## Executive summary (historical baseline)

The following summary describes the state observed when this audit was first
written. It is retained as provenance, not as a statement of current status.
The current authoritative status is the re-audit addendum and prioritized
remediation list above. At the baseline revision, the repository was a genuine,
substantially-built engineering MVP with the following highest-impact gaps:

1. **The canonical IR is decorative.** Spec §4.1 makes "the IR is the source of execution semantics" a hard architecture rule. The IR module exists but code generation never calls it — Python/SQL backends compile straight from the visual graph, bypassing the IR entirely.
2. **The SQL backend doesn't use SQLGlot**, despite that being an explicit, named dependency requirement (§4.1 table, SDPS-0206). It's f-string concatenation with a regex identifier sanitizer.
3. **The React frontend is not "canonical"** as BUILD_STATUS.md claims — it's a single 373-line component with a fraction of the legacy `app.js` SPA's feature surface (no undo/redo, no history, no runtime profiles, no activity rail, no Problems-panel navigation). The build plan's own rule ("keep the SPA only until parity, then remove it") is not yet satisfied, so running both is legitimate mid-migration state, but calling the React app canonical is not accurate yet.
4. **"CRDT persistence/collaboration" is not CRDT.** It's optimistic revision locking (compare-and-swap on a revision number) plus WebSocket presence fan-out. BUILD_STATUS.md's own line 46 correctly says "optimistic collaboration revisions," but line 82 separately claims "CRDT persistence" is implemented — those two claims contradict each other, and only the first is true.
5. **No run state machine exists.** The 8-state CREATED→…→SUCCEEDED machine in spec §25 (plus `LOST` reconciliation on server restart) doesn't exist; the real code has 4 flat statuses and no startup reconciliation, so a server restart mid-run silently orphans it.
6. **The security-critical non-loopback bind guard is bypassable.** It only checks for literal `0.0.0.0`/`::`; binding to a specific LAN IP serves unauthenticated.
7. **Secret decryption is never wired into execution.** `SecretVault.decrypt()` exists and is tested in isolation but has zero production call sites — secrets are encrypted and stored but never actually resolved into a running pipeline.
8. **Zero ADRs exist**, despite both governing documents making "read the relevant spec and ADR before touching architecture" a mandatory rule for every contributor/agent — the referenced documents simply don't exist anywhere in the repo.
9. **The debugger — the spec's named "primary product differentiator" (§14)** — has real per-feature logic for most of its 13 sub-features, but none of the 13 are fully spec-complete; several have a hardcoded parameter the spec explicitly forbids hardcoding (skew ratio), and one (streaming diagnostics) is entirely unimplemented.
10. **Documentation hygiene:** `BUILD_PLAN.md`'s own section numbering jumps from `## 6` straight to `## 38` with no sections 7–37 — an artifact of copy-pasting the tail of `SDP_STUDIO_SPEC.md` without renumbering.

---

## 0. Cross-document consistency (the two spec documents themselves)

| Check | Result |
|---|---|
| `docs/spec/SDP_STUDIO_SPEC.md` vs. the master spec file | 🟢 Byte-identical (confirmed via `diff`) — not stale |
| `BUILD_PLAN.md` vs. the Phase 0–12 task list embedded in `SDP_STUDIO_SPEC.md` §38+ | 🟢 The 154 `SDPS-*` task headings are identical in both files |
| `BUILD_PLAN.md` heading numbering | 🔴 ⚠️ Jumps from `## 6. Definition of done for every task` directly to `## 38. Codex implementation contract` — sections 7–37 don't exist in this file (they exist only in the master spec). Anyone reading `BUILD_PLAN.md` standalone hits an unexplained numbering gap. Documentation-hygiene defect, not a code defect. |
| AGENTS.md / BUILD_PLAN.md §38.1 rule "read the spec and ADR before architecture changes" | 🔴 ⚠️ References a document class (ADRs) that has **zero instances** anywhere in the repo (see §7 below) |

---

## 1. Core domain model, IR, and code generation (Spec §4.1, §9, §10, §20; Phase 1–2)

| Area | Status | Evidence |
|---|---|---|
| Package layout matches spec §20 subpackage structure (`core/{domain,ir,capabilities,validation,operators,migrations}/`) | 🔴 ⚠️ | Repo uses flat single files (`sdpstudio_core/graph.py`, `ir.py`, `capabilities.py`...) with no such subpackages; `sdpstudio_codegen/source_maps/` doesn't exist at all |
| Canonical IR objects (§10.6): IRProject, IRPipeline, IRDataset, IRFlow, IRSource, IRTransform, IRSink, IRParameterRef, IRSecretRef, IRExpression | 🔴 | `ir.py` (52 lines) defines only `IRExpression`, `IRDataset`, `IRPipeline`, `IRProject`. `IRFlow`, `IRSource`, `IRTransform`, `IRSink`, `IRParameterRef`, `IRSecretRef` don't exist. `IRExpression.text` is never populated. |
| **"IR is the source of execution semantics" — hard architecture rule (§4.1)** | 🔴 ⚠️ **Violation** | `python_backend.py` and `sql_backend.py` import `GraphIndex`/`PipelineDocument` directly and compile straight from the visual graph. `pipeline_to_ir()` is called **nowhere** in `sdpstudio_codegen`. The IR-lowering pass sequence required by SDPS-0109 (resolve graph → resolve names → propagate mode → validate → build expression tree → assign dataset → normalize) doesn't exist. |
| Operator catalog (§9, ~50+ items) | 🟡 | 43 operators exist (up from the 28 baseline), but: **0 of 6** utility operators exist (no Parameter, Constant, Note, Group/subflow, reusable-component I/O, custom-code node); only 5/8 quality operators (missing row-count-range test, referential sample test, quarantine split); missing posexplode, struct/map/array builders, SQL/PySpark transform-block nodes, a standalone Append-Flow node, dedicated dedup-with-event-time; no "Custom PySpark source" operator |
| Round-trip / no-data-loss preservation (§10.3) | 🟡 | Byte-exact custom-code preservation with SHA-256 works and is tested. But the hash-guard that should block overwriting a code-owned file is defined (`source_changed()`) but **never called** by either backend before writing, and the 4-branch reconciliation report required by SDPS-0213 doesn't exist as code. |
| Source maps (§10.10) | 🔴 | `SourceRange` only has `node_id, file, start_line, end_line` — no IR object id, no columns, no content hash. No `.sdpstudio/source-maps/*.map.json` writer exists anywhere; no `source_maps` module. |
| SQL backend must use SQLGlot (§4.1 stack table, SDPS-0206) | 🔴 ⚠️ **Violation** | Zero SQLGlot usage anywhere in `python/`; it isn't even a declared dependency. `sql_backend.py` builds SQL via f-string concatenation + a regex identifier sanitizer — exactly the "templates as the semantic model" anti-pattern the spec explicitly forbids. |
| Auto CDC SCD1 signature verified against real Spark 4.2 API (SDPS-0205) | 🔴 ⚠️ | The operator exists and emits `@dp.create_auto_cdc_flow(...)`, but the environment's installed `pyspark` (4.0.1) has no `pyspark.pipelines` module at all — the signature could not have been verified as required, and reads as assumed/copied from Databricks' `dlt.apply_changes` naming. |
| Mixed-language planner (§10.9, SDPS-0207) | 🔴 | `planner.py` (18 lines) only dispatches one global language for the whole document — no per-dataset assignment, no "why this dataset switched to Python" explanation. |
| Determinism (MVP DoD §6 item 4) | 🟡 | Only one smoke test checks determinism; no `tests/golden/` fixture directory, no per-operator golden tests as SDPS-0202/0203 require. |
| Capability model (§10, SDPS-0106/0107) | 🟢 | One of the more complete areas — provider-neutral, matches spec's named capability set. |

## 2. Server, database, and REST/WebSocket API (Spec §19, §22–§25; Phase 3)

| Area | Status | Evidence |
|---|---|---|
| Business logic kept out of route handlers (SDPS-0301) | 🔴 ⚠️ | `compare_runs` (~180 lines), `debug_bundle`, and `git_review` all embed substantial logic directly in FastAPI route functions rather than delegating to a service layer. No distinct Run/Debug/Codegen service classes exist — `DataStore` in `storage.py` is a single monolith covering projects, pipelines, runs, schedules, secrets, users, and collaboration. |
| Database tables match §22 (15 entities) | 🔴 | **Entirely missing:** `workspaces`, `workspace_members`, `documents`, `repositories`, `local_revisions`, `node_snapshots`. `runs` lacks `graph_revision_hash`, `git_commit`, `git_dirty`, `dirty_patch_hash`, `source_hash`, `external_run_id`. `runtime_profiles` has no `is_protected` column (it's hardcoded logic instead). |
| Alembic migrations reflect the real schema | 🔴 ⚠️ | `migrations/versions/0001_initial.py` defines only 3 tables with minimal columns; the actual runtime schema is created by raw SQL in `DataStore._init_db`, completely disconnected from Alembic. Alembic is decorative. |
| `/api/v1` versioning (§23) | 🟡 ⚠️ | Only a path-rewrite middleware that strips the prefix — no true versioned route tree, OpenAPI doesn't reflect it. |
| REST endpoint groups (§23) | 🟡 | Present: projects/tree/files/import/generate/validate, run create/get/cancel/events/debug-bundle/compare, secrets list/create/delete (correctly no decrypt-GET). **Missing:** git stage/unstage and conflicts endpoints, schedule run-now, provider-review list, runtime-profile update/PATCH and a distinct "test" endpoint, pipeline-list CRUD (only single-document GET/PUT). |
| No endpoint ever returns a decrypted secret (§23) | 🟢 | Confirmed clean. But see next row — decrypt isn't wired up anywhere, secret or otherwise. |
| Secrets actually usable at runtime | 🔴 ⚠️ | `SecretVault.decrypt()` exists and is unit-tested, but has **zero call sites** in `sdpstudio_runners` or anywhere else in production code — secret values are encrypted and stored but never resolved into an executing pipeline. This is a functional gap, not just a security nicety. |
| WebSocket channels separated (§24) | 🟢 (naming differs) | `/ws/projects/{id}` (collab) and `/ws/runs/{id}` (run events) are genuinely separate; spec names the first `/ws/collab/{id}` — cosmetic naming mismatch only. Run-event delivery is poll-based (0.35s loop), not push-driven. |
| Run state machine (§25) | 🔴 ⚠️ | The 8-state machine plus `LOST` doesn't exist anywhere — grep for its state names returns zero hits. Actual code has 4 flat statuses (`running/succeeded/failed/cancelled`). **No startup reconciliation of non-terminal runs exists** — a server restart mid-run leaves it silently orphaned forever. |
| Async SQLAlchemy + Alembic in production path (SDPS-0302) | 🔴 ⚠️ | A clean async engine module exists in `database.py` but is dead code — only imported by its own test. Production uses synchronous `sqlite3`/hand-rolled Postgres calls directly inside async route handlers with no thread offload, blocking the event loop. |
| DB-backed worker queue, no Redis (SDPS-0608) | 🟡 | No Redis (satisfies that constraint) but also no `FOR UPDATE SKIP LOCKED` — a bespoke single-row compare-and-set claim instead. |
| Secret encryption itself (§26.4) | 🟡 | AES-256-GCM is correctly implemented with random nonces and AAD. But: key comes from one env var only (no file-based key, no OS keyring option), and there is **no key-rotation support** — only one active key can ever be used regardless of `key_id` bookkeeping. |
| OpenAPI → TypeScript client generation (SDPS-0310) | 🔴 | `web/src/api.ts` is fully hand-written; no generation script exists anywhere, no CI drift check. |
| Filesystem path-traversal defense (SDPS-0304) | 🟢 | Solid — resolves and checks containment under project root, blocks `../` and symlink escapes, atomic writes via temp+rename. |

## 3. Runtime adapters and execution (Spec §12–§13; Phase 6, 10, 11)

| Area | Status | Evidence |
|---|---|---|
| Uniform async `RuntimeAdapter` protocol (§12.1: probe/validate/preview/submit/cancel/status/stream_events/collect_artifacts) | 🔴 ⚠️ | The real protocol is a **sync** two-method `probe`/`command` dispatcher. None of the eight spec method names/types exist anywhere (`RunHandle`, `RunStatus`, `ValidationResult`, `PreviewResult` don't exist). Local/Connect/Kubernetes/Databricks are profile-string branches inside `local.py`/`profiles.py`, not classes implementing one shared interface. |
| Capability discovery reflects real environment, not assumption (§12.2) | 🟢 | Genuinely inspects `shutil.which`, `importlib.util.find_spec`, actual installed version — not hardcoded. Schema field names diverge from spec (snake_case booleans instead of the spec's named fields), a cosmetic gap. |
| Local Spark adapter safety (§12.3) | 🟡 | No `shell=True` anywhere, real argument-array subprocess exec, real incremental log capture, real graceful-then-forced cancellation. **But:** process/run state lives only in an in-memory dict — **no orphaned-process detection after server restart exists at all**, and the adapter assumes fixed CLI flags rather than detecting actual installed-runtime syntax as spec requires. |
| Spark Connect adapter (§12.4) | 🟢 | Matches spec well — secrets injected only via env/argv at execution time, never serialized, with redaction confirmed by test. |
| Kubernetes adapter (§12.5) | 🟡 | Genuinely executes via real `kubectl` calls (not just command-string building) — matches the BUILD_STATUS `kind`-cluster claim. **Gaps:** only the driver pod is tracked (no executor pods), no RBAC/connectivity pre-check beyond binary presence, no artifact-staging step, no K8s event-log collection into run history. |
| Databricks managed-pipeline mode (§12.6) | 🔴 ⚠️ | Core-isolation rule is honored (zero cross-imports confirmed). But the actual "managed pipeline deployment" logic (auth, upload/sync, create/update Lakeflow pipeline, streaming status) is **entirely unimplemented** — only a `Protocol` interface exists, and its sole implementation anywhere in the repo is a test-only `FakeClient`. This is a defined boundary with no real adapter behind it. |
| Preview safety (§13.1–13.3) | 🟡 | Minimal-subgraph compilation and no-write-to-sink behavior are real. The spec's explicit "sink-test preview with user confirmation" escape hatch doesn't exist at all (not disabled — simply absent). Secret-exclusion from preview is by convention/side-effect rather than an enforced check. |
| BUILD_STATUS.md's "fails gracefully when Spark tools absent" claim | 🟢 | Verified true — clean `RuntimeError` path via `shutil.which`, never touches a missing binary directly. |

## 4. Advanced debugger — the spec's named differentiator (Spec §14; Phase 7)

Of the 13 sub-features, **none are fully spec-complete**; most have real per-case logic but omit required fields/metrics/policies. Full detail:

| # | Feature | Status | Key gap |
|---|---|---|---|
| 14.1 | Debug session snapshot | 🟡 | `RunRecord` and the separate `run-snapshot.json` each cover part of the required field set; both omit `git_commit`, `git_dirty_patch_hash`, `generated_source_hash`, `node_execution_summary[]`, and structured `artifacts[]`. |
| 14.2 | Problems panel | 🟡 | Real unification of parser/graph/capability problems into one model, but no `line` number field, no `doc_link` field, no distinct "probable cause" field. |
| 14.3 | Spark Plan Inspector | 🔴 ⚠️ | No logical/analyzed/optimized/physical distinction — one flat text-in/node-list-out parser. **Nothing in the codebase ever calls `.explain()` or persists a plan** — the parse endpoint only re-parses text the client already supplies. Python-UDF operator names aren't even in the recognized-operator allowlist. |
| 14.4 | Plan Diff | 🟡 | Only computes added/removed operator names — no join-strategy, exchange, partitioning, or metric-change detection, no id-normalization (explicitly required by SDPS-0704). Effectively unreachable since 14.3 never persists real plans. |
| 14.5 | Run Diff / Time Travel | 🟡 | Rich in most dimensions (duration, code hash, graph diff, runtime/capability diff, problems delta, stage metrics) but `schema_diffs` is **hardcoded to `unavailable`**, and quality-change comparison doesn't exist at all. |
| 14.6 | Graph performance heatmap (backend data) | 🟡 | Metric deltas are keyed by Spark stage id, not by visual graph node id — no stage→node mapping exists, so a frontend can't actually build the required per-node overlay from this data. |
| 14.7 | Skew detector | 🟡 ⚠️ | Only median/max are computed (no p95, no per-stage byte/spill/GC/scheduler-delay metrics). The severity threshold is a **hardcoded `>=5`/`>=2` ratio** — a direct violation of SDPS-0707's explicit "never hardcode a magic ratio without config" rule. |
| 14.8 | Row Trace (flagship) | 🟡 | Real, tested per-operator trace propagation for source/filter/select/derive/union/join/aggregate (with bounded contributing-id tracking). **But `rename` and `cast` — both real operators — silently fall through unhandled**, and the spec's required "unknown across custom boundary" marking for UDF/custom-code crossings doesn't exist anywhere (there's also no custom-code/UDF operator type in the catalog at all, per §1 above). |
| 14.9 | Schema Evolution Timeline | 🟡 | The diff *algorithm* is solid and tested, but there's **no persistence of fingerprints per run** — the endpoint is stateless, and `compare_runs` explicitly disables schema comparison. No contract block/warn policy engine exists. So there is no actual timeline, only a diff function. |
| 14.10 | Data Profile Diff | 🟡 | Missing mean/stddev and top-values entirely (both required MVP metrics). No opt-in/disable control for sensitive datasets — runs unconditionally. |
| 14.11 | Failure diagnostics rule engine | 🟡 ⚠️ | The engine itself is solid (deterministic, YAML-driven, tested). But the rule pack covers only 4 of the 10 required categories, and **the on-disk `docs/diagnostics/rules.yaml` (3 rules) doesn't match the in-code default rule set (4 rules)** — the shipped file is out of sync with what the code actually claims to ship. |
| 14.12 | Debug bundle | 🟡 | Real ZIP export with SHA-256 manifest, generic redaction. Missing: no plans (14.3 gap cascades here), no schema-fingerprint file. **No pre-export redaction preview**, and redaction is never cross-checked against the actual registered-secrets store — only generic pattern matching, contradicting SDPS-0720's explicit "scan for registered secrets" requirement. |
| 14.13 | Streaming diagnostics | 🔴 | Entirely unimplemented — no checkpoint path, progress, rate, state-metric, or watermark surfacing anywhere in the runtime. |

**Verification of BUILD_STATUS.md's debugger claims:** "Static performance-risk diagnostics" ✅ true. "Upstream Row Trace" ✅ true but incomplete (see 14.8). "Spark event-log stage/task/skew analysis" ✅ true but incomplete (see 14.7). "Generated traceback line → visual node diagnostics" ✅ true and correctly tested.

## 5. Frontend (Spec §8, §19.4, §21; Phase 4–5)

| Area | Status | Evidence |
|---|---|---|
| Feature-oriented package structure (§21: `features/{canvas,code,explorer,operators,inspector,preview,git,runs,debug,settings,collaboration}/`) | 🔴 | `web/src/` has exactly 6 files total (`api.ts`, `collab.ts`, `main.tsx`, `shell.css`, 2 test files). Everything lives in one 373-line component. No `zustand`, `@tanstack/react-query`, `react-hook-form`, `zod`, or Tailwind/Radix — none declared, none imported. |
| **"React app is the canonical UI" (BUILD_STATUS.md)** | 🔴 ⚠️ **Overstated** | `web/app.js` (the "fallback" legacy SPA) is *more* feature-complete than the React app: it alone has runtime-profile management, project-clone-from-git, undo/redo, auto-layout, drag/drop placement, a Problems panel with click-to-navigate, execution-health/skew overlays, local-history diff/restore, and full Git remote/PR-review flows. The React app has none of these. Per the build plan's own rule ("keep the SPA only until parity, then remove it"), parity has not been reached — running both is legitimate mid-migration, but the "canonical" framing is not accurate today. |
| Main application layout (§8.1: app bar / activity rail / tabbed workspace / bottom panel / status bar) | 🟡 (app.js) / 🔴 (React) | `app.js`+`index.html` implement this layout closely (no persisted panel sizes though). The React app is a flat 3-column grid with none of the rail/tabs/status-bar structure. |
| Canvas behavior & overlays (§8.2–8.3) | 🟡 | Split unevenly across both apps; neither has multi-select/rubber-band, group/subflow, notes, command palette, or the toggleable metric-overlay system (execution time, skew, freshness, etc.) described in §8.3 — that overlay concept doesn't exist in either app. |
| Accessibility (§34) | 🟡 | Some ARIA labels/roles in the React app; no focus-visible styling, no theme toggle (dark-only hardcoded CSS) in either app. |
| Testing (SDPS-0003, §32.7) | 🔴 ⚠️ | No Testing Library / jsdom dependency exists at all despite being explicitly required — zero React component tests. Playwright E2E only targets the React app and is missing problem-navigation, history-restore, and run-comparison coverage. |
| Vite (not an SSR framework) | 🟢 | Compliant. |

## 6. Git, local history, collaboration, auth, and scheduling (Spec §15–§18, §26.2–26.3; Phase 8–9)

**Security-relevant flags (surfaced first):**
- 🔴 ⚠️ **The non-loopback bind guard is bypassable.** It only checks for the literal strings `0.0.0.0`/`::`; binding to a specific interface IP (e.g. `--host 10.0.0.5`) serves without requiring auth. The guard also only lives in the CLI's `serve` command, not in `create_app()` itself — any other entry point skips it entirely. This is a direct violation of MVP DoD §6 item 16 ("non-loopback deployments require authentication").
- 🔴 ⚠️ Auth is optional even when running against PostgreSQL ("team mode") — nothing ties DB backend choice to mandatory authentication; a misconfigured team deployment silently runs open.
- Otherwise, auth internals are genuinely solid: Argon2id (with legacy-hash verification only, never new-hash), signed/single-use OIDC state+nonce, real double-submit CSRF, real session revocation/expiry, and a real 5-failure/30-second rate-limit lockout — all confirmed by tests, not just comments.

| Area | Status | Evidence |
|---|---|---|
| Git MVP operations (§15.1) | 🟡 | init/clone/status/diff/commit/branch-create/fetch/pull/push all present via safe argument-array subprocess calls (confirmed injection-test-clean). **Missing:** log, branch switch/delete, tag list/create, stash operations, and any explicit conflict-detection function. |
| Git credential model (§15.2) | 🟢 | No plaintext token store; remote-URL validator blocks embedded credentials and unsafe transports. Minor deviation: provider tokens read from env vars rather than the secrets vault. |
| Visual/semantic git diff (§15.3) | 🟡 | Semantic diff of `.sdpstudio` documents genuinely exists and is used in history/run-comparison — but it only diffs already-loaded snapshots, not git blobs read without checkout as spec describes. |
| GitHub/GitLab provider plugins (§15.4–15.5) | 🟡 | Only PR/MR **create** exists; no list, no repo metadata, no link-commit-to-PR, no open-in-provider-UI. Isolation from generic Git functionality on provider failure is correctly implemented. |
| Local history (§16) | 🟡 | Real auto-snapshotting before pipeline saves and before codegen, stored outside the git-tracked tree, with working restore and diff. Retention is count-only (no age policy), every save triggers a snapshot (no debounce), no named checkpoints, no snapshot-before-conflict-resolution hook. |
| Local vs. team mode boundary (§17.1) | 🔴 ⚠️ | No explicit "mode" concept ties DB backend to auth requirement — purely env-var driven, compounding the bind-guard gap above. |
| RBAC matrix (§17.2) | 🟡 | Real per-route enforcement exists (not decorative), but the spec's finer-grained matrix collapses to just two thresholds (editor/admin) — no distinction between "run in protected environment" and ordinary edit actions, or between "manage secrets" and "manage users." |
| **Real-time collaboration is CRDT (§17.3)** | 🔴 ⚠️ **Contradicts BUILD_STATUS.md** | It's a plain WebSocket presence fan-out plus optimistic revision compare-and-swap (last-writer-wins-with-rejection) — no Yjs, no CRDT merge, no offline/reconnect merge logic anywhere in the Python backend. BUILD_STATUS.md line 46 accurately calls this "optimistic collaboration revisions," but line 82 separately and **incorrectly** claims "CRDT persistence" is implemented. These two lines of the same status document contradict each other; only the first is true. |
| Audit events (§17.4) | 🟡 | The table and service are real, but only 3 of the ~8 required event categories actually have a call site emitting them (user-created, project-created, pipeline-saved) — login/logout, role changes, secret changes, runtime-profile changes, run start/cancel, schedule changes, and git push never write an audit event despite the infrastructure existing. |
| Scheduling (§18) | 🟡 | Real cron matching, timezone handling, and claim-once locking exist. `concurrency_policy` only actually branches on `"skip"` — `"forbid"`/`"replace"` are accepted as data but not implemented, behaving as if unset. No missed-run policy logic (skip vs. run-once-on-recovery) exists at all. |

## 7. Testing, CI/CD, packaging, and documentation (Spec §30–§37, §2.3, §31; Phase 0, 12)

| Area | Status | Evidence |
|---|---|---|
| **ADRs (§37, SDPS-0005)** | 🔴 ⚠️ | **Zero ADR files exist anywhere in the repo.** ADR-001 through ADR-014 are mandated by name; both AGENTS.md and the build plan's Codex contract require reading "the spec and all ADRs" before architecture changes — a process rule pointing at nonexistent documents. |
| `docs/` structure (§31: architecture/, concepts/, guides/, reference/, adr/) | 🔴 | Only `docs/spec/` and `docs/diagnostics/` exist. No user guides, no architecture docs, no plugin/API reference docs (SDPS-1210/1211/1212 entirely unaddressed). |
| `tests/` structure (§31: fixtures/, golden/, integration/, adapter_contract/, e2e/) | 🔴 | Completely flat — 26 `test_*.py` files, no subdirectories. Equivalent coverage exists inline in places (e.g. `test_adapters.py` serves the adapter-contract role) but with no structural separation. |
| GitLab CI (§30, SDPS-0004: "GitHub Actions primary + equivalent GitLab CI sample") | 🔴 | Only `.github/workflows/ci.yml` exists; no `.gitlab-ci.yml` or `.gitlab/` anywhere — total miss. |
| CI job coverage (SDPS-0004) | 🟡 | Python/web lint-unit-build and license-scan jobs are real. **No secret-scanning job** (no gitleaks/trufflehog) and **no dependency-vulnerability scan** (no pip-audit/npm-audit/Trivy) exist anywhere in CI — both explicitly required. |
| Packaging/SBOM (§35) | 🟡 | Release-manifest checksums and the Python license scanner are real, tested, and non-trivial. **The SBOM's npm/JS component license data is a hardcoded stub** (`"UNKNOWN"` for every JS dependency) — meaning the license gate that runs against it is only as good as half-real data. No `ingress.yaml` in the Helm chart (optional per spec, but absent, not just disabled). |
| Root legal/community files (§2.3) | 🟡 | All 8 required files exist, but `CONTRIBUTING.md` (7 lines), `CODE_OF_CONDUCT.md` (4 lines), and `GOVERNANCE.md` (4 lines) are placeholder-depth with no real process/enforcement/voting content. `LICENSE`, `NOTICE`, `SECURITY.md` are substantive. |
| Trademark/naming compliance (§2.1) | 🟢 | Correct attribution language in TRADEMARKS.md/README.md; no accidental "Spark"-containing product name anywhere. |
| Quick start matches §36's exact recommended flow | 🟡 | Functionally similar but doesn't match the exact documented sequence — the README's base install path omits Spark/pipelines setup entirely, deferring it to a later section rather than the spec's `pip install pyspark[pipelines]==4.2.0 sdpstudio; sdpstudio doctor` opening. |

---

## Current prioritized remediation list

The historical table above is retained as provenance. Based on the current-tree
re-audit, the remaining work is limited to these verified boundaries:

1. The compatibility-store extraction is now at the documented MVP boundary:
   route-level filesystem/catalog, Git, persistence, authentication policy, and
   legacy fallback calls use explicit service boundaries. Remaining direct
   `DataStore` references are application-construction callbacks and the
   compatibility adapter itself; removing those would be a larger persistence
   migration, not an unbounded route-level leak.
2. The provider-backed Databricks live probe is qualified when a real
   workspace is configured; the optional REST lifecycle, safe source sync, and
   manual credential-gated workflow are implemented. Default CI still skips it
   because it does not carry provider credentials.
The live probe was subsequently qualified locally on 2026-08-23 using the
configured Databricks CLI profile `sda`; the short-lived CLI token was passed
only to the test process and was not persisted.
3. The collaboration model is explicitly documented: durable Yjs updates,
   browser offline recovery, and optimistic REST compatibility remain the
   default MVP; the optional `collaboration` extra now provides server-side
   Yrs/Yjs merging and has a cross-device-shaped Yjs fixture regression. The
   local two-browser Playwright qualification now passes; deployment-scale
   coordination remains a release-environment qualification step.
4. Continue React feature parity work before removing the legacy `app.js`
   surface. The React shell now covers the major migration workflows,
   including runtime profiles, local history, scheduling, diagnostics, Git
   history/branch operations, and provider repository/review links. Both
   surfaces remain intentionally retained because the legacy app still has
   deeper canvas/inspector and provider-management affordances; removal awaits
   an explicit parity acceptance pass rather than being inferred from route
   coverage.

Current verification baseline: the complete backend pytest suite passes with
thread warnings promoted to errors (one credential-gated Databricks-live test
skipped), and the complete frontend suite, TypeScript, ESLint, and production
build pass using the documented single-fork Vitest invocation on Windows.

### Re-audit addendum — typed client no-content response contract (2026-08-23)

The shared React API client now handles successful HTTP 204 responses without
attempting JSON decoding. This fixes deletion flows for runtime profiles and
schedules and is covered by a dedicated client regression; the frontend suite
now contains 20 passing tests.

### Re-audit addendum — Git mutation request headers (2026-08-23)

Git tag and stash mutations now send explicit JSON content headers through the
typed client, matching the FastAPI request models and preventing avoidable 422
responses. Request-shape coverage is included; the frontend suite now contains
28 passing tests.

### Re-audit addendum — final consistency gate (2026-08-23)

Current-tree consistency checks pass: OpenAPI generation is drift-free, Ruff
format/check passes across Python and scripts, no legacy project-name references
remain, the full backend suite passes with one credential-gated live test
skipped, and the frontend suite has 28 passing tests with ESLint, TypeScript,
and production build passing.

The follow-up typed-client contract scan found no additional JSON mutation
header omissions. Collaboration WebSocket size limits, invalid-message/update
problem codes, replay behavior, and capability reporting were re-confirmed in
the current implementation.

### Re-audit addendum — scheduler concurrency semantics (2026-08-23)

`ScheduleWorker.tick()` now launches dispatches without awaiting the run inline,
tracks active tasks, and applies the configured `skip`/`forbid`/`replace`
concurrency policy against genuinely in-flight work. Shutdown drains active
dispatches and consumes failures to avoid unhandled-task warnings. Regression
coverage now verifies replacement cancellation; the scheduler test module and
Ruff checks pass.

### Re-audit addendum — readiness storage boundary (2026-08-23)

The readiness database probe no longer reaches into the private synchronous
store connection from the FastAPI application. `AsyncStore.call("health_check")`
now owns the SQLAlchemy/SQLite probe and preserves a compatibility fallback for
other backends. SQLite and fallback tests cover the contract, and the focused
storage/auth test suites pass.

### Re-audit addendum — project resource path boundary (2026-08-23)

Workspace-root validation and readiness now belong to `ProjectResourceService`
alongside file and catalog operations. Application orchestration delegates
project-row path resolution to that service, and regression coverage verifies
both accepted workspace paths and rejected escape paths.

### Re-audit addendum — authentication bootstrap service boundary (2026-08-23)

The remaining application-factory authentication policy is now isolated in
`AuthBootstrapService`: persisted identities are loaded and the optional local
admin is provisioned through injected repository callbacks. This preserves the
eager startup behavior required by supported `TestClient(create_app(...))`
usage while removing bootstrap business logic from `app.py`. Dedicated
bootstrap, authentication, and storage API regressions pass.

### Re-audit addendum — React local-history parity (2026-08-23)

The React migration now consumes the existing typed history API, loads project
snapshots, creates named checkpoints, and restores selected snapshots with an
explicit confirmation prompt. This closes a concrete parity gap with the
legacy SPA while retaining the existing local undo/redo controls. TypeScript,
the production build, and all 28 frontend tests pass. On this Windows runner,
the stable invocation uses a single Vitest fork.

### Re-audit addendum — React project-clone parity (2026-08-23)

The React workspace now exposes the existing secure project-clone API through a
typed client method and a user-prompted Clone project control for repository
URL, project name, and optional branch. The shell test asserts the control is
present and enabled; the complete frontend suite remains green.

### Re-audit addendum — React Git tag/stash parity (2026-08-23)

The React Git workspace now exposes tag creation, stash creation, and latest
stash application, with refresh-driven tag/stash counts from the existing
role-protected endpoints. The shell regression asserts the controls are
available; TypeScript, ESLint, all 28 frontend tests, and the production build
pass.

### Re-audit addendum — React Git index/conflict parity (2026-08-23)

The React Git workspace now exposes stage-all and unstage-all actions plus a
conflict count/path list from the existing role-protected endpoints. The shell
regression asserts both index controls; TypeScript, ESLint, all 28 frontend
tests, and the production build pass.

### Re-audit addendum — React provider-review parity (2026-08-23)

The React Git workspace now provides opt-in listing and creation of provider
reviews through the existing isolated backend endpoints. Review loading is
explicit so projects without configured remotes continue to load normally.
The shell regression asserts both controls; TypeScript, ESLint, all 24
frontend tests, and the production build pass.

### Re-audit addendum — React runtime-profile management parity (2026-08-23)

The React workspace now supports creating and deleting runtime profiles through
the existing role-protected APIs, in addition to selecting and testing them.
Controls are guarded for missing selections and destructive actions require
confirmation. The shell regression asserts both management controls;
TypeScript, ESLint, all 28 frontend tests, and the production build pass.

### Re-audit addendum — React schedule-management parity (2026-08-23)

The React workspace now exposes immediate schedule execution and deletion for
existing schedules through the typed API, with confirmation before destructive
deletion. Schedule rows retain their existing pause/resume controls. TypeScript,
ESLint, all 28 frontend tests, and the production build pass.

### Re-audit addendum — React deterministic auto-layout parity (2026-08-23)

The React canvas now includes a deterministic grid auto-layout action. It
records the prior graph for undo, preserves edges, persists node positions, and
is disabled for an empty graph. The shell regression covers the disabled state;
TypeScript, ESLint, all 28 frontend tests, and the production build pass.

The canvas also enables XYFlow selection-on-drag and Control/Meta multi-select
keyboard behavior, with a component regression asserting the interaction
configuration.

Operator palette buttons now support native drag/drop placement onto the
canvas in addition to click-to-add. Dropped coordinates are bounded to the
canvas and use the existing deterministic save/history path; the shell test
asserts operators are draggable.

The React local-history panel now also loads and renders deterministic snapshot
diffs through the existing history API, alongside checkpoint creation and
restore. TypeScript, ESLint, all 28 frontend tests, and the production build
pass.

The React workspace now also exposes the project catalog as an opt-in panel,
listing discovered local tables and formats through the existing catalog API;
catalog failures do not block project loading. The shell regression asserts the
Load catalog control.

The React workspace now exposes the safe project-file tree through an opt-in
Explorer panel backed by the existing validated filesystem endpoint. File-tree
loading is isolated from initial project loading, and the shell regression
asserts the control. Typed-client contract tests cover catalog, file-tree, and
history-diff response decoding; the frontend suite now contains 28 passing
tests.

ActivityRail selectors now target the actual Explorer and Catalog panels rather
than the project selector/runtime panel. A focused rail test verifies both
navigation callbacks and scroll targets.

### Re-audit addendum — collaboration CRDT merge coverage (2026-08-23)

The browser collaboration document now stores pipeline nodes and edges as independent Yjs map entries instead of one JSON blob. This preserves backward-compatible reads for the legacy `pipeline` key while allowing concurrent clients to merge independent node/edge edits. `web/src/collab.test.ts` includes a regression test applying independent client updates and asserting both nodes survive. Frontend tests (24 passed), ESLint, TypeScript, and production build pass after this change.

### Re-audit addendum — typed schedule execution contract (2026-08-23)

The typed React API now has a regression covering immediate schedule execution,
including its POST route and response decoding. The complete frontend gate is
green: 28 Vitest tests, ESLint, TypeScript, and the production build. Vite still
reports the existing advisory that the main bundle is just over 500 kB; this is
not a build failure and remains a follow-up optimization item.

### Re-audit addendum — React execution-health parity (2026-08-23)

The React shell now loads persisted run details and surfaces execution-health
status from Spark stage diagnostics, including stage count and severe-skew count;
runs without event-log stage data receive an explicit availability message. The
typed `runDetail` contract has regression coverage. The frontend gate passes
 with 28 Vitest tests, ESLint, TypeScript, and the production build.

### Re-audit addendum — runtime-profile validation boundary (2026-08-23)

Runtime-profile validation now lives in the dedicated
`runtime_profile_service` module and is shared by both synchronous compatibility
and asynchronous SQLAlchemy persistence paths. `AsyncStore` no longer reaches
into `DataStore`'s private validator; the compatibility method remains only as
a thin shim for older callers. A regression makes the SQLAlchemy path fail if
that private method is invoked, proving the boundary is enforced. Focused
async-store tests and Ruff checks pass.

The remaining compatibility fallback is now isolated behind an explicit
`CompatibilityStoreBoundary`; `AsyncStore` no longer dispatches directly to
legacy store methods. Its off-event-loop delegation has dedicated regression
coverage, further narrowing the application’s direct persistence coupling.

The boundary is also exercised through the SQL-backed runtime-profile path and
the targeted authentication/storage regression set; no legacy project-name
references or diff-whitespace errors remain.

### Re-audit addendum — audit-event coverage recheck (2026-08-23)

The historical audit-event gap is no longer current: the application emits
events for authentication, user changes, projects and pipelines, runtime-profile
changes, secret changes, schedule changes, run start/cancel, history changes,
and Git mutations through the asynchronous persistence boundary. A direct
current-tree call-site scan and the complete backend suite were re-run; the
credential-gated Databricks live test remains the only expected skip.

### Re-audit addendum — diagnostics rule-pack consistency (2026-08-23)

The previously reported mismatch between the shipped YAML diagnostics pack and
the code defaults is resolved in the current tree: the shipped rule IDs match
`load_rules()` exactly, and `tests/test_diagnostics.py` enforces that invariant.

### Re-audit addendum — Row Trace custom-boundary semantics (2026-08-23)

Bounded Row Trace now marks unsupported/custom-code boundaries as
`trace_status: "unknown"` and propagates that status to downstream steps while
preserving bounded rows for continuity. A focused regression covers the custom
code boundary; the debugger suite (17 tests) and Ruff checks pass. Existing
rename and cast semantics remain covered by the adjacent regression.

### Re-audit addendum — persisted schema timeline (2026-08-23)

Persisted node snapshots can now be queried through
`GET /api/projects/{project_id}/debug/schema-timeline`. The deterministic
service orders runs and nodes, emits schema fingerprints, and computes the
first-versus-subsequent schema diff for each node. Service and API regressions
cover a type change across two runs; targeted storage/run-comparison tests and
Ruff checks pass.

### Re-audit addendum — preview secret-reference safety (2026-08-23)

Preview generation now resolves `secret://NAME` file paths through
`os.environ["NAME"]` rather than embedding the reference in generated source;
the behavior is covered by a dedicated preview regression. The preview suite
passes 5/5 tests with Ruff and formatting checks green. The existing preview
compiler remains side-effect-free and does not execute sink writes.

### Re-audit addendum — versioned API contract (2026-08-23)

The historical `/api/v1` concern is resolved in the current tree: the request
path adapter supports versioned calls, OpenAPI publishes aliases for every
`/api` route, and integration coverage exercises a versioned project/catalog
request. The OpenAPI versioning regression passes.

### Re-audit addendum — React command-palette parity (2026-08-23)

The React ActivityRail now exposes an accessible command palette through a
button and Ctrl/Cmd+K, with Escape dismissal and direct navigation to each
workspace section. Component coverage verifies both entry paths. The frontend
gate passes with 28 Vitest tests, ESLint, TypeScript, and the production build;
the existing Vite bundle-size advisory remains non-blocking.

### Re-audit addendum — unresolved-marker sweep (2026-08-23)

A current-tree sweep found no unimplemented application TODO/FIXME markers or
placeholder backend paths. Historical “missing”/“unimplemented” rows in this
report are retained as provenance and are superseded by the implementation and
test addenda above. The intentionally open boundaries are final
compatibility-store migration, live Databricks qualification, live browser
multi-device collaboration qualification, and completion of the React/legacy-
SPA parity migration.

### Re-audit addendum — Alembic/runtime schema parity (2026-08-23)

The historical claim that Alembic is purely decorative is superseded: the
current chain includes the runtime persistence entities and specification
columns. A remaining type mismatch for `local_revisions.content_blob` was
corrected to match the runtime bootstrap schema, and migration tests now assert
the collaboration tables, revision columns, and representative schedule/run
columns. The migration regression passes.

The stronger parity regression also passes: it bootstraps the runtime SQLite
schema, upgrades a separate Alembic database to `head`, and asserts that every
runtime table and column is represented by the migration chain. The complete
backend suite passes with thread warnings promoted to errors; the configured
Databricks live test remains the only expected skip.

### Re-audit addendum — React graph copy/paste parity (2026-08-23)

The React canvas now supports Ctrl/Cmd+C on the selected node and Ctrl/Cmd+V
with deterministic collision-safe IDs, a 32px offset, selection, history, and
the existing persistence path. The clone helper has focused coverage; the
frontend suite passes 28 tests with ESLint, TypeScript, and the production build.

### Re-audit addendum — age-aware local-history retention (2026-08-23)

Local-history cleanup now applies both the configured maximum snapshot count and
`SDPSTUDIO_HISTORY_MAX_AGE_DAYS`, defaulting to a one-year age window while
preserving the existing count limit. A regression ages a snapshot and verifies
that the next checkpoint removes it; the focused history tests and Ruff checks
pass.

### Re-audit addendum — full current-tree verification (2026-08-23)

The complete backend pytest gate completed with thread warnings promoted to
errors; the credential-gated Databricks live test is the only expected skip.
The complete frontend gate passes 28 tests, and Ruff, ESLint, TypeScript,
production build, and diff-whitespace checks pass. The production build retains
the documented non-blocking Vite bundle-size advisory.

### Re-audit addendum — historical finding reconciliation (2026-08-23)

The historical compliance table was cross-checked against the current source
tree and focused regression suites. The following previously red findings are
implemented in the current tree and are therefore retained above as historical
provenance rather than active defects:

- Both Python and SQL generators call `lower_pipeline()` and generate from the
  normalized IR document; the SQL backend validates generated expressions with
  SQLGlot.
- `SourceRange` includes object identity and content hashes, and generation
  persists deterministic `.sdpstudio/source-maps/*.map.json` files.
- `RunRecord` contains the specified persisted states, transition validation is
  enforced, and startup reconciliation marks unrecoverable non-terminal runs as
  `lost` with a stable event code.
- Secret references are resolved only at the local execution boundary and are
  injected into the child process environment; encrypted values remain out of
  generated source and API responses.
- Bind security uses IP parsing and applies the authentication requirement in
  `create_app()` for every non-loopback entry point, with an explicit opt-in
  development override.
- The runtime adapter protocol exposes the asynchronous probe/validate/preview/
  submit/cancel/status/stream-events/artifact contract, with local adapter
  coverage and provider-specific lifecycle adapters behind it.
- React now has tested feature boundaries for activity, canvas, debug,
  collaboration, runtime, Git, runs/history, and generated API access; the
  frontend suite currently passes 28 tests.

Focused verification for this reconciliation passed:
`tests/test_ir.py`, `tests/test_architecture_contracts.py`,
`tests/test_run_state.py`, `tests/test_bind_security.py`,
`tests/test_secrets.py`, `tests/test_adapters.py`, and
`tests/test_storage_api.py`.

At that point the active boundaries were compatibility-store migration, live
Databricks qualification, full server-side multi-device collaboration merge
certification, and final React/legacy-SPA parity before deleting the legacy
surface. Later addenda document the optional server-side Yrs/Yjs merge and the
remaining live browser qualification; the compatibility and React boundaries
remain intentionally staged.

### Re-audit addendum — frontend gate hygiene (2026-08-23)

The configured frontend unit gate (`pnpm test`) passes 28 tests across 7 test
files. ESLint, TypeScript, and the production build also pass. A duplicate
Playwright screenshot option found during an intentionally broad test command
was removed; the documented Vitest script already excludes Playwright E2E
specifications, and the existing non-blocking bundle-size advisory remains.

### Re-audit addendum — strict collaboration update validation (2026-08-23)

The collaboration WebSocket now strictly validates URL-safe base64 Yjs update
payloads before they are persisted or broadcast. Invalid alphabet/padding and
empty payloads are rejected with the stable `COLLAB_INVALID_UPDATE` code, while
valid updates retain the existing one-megabyte bound and durable replay path.
A websocket regression covers rejection of non-canonical payloads. The
server-side Yjs merge boundary remains explicit because no Python Yjs runtime is
installed; CRDT merge continues to occur in browser clients using the declared
Yjs dependency.

### Re-audit addendum — documentation and ADR contract (2026-08-23)

The historical ADR finding is superseded by the current tree: ADR-001 through
ADR-014 are present under `docs/adr`, and the required architecture, concepts,
guides, reference, and ADR sections contain Markdown documentation. A new
repository contract test verifies the complete numbered ADR set, filename
convention, and section presence so the documentation framework cannot regress.

### Re-audit addendum — compatibility boundary scope (2026-08-23)

The current-tree inventory confirms that route handlers do not call
`DataStore` directly: they use `AsyncStore`, `ProjectResourceService`, the Git
service, and authentication policy services. The remaining synchronous store
references are limited to application construction/lifecycle wiring and the
`LocalRuntime` transaction integration. Completing that last migration requires
reworking the runtime's synchronous run/event transaction contract; the
existing `CompatibilityStoreBoundary` keeps those calls off the event loop and
is the documented MVP boundary. No route-level persistence leak was found.

### Re-audit addendum — SBOM npm license resolution (2026-08-23)

The SBOM generator now parses the pnpm lockfile structurally with YAML rather
than relying on indentation-sensitive regexes, handles quoted/scoped package
keys, and searches both the workspace pnpm store and the web-local store for
installed package manifests. Regression coverage verifies scoped-package
license resolution. This supersedes the historical claim that JavaScript
license metadata was hardcoded as `UNKNOWN`; optional platform packages not
installed on the current operating system remain explicitly unresolved until
their platform-specific manifest is available in the release environment.

The Python SBOM path now likewise prefers SPDX `License-Expression`, then
legacy license metadata and license classifiers, rather than treating a
missing legacy `License` field as the only source of truth. Release-gate tests
cover SPDX resolution. In the current Windows environment this reduces
unresolved Python entries to packages whose installed metadata exposes no
license field; the remaining npm entries are optional platform packages not
installed for this host.

### Re-audit addendum — SQL generated-source drift protection (2026-08-23)

SQL generation now applies the same source-map hash guard already used by
Python generation. If `transformations/generated.sql` changes outside SDP
Studio, regeneration refuses to overwrite it and returns the stable
`SDPS-CODEGEN-DRIFT` problem. Malformed ownership metadata similarly fails
closed with `SDPS-CODEGEN-MAP`. A storage regression verifies both refusal and
preservation of the external edit.

### Re-audit addendum — deterministic mixed-language planning (2026-08-23)

The codegen planner now exposes a deterministic per-dataset language plan. In
`auto` mode it assigns SQL-compatible output subgraphs to SQL and explains
fallbacks to Python for unsupported operators such as custom code; explicit
Python/SQL preferences retain their existing all-target behavior. Regression
coverage verifies stable assignment ordering and fallback reasons. The planner
does not silently merge independently generated files into one runtime artifact;
that remains an intentional follow-up for full mixed-language deployment.

### Re-audit addendum — skew evidence metrics (2026-08-23)

Spark event-log summarization now includes configurable-threshold skew scoring,
p95 task duration, and per-stage memory spill, disk spill, executor CPU, and
scheduler-delay totals when those Spark task metrics are present. A debugger
regression verifies the evidence fields alongside the existing skew diagnosis;
missing metrics remain deterministic zero values.

### Re-audit addendum — sensitive data profile opt-out (2026-08-23)

The profile core function and `/api/debug/profile` contract now accept
`include_sensitive_metrics`. When disabled, structural counts remain available
but numeric distribution metrics and categorical top-values are omitted. The
default remains backward-compatible, and both core and API regressions cover
the opt-out behavior.

### Re-audit addendum — structured RBAC denial problems (2026-08-23)

Role authorization failures now return a stable `SDPS-AUTH-ROLE_REQUIRED`
problem code with the required role and human-readable message, including the
protected-runtime run path. Existing 403 behavior is preserved and the RBAC
regression verifies the structured response.

### Re-audit addendum — full backend regression after current remediation (2026-08-23)

The complete backend gate was rerun with
`PytestUnhandledThreadExceptionWarning` promoted to errors after the latest
profiling, skew, planner, SBOM, SQL drift, and RBAC changes. It completed
successfully; the credential-gated Databricks live test remains the only
expected skip.

### Re-audit addendum — scheduler missed-run policy (2026-08-23)

The historical scheduler gap is resolved in the current implementation:
startup evaluates `missed_run_policy: "run_once"` against the last claim marker,
while the default `skip` policy does not backfill. Existing scheduler
regressions cover one-time recovery, timezone-safe next-fire calculation, and
the concurrency policies; the scheduler suite and Ruff checks pass.

### Re-audit addendum — optional server-side Yjs merge (2026-08-23)

The collaboration boundary now has an optional server-side merge implementation
using the maintained `pycrdt` Yrs binding. It is isolated behind the
`collaboration` extra, so the default product remains runnable without the
optional native dependency. When installed, the capabilities endpoint reports
`server_merge: true`, incoming updates are merged before durable persistence,
and the merge path has an independent-update regression test. The default
client-side replay path remains covered when the extra is absent. The remaining
qualification boundary is cross-device certification against the browser's
exact Yjs document shape in a live multi-device session.

The server merge regression now applies two real Yjs 13.x update fixtures
matching the browser document's `sdpstudio` root map and verifies both
independent node entries survive the Python merge. The backend and frontend
unit gates pass after this qualification fixture was added; only an actual
browser-to-server multi-device session remains environment-dependent.

The collaboration evidence is now end-to-end at the server boundary: an
integration regression sends two browser-shaped Yjs 13.x updates through the
project WebSocket, verifies both are durably persisted, and reconstructs both
nodes from the stored merged updates. The local browser-to-server multi-device
path is now covered by the Playwright suite below; deployment-scale
coordination remains a release-environment concern.

The aggregate release gate was rechecked after the collaboration changes:
Python formatting, Ruff lint, bytecode compilation, OpenAPI client freshness,
and the backend/frontend test gates are clean. The CI workflow also contains
the required gitleaks, pip-audit, and production pnpm audit jobs; the earlier
historical security-row wording is therefore superseded by the current
workflow.

### Re-audit addendum — Databricks CLI profile qualification (2026-08-23)

The credential-gated live Databricks probe passed locally using the configured
CLI profile `sda`. Its short-lived access token was injected only into the
pytest process and was not persisted. The remaining CI limitation is the
absence of provider credentials in the default workflow.

### Re-audit addendum — REST endpoint contract reconciliation (2026-08-23)

The historical missing-endpoint row is superseded by the current OpenAPI route
set: pipeline listing/CRUD, runtime-profile patch/test, schedule run-now, Git
stage/unstage/conflicts/tags/stash/branch operations, provider review listing
and repository metadata, streaming diagnostics, and redaction preview are all
registered. A release-gate regression now asserts the required endpoint group
paths directly from the generated OpenAPI schema.

The complete backend regression was rerun after the WebSocket collaboration
integration test was added and passed with thread warnings promoted to errors;
the credential-gated Databricks live test remains the only expected skip.

### Re-audit addendum — live browser qualification (2026-08-23)

The full Playwright Chromium E2E suite passed locally: all six tests covering
the core workflow, two-browser collaboration presence, activity/theme/editor
status, desktop and mobile visual regression, and generated SQL/profile/run/Git
controls. The workflow assertion was tightened to target the exact top-level
Git region, and the desktop/mobile baselines were regenerated from the current
React UI.

### Re-audit addendum — React Git history and branch parity (2026-08-23)

The React Git workspace now consumes the existing typed branch and history
contracts: users can inspect commit history, create branches, and switch
branches without falling back to the legacy SPA. The new client contract is
covered by 20 passing API tests. Git history and branch reads are intentionally
lazy behind the existing refresh action so project selection remains within
the browser workflow timeout. TypeScript, production build, and the complete
six-test Playwright suite pass after the change.
Branch deletion is also exposed with confirmation and a disabled-main-branch
guard; the server-side role and current-branch protections remain authoritative.

The React provider-review panel now also loads repository metadata and renders
safe links to the provider repository and individual reviews. The typed client
contract is covered by 21 passing API tests; TypeScript, production build,
visual regression, and the complete six-test Playwright suite pass.

Configured Git remotes are now visible in the same React panel. The app no
longer implicitly selects an arbitrary persisted project on startup; project
selection is explicit, while the two-browser collaboration test explicitly
selects the shared project. Visual assertions mask only dynamic project/status
regions, and the full Playwright suite passes deterministically 6/6.

`BUILD_STATUS.md` was reconciled with this evidence: local two-browser
collaboration is qualified, while distributed deployment coordination and
full offline-merge acceptance remain explicitly release-environment work.
The focused backend consistency gate (release routes, Git/provider contracts,
and versioned OpenAPI paths) passes with thread warnings promoted to errors.
The production React build also passes; its only output is the existing
non-blocking Vite bundle-size advisory.

The complete frontend Vitest gate now passes 31 tests across seven files,
including the React shell, activity/status/debug components, typed API,
collaboration, and canvas clipboard behavior.

### Re-audit addendum — React execution-health parity (2026-08-23)

The React inspector now renders bounded stage-level execution-health evidence
from persisted run events: skew severity, task count, maximum task duration,
and shuffle read/write totals for up to 20 stages. The dedicated component
regression covers high-skew rendering; the complete frontend gate now passes
32 tests across eight files, with TypeScript and the production build green.
The collaboration browser assertion now waits for the first client’s WebSocket
presence before opening the second client, eliminating order-dependent timing
flakes; the complete Playwright suite passes 6/6 after this change.

Execution-health metrics are now user-toggleable through an accessible
Show/Hide metrics control, with the expanded and collapsed states covered by
the component regression.

The complete backend regression was rerun against the current tree with
`PytestUnhandledThreadExceptionWarning` promoted to errors; it passed at 100%
with only the expected credential-gated Databricks test skipped.

A final repository-wide case-insensitive sweep found no remaining legacy-name
references; current product, package, deployment, and README identity
consistently use SDP Studio / `sdp-studio`.

### React parity acceptance matrix (current tree)

| Capability | React evidence | Status |
|---|---|---|
| Pipeline canvas, drag/drop, multi-select, undo/redo, auto-layout | `main.tsx`, XYFlow shell tests, Playwright smoke/workflow | Verified |
| Runtime profiles, validation, generation, preview, row trace | React controls plus API/component/E2E coverage | Verified |
| Runs, scheduling, history diff/restore, run comparison | React controls plus backend/API/E2E coverage | Verified |
| Git status/diff/commit/stage/stash/tags/branches/history/remotes | Typed client, Git panel, API tests, workflow E2E | Verified |
| Provider repository/review operations | Typed client, provider-review panel, backend contract tests | Verified |
| Collaboration presence/offline replay and local two-browser flow | Yjs tests, WebSocket integration, Playwright two-browser test | Verified locally |
| Stage-level execution-health/skew evidence | `ExecutionHealthPanel` component and regression test | Verified |
| Legacy-only deep canvas/inspector affordances and final SPA removal | ADR-005 requires formal parity acceptance before deletion | Open migration boundary |
