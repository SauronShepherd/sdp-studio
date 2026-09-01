import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ParameterEditor } from "./ParameterEditor";

describe("ParameterEditor", () => {
  afterEach(cleanup);
  it("edits a typed pipeline parameter default", () => {
    const onChange = vi.fn();
    render(<ParameterEditor parameters={[{ id: "p1", config: { name: "limit", default: 10 } }]} onChange={onChange} />);
    fireEvent.change(screen.getByLabelText("Parameter limit"), { target: { value: "25" } });
    expect(onChange).toHaveBeenCalledWith("p1", { name: "limit", default: "25" });
  });

  it("supports kind selection and typed integer values", () => {
    const onChange = vi.fn();
    const { rerender } = render(<ParameterEditor parameters={[{ id: "p1", config: { name: "limit", default: 10 } }]} onChange={onChange} />);
    fireEvent.change(screen.getByLabelText("Parameter type limit"), { target: { value: "int" } });
    rerender(<ParameterEditor parameters={[{ id: "p1", config: { name: "limit", kind: "int", default: 10 } }]} onChange={onChange} />);
    fireEvent.change(screen.getByLabelText("Parameter limit"), { target: { value: "25" } });
    expect(onChange).toHaveBeenLastCalledWith("p1", { name: "limit", kind: "int", default: 25 });
  });

  it("does not expose secret values and uses references for secret-ref parameters", () => {
    const onChange = vi.fn();
    render(<ParameterEditor parameters={[{ id: "p1", config: { name: "token", kind: "secret-ref", default: "secret://TOKEN" } }]} onChange={onChange} />);
    expect(screen.getByPlaceholderText("secret://NAME")).toHaveValue("secret://TOKEN");
  });
});
