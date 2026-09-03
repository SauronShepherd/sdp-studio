import { expect, test } from "@playwright/test";

test.describe("studio visual regression", () => {
  test("desktop shell and inspector remain visually stable", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "SDP Studio" })).toBeVisible();
    await expect(page.getByRole("combobox", { name: "Runtime profile" })).toBeVisible();
    await expect(page.getByLabel("Editor status")).toBeVisible();
    await expect(page).toHaveScreenshot("studio-desktop.png", {
      animations: "disabled",
      caret: "hide",
      mask: [page.getByLabel("Project"), page.getByLabel("Collaborators"), page.getByLabel("Editor status")],
      maxDiffPixels: 1000,
    });

    await page.getByRole("button", { name: "New project" }).click();
    await expect(page.getByRole("status")).toContainText("Created pipeline-");
    await page.getByRole("button", { name: "Python" }).click();
    await expect(page.getByRole("region", { name: "Generated source" })).toContainText("Generated Python");
    await expect(page.getByRole("region", { name: "Generated source" })).toHaveScreenshot("studio-python-inspector.png", {
      animations: "disabled",
      caret: "hide",
      maxDiffPixels: 2500,
    });
  });

  test("mobile shell keeps primary controls reachable", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "SDP Studio" })).toBeVisible();
    await expect(page.getByRole("button", { name: "New project" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Validate" })).toBeVisible();
    await expect(page.getByRole("combobox", { name: "Runtime profile" })).toBeVisible();
    await expect(page.getByLabel("Editor status")).toBeVisible();
    await expect(page).toHaveScreenshot("studio-mobile.png", {
      animations: "disabled",
      caret: "hide",
      mask: [page.getByLabel("Project"), page.getByLabel("Collaborators"), page.getByLabel("Editor status")],
    });
  });
});
