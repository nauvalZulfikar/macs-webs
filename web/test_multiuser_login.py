"""Visual smoke test for the 2-user login flow.

Verifies:
- Login form shows username + password fields
- Wrong creds → error
- shaka / pisang → enters app
- Logout → back to login
- tamu / kelapa → enters app
"""
import sys, os
from pathlib import Path
from playwright.sync_api import sync_playwright

ARTIFACTS = Path(__file__).resolve().parent / "test-artifacts"
ARTIFACTS.mkdir(exist_ok=True)
BASE = os.environ.get("BASE", "http://100.81.47.91:8101")

USERS = [("shaka", "pisang"), ("tamu", "kelapa")]


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        for idx, (u, pw) in enumerate(USERS):
            ctx = browser.new_context(viewport={"width": 390, "height": 844})
            page = ctx.new_page()

            print(f"\n=== user {u} ===")
            page.goto(BASE, wait_until="networkidle", timeout=15000)
            page.wait_for_selector("[data-testid='login-form']")
            assert page.locator("[data-testid='login-username']").count() == 1, "username field missing"
            assert page.locator("[data-testid='login-input']").count() == 1, "password field missing"

            if idx == 0:
                print("  [wrong] try bad creds")
                page.locator("[data-testid='login-username']").fill("nobody")
                page.locator("[data-testid='login-input']").fill("badpw")
                page.locator("[data-testid='login-btn']").click()
                page.wait_for_function(
                    "() => document.body.innerText.includes('Wrong username or password')",
                    timeout=5000,
                )
                page.screenshot(path=str(ARTIFACTS / "mu-01-wrong.png"), full_page=True)
                print("    rejected ✓")
                # clear fields
                page.locator("[data-testid='login-username']").fill("")
                page.locator("[data-testid='login-input']").fill("")

            print(f"  [ok] login as {u}")
            page.locator("[data-testid='login-username']").fill(u)
            page.locator("[data-testid='login-input']").fill(pw)
            page.locator("[data-testid='login-btn']").click()
            page.wait_for_selector("[data-testid='project-list']", timeout=10000)
            count = page.locator("[data-testid^='project-item-']").count()
            assert count >= 4, f"expected ≥4 projects, got {count}"
            print(f"    {count} projects visible ✓")
            page.screenshot(path=str(ARTIFACTS / f"mu-{idx+2:02d}-{u}-in.png"), full_page=True)

            print(f"  [logout] {u}")
            page.locator("[data-testid='logout-btn']").click()
            page.wait_for_selector("[data-testid='login-form']", timeout=5000)
            print("    back to login ✓")

            ctx.close()

        browser.close()

    print("\n✅ multi-user login passed. Screenshots in test-artifacts/")


if __name__ == "__main__":
    main()
