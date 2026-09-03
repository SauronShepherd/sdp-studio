import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

test("studio shell has no automated accessibility violations", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "SDP Studio" })).toBeVisible();

  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);
});
