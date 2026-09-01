import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ActivityRail } from "./ActivityRail";

describe("ActivityRail", () => {
  afterEach(() => cleanup());

  it("routes Explorer and Catalog to their own panels", () => {
    const onSelect = vi.fn();
    const scrollIntoView = vi.fn();
    Element.prototype.scrollIntoView = scrollIntoView;
    render(<><ActivityRail theme="dark" activeSection="canvas" onSelect={onSelect} onToggleTheme={vi.fn()} /><div className="explorer-panel" /><div className="catalog-panel" /></>);
    screen.getByRole("button", { name: "Explorer" }).click();
    expect(onSelect).toHaveBeenCalledWith("explorer");
    screen.getByRole("button", { name: "Catalog" }).click();
    expect(onSelect).toHaveBeenCalledWith("catalog");
    expect(scrollIntoView).toHaveBeenCalledTimes(2);
  });

  it("opens the command palette from the button and keyboard shortcut", async () => {
    render(<ActivityRail theme="dark" activeSection="canvas" onSelect={vi.fn()} onToggleTheme={vi.fn()} />);
    screen.getByRole("button", { name: "Open command palette" }).click();
    await waitFor(() => expect(screen.getByRole("dialog", { name: "Command palette" })).toBeInTheDocument());
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Command palette" })).not.toBeInTheDocument());
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "k", ctrlKey: true }));
    await waitFor(() => expect(screen.getByRole("dialog", { name: "Command palette" })).toBeInTheDocument());
  });

  it("runs supplied pipeline commands from the palette", async () => {
    const run = vi.fn();
    render(<ActivityRail theme="dark" activeSection="canvas" onSelect={vi.fn()} onToggleTheme={vi.fn()} commands={[{ id: "run", label: "Run pipeline", run }]} />);
    fireEvent.click(screen.getByRole("button", { name: "Open command palette" }));
    fireEvent.click(await screen.findByRole("button", { name: /Run pipeline/ }));
    expect(run).toHaveBeenCalledOnce();
  });
});
