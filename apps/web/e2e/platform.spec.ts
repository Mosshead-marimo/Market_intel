import { expect, test } from "@playwright/test";

test("platform console exposes the foundation surface", async ({ page }) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: /Capability infrastructure/ }),
  ).toBeVisible();
  await expect(
    page.getByText("Foundation only · No market logic installed"),
  ).toBeVisible();
  await expect(
    page.getByText(/Platform unavailable|Command console/),
  ).toBeVisible();
});
