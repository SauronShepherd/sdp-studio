import { expect, test } from "@playwright/test";

test("loads the visual IDE and completes the core project workflow", async ({ page }) => {
  await page.goto("/react-index.html");
  await expect(page.getByRole("heading", { name: "SDP Studio" })).toBeVisible();
  await page.getByRole("button", { name: "New project" }).click();
  await expect(page.getByRole("status")).toContainText("Created pipeline-");
  await expect(page.getByLabel("Project", { exact: true })).not.toHaveValue("");
  await page.getByRole("button", { name: "Validate" }).click();
  await expect(page.getByRole("region", { name: "Problems" })).toContainText("Pipeline is valid");
  await page.getByRole("button", { name: "Python" }).click();
  await expect(page.getByRole("region", { name: "Generated source" })).toContainText("Generated Python");
  await page.getByRole("button", { name: "Run" }).click();
  await expect(page.getByLabel("Runs")).toContainText(/queued|running|succeeded|failed/);
  await page.getByRole("button", { name: "Schedule" }).click();
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
    const project = await response.json();
    return project.id as string;
  });
  await projectSelect.selectOption(projectId);
  await expect(page.getByRole("region", { name: "Pipeline canvas" })).toBeVisible();
  const sourceNode = page.locator(".react-flow__node").first();
  await sourceNode.click();
  await page.getByLabel("Inspector configuration").fill(JSON.stringify({ name: "persisted-name", path: "/tmp/source.csv" }, null, 2));
  await page.getByRole("button", { name: "Save config" }).click();
  await expect(page.getByRole("status")).toContainText("Configuration saved");
  const box = await sourceNode.boundingBox();
  if (box) {
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.mouse.down();
    await page.mouse.move(box.x + box.width / 2 + 80, box.y + box.height / 2 + 60, { steps: 5 });
    await page.mouse.up();
  }
  await page.waitForTimeout(500);
  await page.reload();
  await projectSelect.selectOption(projectId);
  await page.locator(".react-flow__node").first().click();
  await expect(page.getByLabel("Inspector configuration")).toContainText("persisted-name");
});

test("exposes activity navigation, theme persistence, and live editor status", async ({ page }) => {
  await page.goto("/react-index.html");
  await expect(page.getByLabel("Editor status")).toBeVisible();
  await page.getByRole("button", { name: "Activity" }).click();
  await expect(page.getByRole("region", { name: "Activity" })).toBeVisible();
  const theme = page.getByLabel("Theme");
  await theme.selectOption("light");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
});
