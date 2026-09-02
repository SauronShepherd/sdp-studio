import { expect, test } from "@playwright/test";

test("loads the visual IDE and completes the core project workflow", async ({ page }) => {
  await page.goto("/react-index.html");
  await expect(page.getByRole("heading", { name: "SDP Studio" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Operators" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Git", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Commit changes" })).toBeVisible();
  await page.getByRole("button", { name: "New project" }).click();
  await expect(page.getByRole("status")).toContainText("Created pipeline-");
  await page.getByRole("button", { name: "Validate" }).click();
  await expect(page.getByText("Pipeline is valid")).toBeVisible();
  await expect(page.getByRole("button", { name: "Refresh selected", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Full refresh all" })).toBeVisible();
  await page.getByRole("button", { name: "Inspect plan" }).click();
  await expect(page.getByRole("region", { name: "Plan inspector" })).toBeVisible();
  await page.getByRole("button", { name: "Python" }).click();
  await expect(page.getByRole("region", { name: "Generated source" })).toBeVisible();
  await page.getByRole("button", { name: "Add daily schedule" }).click();
  await expect(page.getByLabel("Schedules")).toContainText("enabled");
  await page.getByRole("button", { name: "Pause" }).click();
  await expect(page.getByLabel("Schedules")).toContainText("paused");
});

test("shows collaboration presence across two browser clients", async ({ browser, page }) => {
  await page.goto("/react-index.html");
  await page.getByRole("button", { name: "New project" }).click();
  await expect(page.getByRole("status")).toContainText("Created pipeline-");
  const projectId = await page.getByLabel("Project", { exact: true }).inputValue();
  await expect(page.getByLabel("Collaborators")).toHaveText(/[1-9]\d* collaborator/, { timeout: 20000 });

  const secondContext = await browser.newContext();
  const secondPage = await secondContext.newPage();
  try {
    await secondPage.goto("/react-index.html");
    await expect(secondPage.getByRole("heading", { name: "SDP Studio" })).toBeVisible();
    await secondPage.getByLabel("Project", { exact: true }).selectOption(projectId);
    await expect(page.getByLabel("Collaborators")).toHaveText(/[1-9]\d* collaborator/, { timeout: 20000 });
    await expect(secondPage.getByLabel("Collaborators")).toHaveText(/[1-9]\d* collaborator/, { timeout: 20000 });
  } finally {
    await secondContext.close();
  }
});

test("preserves configured node data after moving, saving, and reloading", async ({ page }) => {
  await page.goto("/react-index.html");
  const projectSelect = page.getByLabel("Project", { exact: true });
  const projectId = await page.evaluate(async () => {
    const csrf = document.cookie.split(";").map((item) => item.trim()).find((item) => item.startsWith("sdpstudio_csrf="))?.split("=")[1];
    const response = await fetch("/api/projects", { method: "POST", headers: { "Content-Type": "application/json", ...(csrf ? { "x-csrf-token": decodeURIComponent(csrf) } : {}) }, body: JSON.stringify({ name: `browser-regression-${crypto.randomUUID()}`, example: "retail-etl" }) });
    if (!response.ok) throw new Error(`project setup failed: ${response.status}`);
    return (await response.json()).id as string;
  });
  await page.reload();
  await expect(page.getByLabel("Project", { exact: true })).toBeVisible();
  await page.waitForTimeout(1000);
  await expect.poll(async () => projectSelect.locator(`option[value="${projectId}"]`).count()).toBe(1);
  await projectSelect.selectOption(projectId);

  const source = page.locator(".react-flow__node").filter({ hasText: "source.file" }).first();
  await expect(source).toBeVisible({ timeout: 20000 });
  await expect(page.getByLabel("Editor status")).toContainText(/nodes ·/, { timeout: 20000 });
  await source.getByRole("button", { name: "Select source.file" }).click({ force: true });
  const configuration = page.getByLabel("Node configuration JSON");
  await configuration.fill('{"table":"raw.orders","marker":"regression"}');
  await Promise.all([
    page.waitForResponse((response) => response.url().includes("/pipeline") && response.request().method() === "PUT"),
    page.getByRole("button", { name: "Save configuration" }).click(),
  ]);
  await expect(configuration).toHaveValue(/regression/);
  await expect.poll(async () => page.evaluate(async (id) => {
    const response = await fetch(`/api/projects/${id}/pipeline`);
    const document = await response.json();
    return document.nodes.some((node: { config?: { marker?: string } }) => node.config?.marker === "regression");
  }, projectId)).toBe(true);
  await page.waitForTimeout(300);

  const box = await source.boundingBox();
  if (!box) throw new Error("Source node is not laid out");
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width / 2 + 80, box.y + box.height / 2 + 40);
  await page.mouse.up();
  await page.waitForTimeout(700);
  await expect.poll(async () => page.evaluate(async (id) => {
    const response = await fetch(`/api/projects/${id}/pipeline`);
    const document = await response.json();
    return document.nodes.some((node: { config?: { marker?: string } }) => node.config?.marker === "regression");
  }, projectId)).toBe(true);
  await page.reload();
  await page.getByLabel("Project", { exact: true }).selectOption(projectId);
  await expect.poll(async () => page.evaluate(async (id) => {
    const response = await fetch(`/api/projects/${id}/pipeline`);
    const document = await response.json();
    return document.nodes.some((node: { config?: { marker?: string } }) => node.config?.marker === "regression");
  }, projectId)).toBe(true);
  await page.waitForTimeout(2000);
  await expect(page.getByLabel("Node configuration JSON")).toHaveValue(/regression/);
});

test("exposes activity navigation, theme persistence, and live editor status", async ({ page }) => {
  await page.goto("/react-index.html");
  await expect(page.getByRole("navigation", { name: "Workspace sections" })).toBeVisible();
  await expect(page.getByLabel("Editor status")).toContainText("Runtime: Local Spark");
  const theme = page.getByRole("button", { name: "Switch to light theme" });
  await theme.click();
  await expect(page.getByRole("button", { name: "Switch to dark theme" })).toBeVisible();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
});
