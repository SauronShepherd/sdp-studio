import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { RunComparisonPanel } from "./RunComparisonPanel";

describe("RunComparisonPanel", () => {
  it("renders bounded comparison sections", () => {
    render(<RunComparisonPanel value={JSON.stringify({ left: { id: "r1" }, right: { id: "r2" }, source_diff: { generated_source_available: true, unified_diff: "-old\n+new" }, node_diffs: [{ node_id: "filter" }], metric_deltas: { rows: 2 } })} />);
    expect(screen.getByRole("region", { name: "Run comparison" })).toHaveTextContent("r1");
    expect(screen.getByText("Node changes (1)")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Generated source differences" })).toHaveTextContent("-old");
  });
});
