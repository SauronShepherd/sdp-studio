import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ProblemsPanel } from "./ProblemsPanel";

describe("ProblemsPanel", () => {
  afterEach(cleanup);
  it("renders findings and navigates to a node", () => {
    const onSelectNode = vi.fn();
    render(<ProblemsPanel problems={[{ code: "SDPS-001", severity: "error", message: "Bad filter", node_id: "filter-1" }]} onSelectNode={onSelectNode} />);
    expect(screen.getByRole("region", { name: "Problems" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /SDPS-001/ }));
    expect(onSelectNode).toHaveBeenCalledWith("filter-1");
  });

  it("filters findings by stable code or message", () => {
    render(<ProblemsPanel problems={[{ code: "SDPS-001", severity: "error", message: "Bad filter", node_id: "filter-1" }, { code: "SDPS-002", severity: "warning", message: "Slow source", node_id: "source-1" }]} onSelectNode={vi.fn()} />);
    fireEvent.change(screen.getByRole("textbox", { name: "Filter problems" }), { target: { value: "slow" } });
    expect(screen.getByRole("button", { name: /SDPS-002/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /SDPS-001/ })).not.toBeInTheDocument();
  });
});
