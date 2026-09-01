import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@monaco-editor/react", () => ({ default: () => <div data-testid="monaco" /> }));
vi.mock("@xyflow/react", () => ({
  addEdge: (connection: unknown, edges: unknown[]) => [...edges, connection],
  Background: () => null,
  Controls: () => null,
  MiniMap: () => null,
  ReactFlow: ({ children, selectionOnDrag, multiSelectionKeyCode }: { children: ReactNode; selectionOnDrag?: boolean; multiSelectionKeyCode?: string[] }) => <div data-selection-on-drag={selectionOnDrag ? "true" : "false"} data-multi-key={multiSelectionKeyCode?.join(",")}>{children}</div>,
  ReactFlowProvider: ({ children }: { children: ReactNode }) => <>{children}</>,
  useEdgesState: (initial: unknown[]) => [initial, vi.fn(), vi.fn()],
  useNodesState: (initial: unknown[]) => [initial, vi.fn(), vi.fn()],
}));

import { App, isTerminalRunStatus } from "./main";

const response = (value: unknown) => new Response(JSON.stringify(value), { status: 200 });

describe("React shell", () => {
  afterEach(() => vi.restoreAllMocks());

  it("treats validation failures as terminal run states", () => {
    expect(isTerminalRunStatus("validation_failed")).toBe(true);
    expect(isTerminalRunStatus("running")).toBe(false);
  });

  it("renders accessible navigation and runtime profile controls", async () => {
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const path = String(input);
      if (path === "/api/operators") return Promise.resolve(response([{ id: "transform.filter", title: "Filter", category: "Transforms" }]));
      if (path === "/api/projects") return Promise.resolve(response([{ id: "p1", name: "Orders" }]));
      if (path === "/api/doctor") return Promise.resolve(response({ available: true, adapter: "local" }));
      if (path === "/api/runtime-profiles") return Promise.resolve(response([{ id: "local", name: "Local", adapter: "local", config: {} }]));
      if (path.includes("/pipeline")) return Promise.resolve(response({ nodes: [], edges: [] }));
      if (path.includes("/runs")) return Promise.resolve(response([]));
      if (path.includes("/schedules")) return Promise.resolve(response([]));
      if (path.includes("/git/status")) return Promise.resolve(response({ initialized: false, branch: null, dirty: false, entries: [] }));
      if (path.includes("/history")) return Promise.resolve(response([]));
      return Promise.resolve(response({}));
    }));
    vi.stubGlobal("WebSocket", class { close() {} addEventListener() {} });

    const rendered = render(<App />);
    await waitFor(() => expect(screen.getByRole("combobox", { name: "Runtime profile" })).toBeInTheDocument());
    expect(screen.getByRole("navigation", { name: "Workspace sections" })).toBeInTheDocument();
    for (const label of ["Pipeline editor", "Explorer", "Operators", "Catalog", "Git changes", "Runs and history", "Debug tools", "Settings"]) {
      expect(screen.getByRole("button", { name: label })).toBeInTheDocument();
    }
    expect(screen.getByRole("contentinfo", { name: "Editor status" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Local · local" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Test profile" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Create runtime profile" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Delete selected profile" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Auto-layout" })).toBeDisabled();
    expect(screen.getByRole("heading", { name: "Local history" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Filter/ })).toHaveAttribute("draggable", "true");
    expect(screen.getByRole("textbox", { name: "Search operators" })).toBeInTheDocument();
    fireEvent.change(screen.getByRole("textbox", { name: "Search operators" }), { target: { value: "filter" } });
    expect(screen.getByRole("button", { name: /Filter/ })).toBeInTheDocument();
    expect(document.querySelector("[data-selection-on-drag='true']")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Clone project" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Create tag" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Stash changes" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Stage all" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Unstage all" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Load reviews" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Create review" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Load catalog" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Load project files" })).toBeEnabled();
    screen.getByRole("button", { name: "Test profile" }).click();
    await waitFor(() => expect(screen.getAllByRole("status").some((element) => element.textContent?.includes("Unavailable"))).toBe(true));
    expect(screen.getByRole("button", { name: "Switch to light theme" })).toBeInTheDocument();
    rendered.unmount();
  }, 15000);

  it("inspects the latest captured run plan before static advisories", async () => {
    const calls: string[] = [];
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const path = String(input);
      calls.push(path);
      if (path === "/api/operators") return Promise.resolve(response([]));
      if (path === "/api/projects") return Promise.resolve(response([{ id: "p1", name: "Orders" }]));
      if (path === "/api/doctor") return Promise.resolve(response({ available: true, adapter: "local" }));
      if (path === "/api/runtime-profiles") return Promise.resolve(response([]));
      if (path.endsWith("/pipeline")) return Promise.resolve(response({ nodes: [], edges: [] }));
      if (path.endsWith("/runs")) return Promise.resolve(response([{ id: "r1", status: "succeeded" }]));
      if (path === "/api/runs/r1/plan") return Promise.resolve(response({ plan_kinds: ["logical", "physical"] }));
      if (path.includes("/schedules")) return Promise.resolve(response([]));
      if (path.includes("/git/status")) return Promise.resolve(response({ initialized: false, branch: null, dirty: false, entries: [] }));
      if (path.includes("/history")) return Promise.resolve(response([]));
      return Promise.resolve(response({}));
    }));
    vi.stubGlobal("WebSocket", class { close() {} addEventListener() {} });
    const rendered = render(<App />);
    await waitFor(() => expect(screen.getAllByRole("button", { name: "Inspect plan" }).length).toBeGreaterThan(0));
    fireEvent.change(screen.getByRole("combobox", { name: "Project" }), { target: { value: "p1" } });
    await waitFor(() => expect(calls).toContain("/api/projects/p1/runs"));
    fireEvent.click(screen.getAllByRole("button", { name: "Inspect plan" })[0]);
    await waitFor(() => expect(calls).toContain("/api/runs/r1/plan"));
    expect(calls).not.toContain("/api/projects/p1/debug/plan");
    rendered.unmount();
  }, 15000);
});
