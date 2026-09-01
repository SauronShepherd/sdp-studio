import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { SchemaInspector } from "./SchemaInspector";

describe("SchemaInspector", () => {
  it("preserves typed number and expression values", () => {
    const onChange = vi.fn();
    render(<SchemaInspector fields={[{ name: "limit", label: "Limit", type: "number" }, { name: "expr", label: "Expression", type: "expression" }]} value="{}" onChange={onChange} />);
    fireEvent.change(screen.getByRole("spinbutton", { name: "Limit" }), { target: { value: "12" } });
    expect(onChange).toHaveBeenCalledWith(expect.stringContaining('"limit": 12'));
    fireEvent.change(screen.getByRole("textbox", { name: "Expression" }), { target: { value: "amount > 0" } });
    expect(onChange).toHaveBeenLastCalledWith(expect.stringContaining('"expr": "amount > 0"'));
  });
});
