import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StatusBar } from "./StatusBar";

describe("StatusBar", () => {
  it("surfaces execution-health diagnostics alongside editor state", () => {
    render(<StatusBar projectId="project-1" nodes={2} edges={1} runtimeName="Local" collaborators={1} executionHealth="Run running · 2 stages · 1 severe skew stage" branch="main" dirty />);
    expect(screen.getByRole("contentinfo", { name: "Editor status" })).toHaveTextContent("2 stages");
    expect(screen.getByLabelText("Execution health")).toHaveTextContent("1 severe skew stage");
    expect(screen.getByLabelText("Git status")).toHaveTextContent("main · dirty");
  });
});
