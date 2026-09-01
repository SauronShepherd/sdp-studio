export type OperatorField = { name: string; label: string; type: string; required?: boolean; default?: unknown };
export type Operator = { id: string; title: string; category: string; fields?: OperatorField[]; inputs?: string[]; outputs?: string[]; modes?: string[]; required_capabilities?: string[]; forbidden_capabilities?: string[] };
import type { Edge as OpenApiEdge, GenerationResult, Node as OpenApiNode, Problem as OpenApiProblem, ProjectResponse, RuntimeProfileResponse } from "./openapi.generated";
export type PipelineNode = Omit<OpenApiNode, "id" | "position"> & { id: string; type: string; position: { x: number; y: number }; config: Record<string, unknown> };
export type PipelineEdge = Omit<OpenApiEdge, "id" | "from" | "to"> & { id: string; from: { node: string; port: string }; to: { node: string; port: string } };
export type Pipeline = { nodes: PipelineNode[]; edges: PipelineEdge[] };
export type Project = ProjectResponse;
export type HistorySnapshot = { id: string; name?: string | null; reason?: string; created_at?: string };
export type SchemaField = { name: string; type: string; nullable?: boolean };
export type SchemaDiff = { before_fingerprint: string; after_fingerprint: string; diff: { added: string[]; removed: string[]; changed: Array<{ name: string; before: SchemaField; after: SchemaField }>; compatible: boolean } };
export type CapabilityProblem = { code: string; severity: string; message: string; node_id?: string | null; line?: number | null; doc_link?: string | null };
export type CapabilityValidation = { valid: boolean; problems: CapabilityProblem[] };
export type RuntimeCapabilities = { available: boolean; spark_version?: string | null; adapter: string; details?: Record<string, unknown> };
export type RuntimeProfile = Omit<RuntimeProfileResponse, "config"> & {
  config: Record<string, unknown>;
  available?: boolean;
};
export type ValidationResult = { valid: boolean; problems: CapabilityProblem[] };
export type RunRecord = { id: string; status: string; error?: string | null; provider?: { adapter?: string; workspace_url?: string | null; external_run_id?: string | null } };
export type RunEvent = { kind?: string; data?: Record<string, unknown>; message?: string };
export type RunDetail = RunRecord & { events: RunEvent[] };
export type AuthIdentity = { username: string; role: string };
export type Schedule = { id: string; name: string; cron: string; timezone: string; enabled: boolean; next_fire?: string | null; mode: string; runtime_profile_id?: string | null; concurrency_policy?: string; missed_run_policy?: string };
export type GitStatus = { initialized: boolean; branch: string | null; dirty: boolean; entries: string[] };
export type GitBranches = { current: string | null; branches: string[] };
export type GitCommit = { commit: string; author: string; timestamp: string; subject: string };
export type GitRemotes = Record<string, string>;
export type ProviderReview = { id?: string; title?: string; state?: string; url?: string; head?: string; base?: string };
export type ProviderRepository = { full_name?: string; name?: string; description?: string | null; html_url?: string; web_url?: string; default_branch?: string; visibility?: string };
export type ProjectCatalog = { catalog: string; namespace: string; tables: Array<{ name: string; path: string; format: string; columns?: string[] }> };
export type ProjectFile = { path: string; kind: string; size?: number; etag?: string };
export type ProjectFileContent = { path: string; content: string; etag: string; size?: number };
export type PreviewResult = { schema: unknown[]; rows: Array<Record<string, unknown>>; limit: number; node_id: string; profile?: ProfileResult; plan?: string; schema_artifact?: string; plan_artifact?: string; cache?: { hit: boolean; age_seconds: number; ttl_seconds: number } };
export type ProfileResult = { row_count: number; columns: Record<string, { count: number; null_count: number; distinct_count: number; min?: number; max?: number }> };
export type ProfileDiffResult = { status: string; before_row_count: number; after_row_count: number; added_columns: string[]; removed_columns: string[]; columns: Record<string, Record<string, unknown>> };
export type ReconcileResult = { ownership: "visual" | "custom"; changed: boolean; document: Pipeline; problems: Array<{ code: string; message: string; line?: number | null }>; regions: Array<{ start_line: number; end_line: number; ownership: string; node_id?: string | null }> };
export type RowTraceResult = { ok: boolean; trace_mode?: "sample" | "execution"; execution_backed?: boolean; input_row_count?: number; provenance?: string; [key: string]: unknown };
export type StreamingDiagnostics = { query_count: number; checkpoint_paths: string[]; queries: Array<{ query_id: string; progress: Array<Record<string, unknown>>; latest?: Record<string, unknown> | null }> };
export {
  OPENAPI_OPERATIONS,
  OPENAPI_PATHS,
} from "./openapi.generated";
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (init?.method && !["GET", "HEAD", "OPTIONS"].includes(init.method.toUpperCase()) && typeof document !== "undefined") {
    const csrf = document.cookie.split(";").map((item) => item.trim()).find((item) => item.startsWith("sdpstudio_csrf="))?.slice("sdpstudio_csrf=".length);
    if (csrf) headers.set("x-csrf-token", decodeURIComponent(csrf));
  }
  const response = await fetch(path, { ...init, headers, credentials: "same-origin" });
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  if (response.status === 204) return undefined as T;
  const body = await response.text();
  return (body ? JSON.parse(body) : undefined) as T;
}

export const api = {
  login: (username: string, password: string) => request<{ username: string; authenticated: boolean }>("/api/auth/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username, password }) }),
  updateUserRole: (username: string, role: "viewer" | "editor" | "admin") => request<{ username: string; role: string }>(`/api/auth/users/${encodeURIComponent(username)}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ role }) }),
  rotateSecretKey: () => request<{ rotated: number; key_id: string }>("/api/secrets/rotate-key", { method: "POST" }),
  me: () => request<AuthIdentity>("/api/auth/me"),
  logout: () => request<void>("/api/auth/logout", { method: "POST" }),
  operators: () => request<Operator[]>("/api/operators"),
  projects: () => request<Project[]>("/api/projects"),
  createProject: (name: string, example?: string) => request<Project>("/api/projects", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name, ...(example ? { example } : {}) }) }),
  cloneProject: (name: string, remoteUrl: string, branch?: string) => request<Project>("/api/projects/clone", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name, remote_url: remoteUrl, branch }) }),
  pipeline: (projectId: string) => request<Pipeline>(`/api/projects/${projectId}/pipeline`),
  catalog: (projectId: string) => request<ProjectCatalog>(`/api/projects/${projectId}/catalog`),
  files: (projectId: string) => request<ProjectFile[]>(`/api/projects/${projectId}/files`),
  readFile: (projectId: string, path: string) => request<ProjectFileContent>(`/api/projects/${projectId}/files/${encodeURIComponent(path)}`),
  writeFile: (projectId: string, path: string, content: string, etag?: string) => request<ProjectFile>(`/api/projects/${projectId}/files/${encodeURIComponent(path)}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ content, etag }),
  }),
  createDirectory: (projectId: string, path: string) => request<ProjectFile>(`/api/projects/${projectId}/files/directory`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ path }) }),
  renameFile: (projectId: string, oldPath: string, newPath: string, etag: string) => request<ProjectFile>(`/api/projects/${projectId}/files/rename`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ old_path: oldPath, new_path: newPath, etag }) }),
  deleteFile: (projectId: string, path: string, etag: string) => request<void>(`/api/projects/${projectId}/files/${encodeURIComponent(path)}?etag=${encodeURIComponent(etag)}`, { method: "DELETE" }),
  savePipeline: (projectId: string, pipeline: Pipeline) => request<Pipeline>(`/api/projects/${projectId}/pipeline`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(pipeline),
  }),
  schemaDiff: (before: SchemaField[], after: SchemaField[]) => request<SchemaDiff>("/api/debug/schema-diff", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ before, after }),
  }),
  validateCapabilities: (projectId: string, capabilities: Record<string, unknown>) => request<CapabilityValidation>(`/api/projects/${projectId}/validate-capabilities`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(capabilities),
  }),
  doctor: () => request<RuntimeCapabilities>("/api/doctor"),
  runtimeProfiles: () => request<RuntimeProfile[]>("/api/runtime-profiles"),
  createRuntimeProfile: (payload: { name: string; adapter: string; config?: Record<string, unknown> }) => request<RuntimeProfile>("/api/runtime-profiles", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }),
  updateRuntimeProfile: (profileId: string, payload: { config: Record<string, unknown> }) => request<RuntimeProfile>(`/api/runtime-profiles/${profileId}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }),
  deleteRuntimeProfile: (profileId: string) => request<void>(`/api/runtime-profiles/${profileId}`, { method: "DELETE" }),
  probeRuntimeProfile: (profileId: string) => request<Record<string, unknown>>(`/api/runtime-profiles/${profileId}/probe`),
  testRuntimeProfile: (profileId: string) => request<Record<string, unknown>>(`/api/runtime-profiles/${profileId}/test`, { method: "POST" }),
  validate: (projectId: string) => request<ValidationResult>(`/api/projects/${projectId}/validate`, { method: "POST" }),
  generate: (projectId: string) => request<GenerationResult>(`/api/projects/${projectId}/generate`, { method: "POST" }),
  generateSql: (projectId: string) => request<GenerationResult>(`/api/projects/${projectId}/generate-sql`, { method: "POST" }),
  reconcilePython: (projectId: string, source: string) => request<ReconcileResult>(`/api/projects/${projectId}/reconcile/python`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ path: "transformations/generated.py", source }) }),
  reconcileSql: (projectId: string, source: string) => request<ReconcileResult>(`/api/projects/${projectId}/reconcile/sql`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ path: "transformations/generated.sql", source }) }),
  run: (projectId: string, mode: "incremental" | "refresh" | "full-refresh" | "full-refresh-all" = "incremental", selected: string[] = [], runtimeProfileId?: string) => request<RunRecord>(`/api/projects/${projectId}/runs`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ mode, selected, ...(runtimeProfileId ? { runtime_profile_id: runtimeProfileId } : {}) }) }),
  cancelRun: (runId: string) => request<{ cancelled: boolean }>(`/api/runs/${runId}/cancel`, { method: "POST" }),
  runs: (projectId: string) => request<RunRecord[]>(`/api/projects/${projectId}/runs`),
  runPlan: (runId: string) => request<Record<string, unknown>>(`/api/runs/${runId}/plan`),
  runDetail: (runId: string) => request<RunDetail>(`/api/runs/${runId}`),
  kubernetesStatus: (runId: string) => request<Record<string, unknown>>(`/api/runs/${runId}/kubernetes/status`),
  kubernetesProbe: (runId: string) => request<Record<string, unknown>>(`/api/runs/${runId}/kubernetes/probe`),
  kubernetesLogs: (runId: string, tail = 200) => request<Record<string, unknown>>(`/api/runs/${runId}/kubernetes/logs?tail=${tail}`),
  kubernetesEvents: (runId: string) => request<Record<string, unknown>>(`/api/runs/${runId}/kubernetes/events`),
  schedules: (projectId: string) => request<Schedule[]>(`/api/projects/${projectId}/schedules`),
  runScheduleNow: (projectId: string, scheduleId: string) => request<RunRecord>(`/api/projects/${projectId}/schedules/${scheduleId}/run-now`, { method: "POST" }),
  gitStatus: (projectId: string) => request<GitStatus>(`/api/projects/${projectId}/git/status`),
  gitRemotes: (projectId: string) => request<GitRemotes>(`/api/projects/${projectId}/git/remotes`),
  gitFetch: (projectId: string, remote = "origin") => request<GitStatus>(`/api/projects/${projectId}/git/fetch`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ remote }) }),
  gitPull: (projectId: string, remote = "origin", branch?: string) => request<GitStatus>(`/api/projects/${projectId}/git/pull`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ remote, branch }) }),
  gitPush: (projectId: string, remote = "origin", branch?: string) => request<GitStatus>(`/api/projects/${projectId}/git/push`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ remote, branch }) }),
  gitBranches: (projectId: string) => request<GitBranches>(`/api/projects/${projectId}/git/branches`),
  gitLog: (projectId: string, limit = 20) => request<GitCommit[]>(`/api/projects/${projectId}/git/log?limit=${limit}`),
  createGitBranch: (projectId: string, name: string) => request<GitBranches>(`/api/projects/${projectId}/git/branches`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name }) }),
  switchGitBranch: (projectId: string, name: string) => request<GitBranches>(`/api/projects/${projectId}/git/branches/switch`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name }) }),
  deleteGitBranch: (projectId: string, name: string, force = false) => request<GitBranches>(`/api/projects/${projectId}/git/branches`, { method: "DELETE", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name, force }) }),
  gitTags: (projectId: string) => request<string[]>(`/api/projects/${projectId}/git/tags`),
  createGitTag: (projectId: string, name: string, message?: string) => request<string[]>(`/api/projects/${projectId}/git/tags`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name, message }) }),
  gitStash: (projectId: string) => request<string[]>(`/api/projects/${projectId}/git/stash`),
  gitStashAction: (projectId: string, action: "create" | "apply", message?: string) => request<unknown>(`/api/projects/${projectId}/git/stash`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ action, message }) }),
  gitStage: (projectId: string, paths: string[] = []) => request<GitStatus>(`/api/projects/${projectId}/git/stage`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ paths }) }),
  gitUnstage: (projectId: string, paths: string[] = []) => request<GitStatus>(`/api/projects/${projectId}/git/unstage`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ paths }) }),
  gitConflicts: (projectId: string) => request<string[]>(`/api/projects/${projectId}/git/conflicts`),
  gitConflictVersions: (projectId: string, path: string) => request<{ ours: string; theirs: string }>(`/api/projects/${projectId}/git/conflicts/${encodeURIComponent(path)}`),
  resolveGitConflict: (projectId: string, path: string, strategy: "ours" | "theirs") => request<GitStatus>(`/api/projects/${projectId}/git/conflicts/resolve`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ path, strategy }) }),
  gitReviews: (projectId: string) => request<ProviderReview[]>(`/api/projects/${projectId}/git/reviews`),
  gitRepository: (projectId: string) => request<ProviderRepository>(`/api/projects/${projectId}/git/repository`),
  createGitReview: (projectId: string, payload: { title: string; body: string; head: string; base?: string; provider?: string }) => request<ProviderReview>(`/api/projects/${projectId}/git/review`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }),
  gitDiff: (projectId: string) => request<{ diff: string }>(`/api/projects/${projectId}/git/diff`),
  gitGraphDiff: (projectId: string, left: string, right: string, path = ".sdpstudio/pipelines/main.sdpstudio.yaml") => request<{ diff: { added_nodes: unknown[]; removed_nodes: unknown[]; changed_nodes: unknown[]; added_edges: unknown[]; removed_edges: unknown[]; summary: Record<string, number> } }>(`/api/projects/${projectId}/git/graph-diff?left=${encodeURIComponent(left)}&right=${encodeURIComponent(right)}&path=${encodeURIComponent(path)}`),
  gitCommit: (projectId: string, message: string) => request<GitStatus>(`/api/projects/${projectId}/git/commit`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ message }) }),
  createSchedule: (projectId: string, payload: { name: string; cron: string; timezone?: string; mode?: string; runtime_profile_id?: string; concurrency_policy?: string; missed_run_policy?: string }) => request<Schedule>(`/api/projects/${projectId}/schedules`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }),
  toggleSchedule: (scheduleId: string, enabled: boolean) => request<Schedule>(`/api/schedules/${scheduleId}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ enabled }) }),
  deleteSchedule: (scheduleId: string) => request<void>(`/api/schedules/${scheduleId}`, { method: "DELETE" }),
  preview: (projectId: string, nodeId: string, limit = 50, options: { include_plan?: boolean; include_profile?: boolean; sampling_fraction?: number; seed?: number; timeout_seconds?: number; cache_ttl_seconds?: number; force_refresh?: boolean; confirm_sink_test?: boolean } = {}) => request<PreviewResult>(`/api/projects/${projectId}/preview`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ node_id: nodeId, limit, ...options }) }),
  profile: (rows: Array<Record<string, unknown>>) => request<ProfileResult>("/api/debug/profile", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ rows }) }),
  profileDiff: (before: ProfileResult, after: ProfileResult) => request<ProfileDiffResult>("/api/debug/profile-diff", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ before, after }) }),
  debugPlan: (projectId: string) => request<Record<string, unknown>>(`/api/projects/${projectId}/debug/plan`),
  streamingDiagnostics: (events: Array<Record<string, unknown>>) => request<StreamingDiagnostics>("/api/debug/streaming/analyze", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ events }) }),
  rowTrace: (projectId: string, nodeId: string, rows: Array<Record<string, unknown>> = []) => request<RowTraceResult>(`/api/projects/${projectId}/debug/row-trace/execute`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ node_id: nodeId, rows }) }),
  evaluateQuality: (projectId: string, nodeId: string, rows: Array<Record<string, unknown>>, limit = 200) => request<Record<string, unknown>>(`/api/projects/${projectId}/quality/evaluate`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ node_id: nodeId, rows, limit }) }),
  compareRuns: (projectId: string, leftRunId: string, rightRunId: string) => request<Record<string, unknown>>(`/api/projects/${projectId}/debug/compare-runs`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ left_run_id: leftRunId, right_run_id: rightRunId }) }),
  history: (projectId: string) => request<HistorySnapshot[]>(`/api/projects/${projectId}/history`),
  createHistoryCheckpoint: (projectId: string, name: string) => request<HistorySnapshot>(`/api/projects/${projectId}/history/checkpoints`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name }) }),
  historyDiff: (projectId: string, snapshotId: string) => request<{ diff: unknown }>(`/api/projects/${projectId}/history/${snapshotId}/diff`),
  restoreHistory: (projectId: string, snapshotId: string) => request<Pipeline>(`/api/projects/${projectId}/history/${snapshotId}/restore`, { method: "POST" }),
};
export type { GeneratedFile, GenerationResult } from "./openapi.generated";
export type Problem = OpenApiProblem;
