import { test, expect } from "@playwright/test";

test("verify-toggle expander appears + opens with 2 inputs when clicked", async ({
  page,
}) => {
  // Login
  await page.goto("/");
  await expect(page.getByTestId("login-form")).toBeVisible();
  await page.getByTestId("login-username").fill("shaka");
  await page.getByTestId("login-input").fill("pisang");
  await page.getByRole("button", { name: /sign in/i }).click();

  // Wait for welcome screen (post-login landing)
  await expect(page.getByText(/welcome to macs/i)).toBeVisible({
    timeout: 10_000,
  });

  // Click "Lanjut chat terakhir" card to enter most-recent chat
  await page
    .getByText(/lanjut chat terakhir/i)
    .first()
    .click();

  // Wait for chat input area to render
  await expect(page.getByTestId("chat-input")).toBeVisible({ timeout: 15_000 });

  // Verify toggle should be visible (collapsed by default)
  const toggle = page.getByTestId("verify-toggle");
  await expect(toggle).toBeVisible();
  await expect(toggle).toContainText(/verify after send/i);

  // Click to expand
  await toggle.click();

  // Both inputs visible after expand
  await expect(page.getByTestId("verify-url-input")).toBeVisible();
  await expect(page.getByTestId("verify-what-input")).toBeVisible();

  // Fill them to prove they're usable
  await page.getByTestId("verify-url-input").fill("http://100.81.47.91:8101/");
  await page
    .getByTestId("verify-what-input")
    .fill("login form is visible with username and password inputs");

  // Screenshot
  await page.screenshot({
    path: "tests/e2e/screenshots/verify-toggle-visible-final.png",
    fullPage: true,
  });
});
