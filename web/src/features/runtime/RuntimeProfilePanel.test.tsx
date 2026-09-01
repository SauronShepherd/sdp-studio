import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { RuntimeProfilePanel } from "./RuntimeProfilePanel";

describe("RuntimeProfilePanel", () => {
  it("edits Databricks settings without exposing token fields", () => {
    const onSaveConfig = vi.fn();
    render(<RuntimeProfilePanel profiles={[{ id: "db", name: "Databricks", adapter: "databricks", config: {} }]} value="db" onChange={vi.fn()} onTest={vi.fn()} onSaveConfig={onSaveConfig} />);
    fireEvent.change(screen.getByRole("textbox", { name: "Databricks workspace URL" }), { target: { value: "https://workspace.example" } });
    fireEvent.change(screen.getByRole("textbox", { name: "Databricks secret reference" }), { target: { value: "secret://db/token" } });
    fireEvent.click(screen.getByRole("button", { name: "Save Databricks settings" }));
    expect(onSaveConfig).toHaveBeenCalledWith(expect.objectContaining({ workspace_url: "https://workspace.example", secret_ref: "secret://db/token" }));
    expect(screen.queryByLabelText(/token value/i)).not.toBeInTheDocument();
  });

  it("edits typed Kubernetes runtime settings", () => {
    const onSaveConfig = vi.fn();
    render(<RuntimeProfilePanel profiles={[{ id: "k8s", name: "Kubernetes", adapter: "kubernetes", config: {} }]} value="k8s" onChange={vi.fn()} onTest={vi.fn()} onSaveConfig={onSaveConfig} />);
    fireEvent.change(screen.getByRole("textbox", { name: "Kubernetes image" }), { target: { value: "spark:4.2" } });
    fireEvent.change(screen.getByRole("textbox", { name: "Kubernetes executor instances" }), { target: { value: "3" } });
    fireEvent.click(screen.getByRole("button", { name: "Save Kubernetes settings" }));
    expect(onSaveConfig).toHaveBeenCalledWith(expect.objectContaining({ image: "spark:4.2", executor_instances: 3 }));
  });
});
