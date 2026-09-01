import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ExecutionHealthPanel } from "./ExecutionHealthPanel";

describe("ExecutionHealthPanel", () => {
  it("shows bounded stage skew and I/O diagnostics", () => {
    render(<ExecutionHealthPanel stages={[{ stage_id: 3, skew_score: 6, task_count: 4, max_task_ms: 120, shuffle_read_bytes: 10, shuffle_write_bytes: 20 }]} />);
    expect(screen.getByRole("region", { name: "Execution health details" })).toHaveTextContent("Stage 3");
    expect(screen.getByRole("region", { name: "Execution health details" })).toHaveTextContent("high skew");
    expect(screen.getByRole("region", { name: "Execution health details" })).toHaveTextContent("shuffle read 10");
    fireEvent.click(screen.getByRole("button", { name: "Hide metrics" }));
    expect(screen.getByRole("region", { name: "Execution health details" })).not.toHaveTextContent("Stage 3");
    expect(screen.getByRole("button", { name: "Show metrics" })).toHaveAttribute("aria-expanded", "false");
  });
});
