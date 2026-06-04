import { test, expect } from "@playwright/test";

test("app loads and shows title", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("text=MAREF")).toBeVisible();
});

test("can create new session", async ({ page }) => {
  await page.goto("/");
  await page.click('button:has-text("新会话")');
  await expect(page.locator(".session-item")).toBeVisible();
});

test("dark mode toggle works", async ({ page }) => {
  await page.goto("/");
  await page.click('[aria-label="切换主题"]');
  await expect(page.locator("html")).toHaveClass(/dark/);
});
