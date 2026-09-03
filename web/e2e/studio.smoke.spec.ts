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
  await expect(page.getByLabel("Collaborators")).toHaveText("0 collaborators");

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
  await expect(page.getByLabel("Collaborators")).toHaveText("0 collaborators", { timeout: 20000 });
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
  await projectSelect.selectOption(projectId);
  await page.getByRole("button", { name: "Source" }).click();
  await page.getByLabel("Node label").fill("Orders input");
  await page.getByLabel("Format").selectOption("json");
  await page.getByLabel("Path").fill("/tmp/orders.json");
  await page.getByRole("button", { name: "Save node" }).click();
  await expect(page.getByRole("status")).toContainText("Saved");
  const node = page.locator(".react-flow__node").filter({ hasText: "Orders input" });
  const before = await node.boundingBox();
  if (!before) throw new Error("configured node did not render");
  await node.hover();
  await page.mouse.down();
  await page.mouse.move(before.x + 150, before.y + 120, { steps: 8 });
  await page.mouse.up();
  await page.getByRole("button", { name: "Save project" }).click();
  await expect(page.getByRole("status")).toContainText("Saved");
  await page.reload();
  await projectSelect.selectOption(projectId);
  await expect(page.locator(".react-flow__node").filter({ hasText: "Orders input" })).toBeVisible();
  await expect(page.getByLabel("Format")).toHaveValue("json");
  await expect(page.getByLabel("Path")).toHaveValue("/tmp/orders.json");
});

test("exposes activity navigation, theme persistence, and live editor status", async ({ page }) => {
  await page.goto("/react-index.html");
  await expect(page.getByRole("button", { name: "Toggle theme" })).toBeVisible();
  await page.getByRole("button", { name: "Toggle theme" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await expect(page.getByLabel("Editor status")).toBeVisible();
  await page.getByRole("button", { name: "Activity" }).click();
  await expect(page.getByRole("heading", { name: "Activity" })).toBeVisible();
});
