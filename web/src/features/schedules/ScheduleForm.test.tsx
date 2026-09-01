import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ScheduleForm } from "./ScheduleForm";

describe("ScheduleForm", () => {
  it("submits configurable cron, timezone, and mode", () => {
    const onSubmit = vi.fn();
    render(<ScheduleForm onSubmit={onSubmit} onCancel={vi.fn()} />);
    fireEvent.change(screen.getByRole("textbox", { name: "Schedule name" }), { target: { value: "hourly" } });
    fireEvent.change(screen.getByRole("textbox", { name: "Cron expression" }), { target: { value: "0 * * * *" } });
    fireEvent.change(screen.getByRole("combobox", { name: "Schedule mode" }), { target: { value: "refresh" } });
    fireEvent.click(screen.getByRole("button", { name: "Create schedule" }));
    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({ name: "hourly", cron: "0 * * * *", mode: "refresh" }));
  });
});
