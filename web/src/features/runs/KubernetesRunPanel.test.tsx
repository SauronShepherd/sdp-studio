import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { KubernetesRunPanel } from "./KubernetesRunPanel";

describe("KubernetesRunPanel", () => {
  it("loads and renders bounded runtime status", async () => {
    vi.spyOn((await import("../../api")).api, "kubernetesStatus").mockResolvedValue({ phase: "Running", pod: "driver-1" });
    render(<KubernetesRunPanel runId="run-1" />);
    fireEvent.click(screen.getByRole("button", { name: "Load status" }));
    await waitFor(() => expect(screen.getByRole("region", { name: "Kubernetes run details" })).toHaveTextContent("driver-1"));
  });
});
