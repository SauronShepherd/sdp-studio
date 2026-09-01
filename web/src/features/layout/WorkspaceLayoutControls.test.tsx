import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { WorkspaceLayoutControls, type WorkspaceLayout } from "./WorkspaceLayoutControls";

describe("WorkspaceLayoutControls", () => {
  afterEach(() => { cleanup(); window.localStorage.clear(); });
  it("persists resizing and collapse state", () => {
    const initial: WorkspaceLayout = { paletteWidth: 220, inspectorWidth: 260, paletteCollapsed: false, inspectorCollapsed: false };
    let current = initial;
    render(<WorkspaceLayoutControls value={current} onChange={(next) => { current = next; }} />);
    fireEvent.change(screen.getByRole("slider", { name: "Palette width" }), { target: { value: "300" } });
    expect(JSON.parse(window.localStorage.getItem("sdpstudio.workspace-layout") || "{}")).toMatchObject({ paletteWidth: 300 });
    fireEvent.click(screen.getByRole("button", { name: "Hide palette" }));
    expect(JSON.parse(window.localStorage.getItem("sdpstudio.workspace-layout") || "{}")).toMatchObject({ paletteCollapsed: true });
  });
});
