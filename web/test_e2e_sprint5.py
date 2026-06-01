"""Sprint 5 E2E: auth + production build serving.

Validates:
- Production build served by FastAPI works (no Vite needed)
- Login screen appears on first visit
- Wrong password rejected
- Correct password lets you in
- After login, project list + chat work
- Logout clears session
"""
import sys, os
from pathlib import Path
from playwright.sync_api import sync_playwright
from test_helpers import get_password

ARTIFACTS = Path(__file__).resolve().parent / "test-artifacts"
ARTIFACTS.mkdir(exist_ok=True)
PROD_BASE = os.environ.get("PROD_BASE", "http://100.81.47.91:8101")

errors = []
console_msgs = []


def main():
    pw = get_password()
    print(f"using password: {pw[:6]}…")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 390, "height": 844})
        page = ctx.new_page()
        page.on("console", lambda m: console_msgs.append(f"[{m.type}] {m.text}"))
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.on("requestfailed", lambda r: errors.append(f"reqfail: {r.url} — {r.failure}"))

        print(f"[1] visit prod build {PROD_BASE}/")
        page.goto(PROD_BASE, wait_until="networkidle", timeout=20000)

        print("[2] login screen visible (no cookie yet)")
        page.wait_for_selector("[data-testid='login-form']", timeout=5000)
        assert page.locator("[data-testid='login-input']").count() == 1
        page.screenshot(path=str(ARTIFACTS / "s5-01-login-screen.png"), full_page=True)

        print("[3] wrong password rejected")
        page.locator("[data-testid='login-input']").fill("wrong-password")
        page.locator("[data-testid='login-btn']").click()
        page.wait_for_function(
            "() => Array.from(document.querySelectorAll('*')).some(e => e.innerText && e.innerText.includes('Wrong password'))",
            timeout=5000,
        )
        print("    error message shown ✓")
        page.screenshot(path=str(ARTIFACTS / "s5-02-wrong-pw.png"), full_page=True)

        print("[4] correct password → enters app")
        page.locator("[data-testid='login-input']").fill(pw)
        page.locator("[data-testid='login-btn']").click()
        page.wait_for_selector("[data-testid='project-list']", timeout=10000)
        projects = page.locator("[data-testid^='project-item-']").count()
        print(f"    {projects} projects loaded after login")
        assert projects >= 4
        # logout button present
        assert page.locator("[data-testid='logout-btn']").count() == 1
        page.screenshot(path=str(ARTIFACTS / "s5-03-after-login.png"), full_page=True)

        print("[5] click a project + send a message (full chat path)")
        page.locator("[data-testid='project-item-1']").click()
        page.wait_for_selector("[data-testid='chat-input']")
        page.wait_for_function(
            "() => !document.querySelector('[data-testid=loading]')", timeout=10000
        )
        page.locator("[data-testid='new-convo-btn']").click()
        page.locator("[data-testid='chat-input']").fill("reply with: sprint5-prod-ok")
        page.locator("[data-testid='send-btn']").click()
        page.wait_for_function(
            """() => {
                const msgs = document.querySelectorAll('[data-testid=messages] li');
                if (msgs.length < 2) return false;
                const last = msgs[msgs.length - 1];
                if (!last || last.querySelector('.animate-pulse')) return false;
                return !!document.querySelector('[data-testid=send-btn]');
            }""",
            timeout=90000,
        )
        body = page.locator("[data-testid='messages']").inner_text()
        assert "sprint5-prod-ok" in body, f"missing marker: {body[:200]}"
        print("    chat reply received ✓")
        page.screenshot(path=str(ARTIFACTS / "s5-04-chat-via-prod.png"), full_page=True)

        print("[6] logout → cookie cleared → back to login")
        page.locator("[data-testid='back-btn']").click()
        page.wait_for_selector("[data-testid='project-list']")
        page.locator("[data-testid='logout-btn']").click()
        page.wait_for_selector("[data-testid='login-form']", timeout=5000)
        print("    login form re-shown ✓")

        # verify cookie actually cleared by re-fetching /api/projects raw via JS
        ok = page.evaluate("""async () => {
            const r = await fetch('/api/projects')
            return r.status === 401
        }""")
        assert ok, "expected 401 after logout"
        print("    /api/projects returns 401 after logout ✓")
        page.screenshot(path=str(ARTIFACTS / "s5-05-after-logout.png"), full_page=True)

        browser.close()

    if errors:
        # filter noise: 401 responses are expected during the test
        real = [e for e in errors if "401" not in e]
        if real:
            print(f"\n--- ERRORS ({len(real)}) ---")
            for e in real:
                print(e)
            sys.exit(1)

    suspicious = [m for m in console_msgs if m.startswith("[error]") and "401" not in m]
    if suspicious:
        print(f"\n--- CONSOLE ERRORS ({len(suspicious)}) ---")
        for m in suspicious:
            print(m)
        sys.exit(1)

    print("\n✅ Sprint 5 E2E passed. Screenshots in test-artifacts/")


if __name__ == "__main__":
    main()
