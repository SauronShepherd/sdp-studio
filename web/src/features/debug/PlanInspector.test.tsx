import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PlanInspector } from "./PlanInspector";

describe("PlanInspector", () => {
  it("renders structural plan operations", () => {
    render(<PlanInspector value={JSON.stringify({ nodes: [{ operator: "Filter" }], diff: { operations: [{ op: "replace", index: 0, before: { operator: "Scan" }, after: { operator: "Filter" } }] } })} />);
    expect(screen.getByRole("region", { name: "Plan diff" })).toHaveTextContent("replace");
  });
});
