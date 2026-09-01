import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { RunComparisonSelector } from "./RunComparisonSelector";

describe("RunComparisonSelector", () => {
  it("compares explicitly selected runs", () => {
    const onCompare = vi.fn();
    render(<RunComparisonSelector runs={[{ id: "r3", status: "succeeded" }, { id: "r2" }, { id: "r1" }]} onCompare={onCompare} />);
    fireEvent.change(screen.getByRole("combobox", { name: "Baseline run" }), { target: { value: "r1" } });
    fireEvent.change(screen.getByRole("combobox", { name: "Current run" }), { target: { value: "r3" } });
    fireEvent.click(screen.getByRole("button", { name: "Compare selected runs" }));
    expect(onCompare).toHaveBeenCalledWith("r1", "r3");
  });
});
