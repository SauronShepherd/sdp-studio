import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { GitGraphDiffPanel } from "./GitGraphDiffPanel";

describe("GitGraphDiffPanel", () => {
  it("requests and summarizes semantic graph changes", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ diff: { summary: { changed_nodes: 1 }, changed_nodes: [{}], added_nodes: [], removed_nodes: [], added_edges: [], removed_edges: [] } }), { status: 200 }));
    render(<GitGraphDiffPanel projectId="p1" />);
    fireEvent.click(screen.getByRole("button", { name: "Compare graph" }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("1 changed nodes"));
    vi.restoreAllMocks();
  });
});
