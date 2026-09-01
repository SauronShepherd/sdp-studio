import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { QUICK_START_STEPS, QuickStartWizard } from "./QuickStartWizard";

describe("QuickStartWizard", () => {
  afterEach(cleanup);
  it("walks through every guided first-run step", () => {
    const onAction = vi.fn();
    render(<QuickStartWizard onAction={onAction} onDismiss={vi.fn()} />);
    for (const step of QUICK_START_STEPS) {
      expect(screen.getAllByText(step.title)[0]).toBeInTheDocument();
      fireEvent.click(screen.getByRole("button", { name: step.action }));
    }
    expect(onAction).toHaveBeenCalledTimes(QUICK_START_STEPS.length);
  });

  it("allows the user to close the guide", () => {
    const onDismiss = vi.fn();
    render(<QuickStartWizard onAction={vi.fn()} onDismiss={onDismiss} />);
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(onDismiss).toHaveBeenCalled();
  });
});
