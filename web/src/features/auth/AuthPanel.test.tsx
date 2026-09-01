import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { api } from "../../api";
import { AuthPanel } from "./AuthPanel";

describe("AuthPanel", () => {
  it("logs in, loads identity, and signs out", async () => {
    vi.spyOn(api, "login").mockResolvedValue({ username: "alice", authenticated: true });
    vi.spyOn(api, "me").mockResolvedValue({ username: "alice", role: "editor" });
    vi.spyOn(api, "logout").mockResolvedValue(undefined);
    const onToken = vi.fn();
    render(<AuthPanel onToken={onToken} />);
    fireEvent.change(screen.getByRole("textbox", { name: "Username" }), { target: { value: "alice" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "secret" } });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    await waitFor(() => expect(screen.getByText(/Signed in as alice/)).toBeInTheDocument());
    expect(window.localStorage.getItem("sdpstudioAuthToken")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Sign out" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Sign in" })).toBeInTheDocument());
    expect(onToken).toHaveBeenCalled();
  });
});
