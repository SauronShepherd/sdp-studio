import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { WorkspaceTabs } from "./WorkspaceTabs";

describe("WorkspaceTabs", () => {
  it("routes each view to its live panel", () => {
    const scroll = vi.fn();
    Element.prototype.scrollIntoView = scroll;
    function Harness() {
      const [active, setActive] = useState<"canvas" | "code" | "diff" | "comparison">("canvas");
      return <><WorkspaceTabs active={active} onChange={setActive} /><div className="code-panel" /></>;
    }
    render(<Harness />);
    fireEvent.click(screen.getByRole("tab", { name: "Code" }));
    expect(screen.getByRole("tab", { name: "Code" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "Code" })).toHaveAttribute("aria-controls", "workspace-view-code");
    expect(scroll).toHaveBeenCalled();
    scroll.mockRestore();
  });
});
