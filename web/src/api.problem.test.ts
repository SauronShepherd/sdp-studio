import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "./api";

describe("API problem errors", () => {
  afterEach(() => vi.restoreAllMocks());

  it("preserves stable problem codes and messages", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            code: "SDPS-AUTH-001",
            message: "Forbidden operation",
            severity: "error",
          }),
          { status: 403, statusText: "Forbidden" },
        ),
      ),
    );

    await expect(api.projects()).rejects.toThrow(
      "SDPS-AUTH-001: Forbidden operation",
    );
  });

  it("falls back to HTTP status when the body is not a Problem", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response("not-json", { status: 503, statusText: "Unavailable" }),
      ),
    );

    await expect(api.projects()).rejects.toThrow("503 Unavailable");
  });
});
