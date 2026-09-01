import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { GraphOutline } from "./GraphOutline";

describe("GraphOutline", () => {
  it("provides a textual accessible graph alternative", () => {
    render(<GraphOutline nodes={[{ id: "source", label: "Orders", operatorId: "source.table" }, { id: "out", label: "Clean", operatorId: "dataset.materialized_view" }]} edges={[{ source: "source", target: "out" }]} />);
    expect(screen.getByRole("region", { name: "Pipeline outline" })).toHaveTextContent("Orders");
    expect(screen.getByRole("region", { name: "Pipeline outline" })).toHaveTextContent("Clean");
  });
});
