import { render, screen } from "@testing-library/react";
import type { ComponentProps } from "react";
import { ReactFlowProvider } from "@xyflow/react";
import { describe, expect, it } from "vitest";
import { GenericNode } from "./GenericNode";

describe("GenericNode", () => {
  it("renders operator identity and typed handles", () => {
    const props = { id: "n1", data: { label: "Filter", operatorId: "transform.filter" }, selected: false, type: "generic", xPos: 0, yPos: 0, zIndex: 0, isConnectable: true } as unknown as ComponentProps<typeof GenericNode>;
    render(<ReactFlowProvider><GenericNode {...props} /></ReactFlowProvider>);
    expect(screen.getByRole("group", { name: "Filter node" })).toBeInTheDocument();
    expect(screen.getByLabelText("Input")).toBeInTheDocument();
    expect(screen.getByLabelText("Output")).toBeInTheDocument();
  });

  it("renders performance health overlays when supplied", () => {
    const props = { id: "n1", data: { label: "Join", operatorId: "transform.join", health: "severe skew", healthDetail: "skew score 6" }, selected: false, type: "generic", xPos: 0, yPos: 0, zIndex: 0, isConnectable: true } as unknown as ComponentProps<typeof GenericNode>;
    render(<ReactFlowProvider><GenericNode {...props} /></ReactFlowProvider>);
    expect(screen.getByText("severe skew")).toHaveAttribute("title", "skew score 6");
  });

  it("renders every declared typed port", () => {
    const props = { id: "n1", data: { label: "Join", operatorId: "transform.join", inputs: ["left", "right"], outputs: ["out"] }, selected: false, type: "generic", xPos: 0, yPos: 0, zIndex: 0, isConnectable: true } as unknown as ComponentProps<typeof GenericNode>;
    render(<ReactFlowProvider><GenericNode {...props} /></ReactFlowProvider>);
    expect(screen.getByLabelText("Input left")).toBeInTheDocument();
    expect(screen.getByLabelText("Input right")).toBeInTheDocument();
  });

  it("renders mode, materialization, provider, lifecycle, and metric badges", () => {
    const props = { id: "n1", data: { label: "Orders", operatorId: "dataset.materialized_view", mode: "streaming", materialization: "materialized", provider: "databricks", status: "cached-preview", metrics: { rows: 42 } }, selected: false, type: "generic", xPos: 0, yPos: 0, zIndex: 0, isConnectable: true } as unknown as ComponentProps<typeof GenericNode>;
    render(<ReactFlowProvider><GenericNode {...props} /></ReactFlowProvider>);
    expect(screen.getByText("streaming")).toBeInTheDocument();
    expect(screen.getByText("materialized")).toBeInTheDocument();
    expect(screen.getByText("databricks")).toBeInTheDocument();
    expect(screen.getByText("cached-preview")).toBeInTheDocument();
    expect(screen.getByLabelText("rows: 42")).toBeInTheDocument();
  });

  it("renders the selected debug metric overlay, including unavailable values", () => {
    const props = { id: "n1", data: { label: "Orders", operatorId: "source.csv", overlayMetric: "bytes", overlayValue: "unavailable" }, selected: false, type: "generic", xPos: 0, yPos: 0, zIndex: 0, isConnectable: true } as unknown as ComponentProps<typeof GenericNode>;
    render(<ReactFlowProvider><GenericNode {...props} /></ReactFlowProvider>);
    expect(screen.getByLabelText("bytes: unavailable")).toBeInTheDocument();
  });
});
