import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { RowTracePanel } from "./RowTracePanel";

describe("RowTracePanel", () => {
  it("renders bounded execution provenance and step counts", () => {
    render(<RowTracePanel value={JSON.stringify({ trace_mode: "execution", provenance: "runtime_preview_rows", trace_instrumentation: "spark_monotonically_increasing_id", steps: [{ node_id: "filter", input_count: 4, output_count: 2, trace_status: "known" }] })} />);
    expect(screen.getByRole("region", { name: "Row trace result" })).toHaveTextContent("runtime_preview_rows");
    expect(screen.getByRole("region", { name: "Row trace result" })).toHaveTextContent("4 → 2 rows");
  });
});
