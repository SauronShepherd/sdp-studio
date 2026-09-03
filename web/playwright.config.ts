import { defineConfig, devices } from "@playwright/test";
import os from "node:os";
import path from "node:path";

const e2eDataRoot = path.join(os.tmpdir(), `sdpstudio-e2e-${process.pid}`);

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  workers: 1,
  reporter: [["line"], ["html", { open: "never" }]],
  use: { baseURL: "http://127.0.0.1:8788", trace: "retain-on-failure" },
  webServer: [
    {
      command: "pnpm build && python -m uvicorn sdpstudio_server.app:create_app --factory --port 8788",
      url: "http://127.0.0.1:8788/health",
      reuseExistingServer: false,
      env: {
        PYTHONPATH: path.resolve(process.cwd(), "../python"),
        SDPSTUDIO_DATA_ROOT: e2eDataRoot,
      },
    },
  ],
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
