import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PreviewTable } from "./PreviewTable";

describe("PreviewTable", () => {
  it("renders bounded rows and profile summary", () => {
    render(<PreviewTable result={{ schema: [{ name: "id" }], rows: [{ id: 1 }], limit: 50, node_id: "n1", profile: { row_count: 1, columns: { id: { count: 1, null_count: 0, distinct_count: 1 } } } }} />);
    expect(screen.getByRole("region", { name: "Preview data" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "1" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Preview profile" })).toHaveTextContent("1 rows analyzed");
  });

  it("labels cached previews with their age", () => {
    render(<PreviewTable result={{ schema: [], rows: [], limit: 10, node_id: "n1", cache: { hit: true, age_seconds: 4.2, ttl_seconds: 300 } }} />);
    expect(screen.getByRole("status")).toHaveTextContent("Cached · 4.2s old");
  });
});
