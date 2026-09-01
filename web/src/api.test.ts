import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "./api";

describe("typed API client", () => {
  afterEach(() => vi.restoreAllMocks());

  it("decodes operator responses", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify([{ id: "transform.filter", title: "Filter", category: "Transforms" }]), { status: 200 })));
    await expect(api.operators()).resolves.toEqual([{ id: "transform.filter", title: "Filter", category: "Transforms" }]);
  });

  it("propagates HTTP failures", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("", { status: 503, statusText: "Unavailable" })));
    await expect(api.projects()).rejects.toThrow("503 Unavailable");
  });

  it("exposes typed administration mutations", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ username: "analyst", role: "editor" }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ rotated: 2, key_id: "key-2" }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    await expect(api.updateUserRole("analyst", "editor")).resolves.toMatchObject({ role: "editor" });
    await expect(api.rotateSecretKey()).resolves.toMatchObject({ rotated: 2 });
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/auth/users/analyst");
    expect(fetchMock.mock.calls[1]?.[0]).toBe("/api/secrets/rotate-key");
  });

  it("accepts successful no-content deletes", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 204 })));
    await expect(api.deleteRuntimeProfile("local")).resolves.toBeUndefined();
    await expect(api.deleteSchedule("schedule-1")).resolves.toBeUndefined();
  });

  it("sends JSON headers for Git mutation requests", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify([]), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify([]), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    await api.createGitTag("project-1", "v1");
    await api.gitStashAction("project-1", "create", "checkpoint");
    expect((fetchMock.mock.calls[0]?.[1] as RequestInit).headers).toEqual(expect.any(Headers));
    expect((fetchMock.mock.calls[1]?.[1] as RequestInit).headers).toEqual(expect.any(Headers));
    expect((fetchMock.mock.calls[0]?.[1] as RequestInit).headers).toHaveProperty("get");
    expect(((fetchMock.mock.calls[0]?.[1] as RequestInit).headers as Headers).get("Content-Type")).toBe("application/json");
    expect(((fetchMock.mock.calls[1]?.[1] as RequestInit).headers as Headers).get("Content-Type")).toBe("application/json");
  });

  it("loads and mutates Git branches and history through typed contracts", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ current: "main", branches: ["main", "feature"] }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify([{ commit: "abc", author: "user", timestamp: "2026-01-01T00:00:00Z", subject: "initial" }]), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ current: "feature", branches: ["main", "feature"] }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ current: "main", branches: ["main"] }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    await expect(api.gitBranches("project-1")).resolves.toMatchObject({ current: "main" });
    await expect(api.gitLog("project-1")).resolves.toHaveLength(1);
    await expect(api.switchGitBranch("project-1", "feature")).resolves.toMatchObject({ current: "feature" });
    expect(fetchMock.mock.calls[2]?.[0]).toBe("/api/projects/project-1/git/branches/switch");
    await expect(api.deleteGitBranch("project-1", "feature")).resolves.toMatchObject({ current: "main" });
    expect(fetchMock.mock.calls[3]?.[0]).toBe("/api/projects/project-1/git/branches");
  });

  it("loads provider repository metadata", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ full_name: "acme/pipelines", html_url: "https://github.com/acme/pipelines" }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    await expect(api.gitRepository("project-1")).resolves.toMatchObject({ full_name: "acme/pipelines" });
    expect(fetchMock).toHaveBeenCalledWith("/api/projects/project-1/git/repository", expect.anything());
  });

  it("loads configured Git remotes", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ origin: "https://github.com/acme/pipelines.git" }), { status: 200 })));
    await expect(api.gitRemotes("project-1")).resolves.toEqual({ origin: "https://github.com/acme/pipelines.git" });
  });

  it("decodes catalog, file-tree, and history-diff responses", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ catalog: "local", namespace: "orders", tables: [] }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify([{ path: "data/orders.csv", kind: "file", size: 12 }]), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ diff: { added: ["node-2"] } }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    await expect(api.catalog("project-1")).resolves.toMatchObject({ namespace: "orders" });
    await expect(api.files("project-1")).resolves.toEqual([{ path: "data/orders.csv", kind: "file", size: 12 }]);
    await expect(api.historyDiff("project-1", "snapshot-1")).resolves.toEqual({ diff: { added: ["node-2"] } });
  });

  it("submits an immediate schedule run through the typed contract", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ id: "run-2", status: "queued" }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    await expect(api.runScheduleNow("project-1", "schedule-1")).resolves.toMatchObject({ id: "run-2" });
    expect(fetchMock).toHaveBeenCalledWith("/api/projects/project-1/schedules/schedule-1/run-now", expect.objectContaining({ method: "POST" }));
  });

  it("posts schema comparisons through the typed contract", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ before_fingerprint: "a", after_fingerprint: "b", diff: { added: [], removed: [], changed: [], compatible: true } }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    await expect(api.schemaDiff([{ name: "id", type: "integer" }], [{ name: "id", type: "long" }])).resolves.toMatchObject({ diff: { compatible: true } });
    expect(fetchMock).toHaveBeenCalledWith("/api/debug/schema-diff", expect.objectContaining({ method: "POST" }));
  });

  it("validates runtime capabilities for a project", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ valid: false, problems: [{ code: "SDPS-CAP-001", severity: "error", message: "missing" }] }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    await expect(api.validateCapabilities("project-1", { streaming_table: false })).resolves.toMatchObject({ valid: false });
    expect(fetchMock).toHaveBeenCalledWith("/api/projects/project-1/validate-capabilities", expect.objectContaining({ method: "POST" }));
  });

  it("loads the runtime doctor result", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ available: true, adapter: "local", spark_version: "4.1.0" }), { status: 200 })));
    await expect(api.doctor()).resolves.toMatchObject({ available: true, spark_version: "4.1.0" });
  });

  it("tests a selected runtime profile through the typed contract", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ available: true, adapter: "local" }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    await expect(api.testRuntimeProfile("local")).resolves.toMatchObject({ available: true, adapter: "local" });
    expect(fetchMock).toHaveBeenCalledWith("/api/runtime-profiles/local/test", expect.objectContaining({ method: "POST" }));
  });

  it("validates a project", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ valid: true, problems: [] }), { status: 200 })));
    await expect(api.validate("project-1")).resolves.toMatchObject({ valid: true });
  });

  it("generates project source", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ files: [{ path: "generated.py", content: "print(1)", sha256: "x" }], problems: [] }), { status: 200 })));
    await expect(api.generate("project-1")).resolves.toMatchObject({ files: [{ path: "generated.py" }] });
  });

  it("submits a project run", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ id: "run-1", status: "queued" }), { status: 200 })));
    await expect(api.run("project-1")).resolves.toMatchObject({ id: "run-1", status: "queued" });
  });

  it("loads project run history", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify([{ id: "run-1", status: "succeeded" }]), { status: 200 })));
    await expect(api.runs("project-1")).resolves.toEqual([{ id: "run-1", status: "succeeded" }]);
  });

  it("loads run details with persisted events for execution health", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ id: "run-1", status: "running", events: [{ kind: "debug", data: { stages: [{ stage_id: 1, skew_score: 5 }] } }] }), { status: 200 })));
    await expect(api.runDetail("run-1")).resolves.toMatchObject({ id: "run-1", events: [{ kind: "debug" }] });
  });

  it("requests a bounded node preview", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ schema: [], rows: [{ id: 1 }], limit: 50, node_id: "node-1" }), { status: 200 })));
    await expect(api.preview("project-1", "node-1")).resolves.toMatchObject({ limit: 50, node_id: "node-1" });
  });

  it("creates a project", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ id: "project-2", name: "orders" }), { status: 200 })));
    await expect(api.createProject("orders")).resolves.toEqual({ id: "project-2", name: "orders" });
  });

  it("profiles bounded preview rows", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ row_count: 1, columns: {} }), { status: 200 })));
    await expect(api.profile([{ id: 1 }])).resolves.toMatchObject({ row_count: 1 });
  });

  it("analyzes streaming progress diagnostics", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ query_count: 1, checkpoint_paths: [], queries: [] }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    await expect(api.streamingDiagnostics([{ Event: "query_progress" }])).resolves.toMatchObject({ query_count: 1 });
    expect(fetchMock).toHaveBeenCalledWith("/api/debug/streaming/analyze", expect.objectContaining({ method: "POST" }));
  });
});
