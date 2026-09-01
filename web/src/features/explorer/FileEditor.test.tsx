import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { FileEditor } from "./FileEditor";

describe("FileEditor", () => {
  afterEach(() => cleanup());
  it("loads and saves using the current etag", async () => {
    const readFile = vi.fn().mockResolvedValue({ path: "README.md", content: "old", etag: "v1" });
    const writeFile = vi.fn().mockResolvedValue({ path: "README.md", kind: "file", etag: "v2" });
    render(<FileEditor projectId="p1" files={[{ path: "README.md", kind: "file" }]} readFile={readFile} writeFile={writeFile} />);
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "README.md" } });
    await waitFor(() => expect(screen.getByRole("textbox", { name: "File contents" })).toHaveValue("old"));
    fireEvent.change(screen.getByRole("textbox", { name: "File contents" }), { target: { value: "new" } });
    fireEvent.click(screen.getByRole("button", { name: "Save file" }));
    await waitFor(() => expect(writeFile).toHaveBeenCalledWith("p1", "README.md", "new", "v1"));
  });

  it("surfaces an etag conflict without overwriting local content", async () => {
    const readFile = vi.fn().mockResolvedValue({ path: "README.md", content: "local", etag: "v1" });
    const writeFile = vi.fn().mockRejectedValue(new Error("409 Conflict"));
    render(<FileEditor projectId="p1" files={[{ path: "README.md", kind: "file" }]} readFile={readFile} writeFile={writeFile} />);
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "README.md" } });
    await waitFor(() => expect(screen.getByRole("textbox", { name: "File contents" })).toHaveValue("local"));
    fireEvent.click(screen.getByRole("button", { name: "Save file" }));
    expect(await screen.findByRole("status")).toHaveTextContent("reload before saving");
    expect(screen.getByRole("alert")).toHaveTextContent("Conflict");
    fireEvent.click(screen.getByRole("button", { name: "Reload file" }));
    await waitFor(() => expect(screen.getByRole("textbox", { name: "File contents" })).toHaveValue("local"));
  });

  it("creates a new file through the optimistic write contract", async () => {
    const writeFile = vi.fn().mockResolvedValue({ path: "notes.md", kind: "file", etag: "v1" });
    vi.spyOn(window, "prompt").mockReturnValue("notes.md");
    render(<FileEditor projectId="p1" files={[]} writeFile={writeFile} />);
    fireEvent.click(screen.getByRole("button", { name: "Create file" }));
    await waitFor(() => expect(writeFile).toHaveBeenCalledWith("p1", "notes.md", ""));
    expect(await screen.findByRole("status")).toHaveTextContent("File created");
  });

  it("keeps multiple files open as switchable tabs", async () => {
    const readFile = vi.fn().mockImplementation(async (_project: string, path: string) => ({ path, content: path === "a.py" ? "a" : "b", etag: path }));
    render(<FileEditor projectId="p1" files={[{ path: "a.py", kind: "file" }, { path: "b.py", kind: "file" }]} readFile={readFile} />);
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "a.py" } });
    await waitFor(() => expect(screen.getByRole("textbox", { name: "File contents" })).toHaveValue("a"));
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "b.py" } });
    await waitFor(() => expect(screen.getByRole("textbox", { name: "File contents" })).toHaveValue("b"));
    expect(screen.getByRole("tab", { name: /b\.py/ })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /a\.py/ })).toBeInTheDocument();
  });
});
