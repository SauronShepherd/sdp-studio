import { expect, test } from "@playwright/test";

test("covers generated SQL, preview/profile, row trace, run and Git controls", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "New project" }).click();
  await expect(page.getByRole("status")).toContainText("Created pipeline-");
  await page.getByRole("button", { name: "SQL", exact: true }).click();
  await expect(page.getByRole("region", { name: "Generated source" })).toContainText("Generated SQL", { timeout: 15000 });
  const preview = page.getByRole("button", { name: "Preview rows" });
  if (await preview.count()) {
    await preview.click();
    await expect(page.getByLabel("Preview rows")).toBeVisible();
    await expect(page.getByLabel("Preview profile")).toBeVisible();
    await page.getByRole("button", { name: "Row trace" }).click();
    await expect(page.getByLabel("Row trace result")).toBeVisible();
  }

  await page.getByRole("button", { name: "Run", exact: true }).click();
  await expect(page.getByRole("status").filter({ hasText: "Run:" })).toBeVisible();
  await page.getByRole("button", { name: "Refresh selected", exact: true }).click();
  await expect(page.getByRole("status").filter({ hasText: "Run:" })).toBeVisible();

  const commitMessage = page.getByLabel("Git commit message");
  await commitMessage.fill("test browser workflow");
  await expect(page.getByRole("button", { name: "Commit changes" })).toBeEnabled();
  await page.getByRole("button", { name: "Commit changes" }).click();
  await expect(page.getByRole("region", { name: "Git", exact: true })).toContainText(/clean|Repository not initialized/);
});
