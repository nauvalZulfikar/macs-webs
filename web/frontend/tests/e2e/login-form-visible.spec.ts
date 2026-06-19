import { test, expect } from "@playwright/test";

test("user lands on root URL and sees login form with username and password inputs", async ({
  page,
}) => {
  // Arrange — navigate to the app root
  await page.goto("/");

  // Assert — login form container is visible
  await expect(page.getByTestId("login-form")).toBeVisible();

  // Assert — heading identifies the app
  await expect(page.getByRole("heading", { name: /MACS/i })).toBeVisible();

  // Assert — username input is visible (data-testid=login-username)
  await expect(page.getByTestId("login-username")).toBeVisible();

  // Assert — password input is visible (data-testid=login-input)
  await expect(page.getByTestId("login-input")).toBeVisible();

  // Evidence — explicit screenshot even on pass (config only screenshots on failure)
  await page.screenshot({
    path: "tests/e2e/screenshots/login-form-visible-final.png",
    fullPage: true,
  });
});
