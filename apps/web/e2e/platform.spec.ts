import { expect, test } from "@playwright/test";

test("chat shell exposes the mock conversation surface", async ({ page }) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", {
      name: /How can I help you test TradeSentinel/,
    }),
  ).toBeVisible();
  await expect(
    page.getByText(/No financial analysis is installed/),
  ).toBeVisible();
  await expect(page.getByLabel("Chat message")).toBeVisible();
});
