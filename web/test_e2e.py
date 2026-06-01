"""E2E smoke test via Playwright: load app, click project, send message, screenshot."""
import sys, time, json
from pathlib import Path
from playwright.sync_api import sync_playwright
from test_helpers import login

ARTIFACTS = Path(__file__).resolve().parent / "test-artifacts"
ARTIFACTS.mkdir(exist_ok=True)
BASE = "http://127.0.0.1:5173"

errors = []
console_msgs = []

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 390, "height": 844})  # iPhone-ish
        page = ctx.new_page()

        page.on("console", lambda m: console_msgs.append(f"[{m.type}] {m.text}"))
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.on("requestfailed", lambda r: errors.append(f"reqfail: {r.url} — {r.failure}"))

        print(f"[1] navigate {BASE} + login")
        login(page, BASE)
        page.screenshot(path=str(ARTIFACTS / "01-project-list.png"), full_page=True)

        print("[2] wait for project list")
        page.wait_for_selector("[data-testid='project-list']", timeout=10000)
        items = page.locator("[data-testid^='project-item-']").count()
        print(f"    found {items} project items")
        assert items >= 4, f"expected ≥4 projects, got {items}"

        print("[3] click SIBEDAS (project id 1)")
        page.locator("[data-testid='project-item-1']").click()
        page.wait_for_selector("[data-testid='chat-input']", timeout=5000)
        name = page.locator("[data-testid='project-name']").text_content()
        print(f"    chat opened for: {name}")
        assert name and "SIBEDAS" in name
        page.screenshot(path=str(ARTIFACTS / "02-chat-empty.png"), full_page=True)

        print("[4] type message + send")
        page.locator("[data-testid='chat-input']").fill("say only the word 'pong' and nothing else")
        page.locator("[data-testid='send-btn']").click()

        print("[5] wait for assistant message")
        page.wait_for_function(
            """() => {
                const msgs = document.querySelectorAll('[data-testid=messages] li');
                if (msgs.length < 2) return false;
                const last = msgs[msgs.length - 1];
                return last && !last.querySelector('.animate-pulse');
            }""",
            timeout=90000,
        )
        page.screenshot(path=str(ARTIFACTS / "03-chat-response.png"), full_page=True)

        # extract assistant text
        last_text = page.locator("[data-testid='messages'] li").last.inner_text()
        print(f"[6] assistant reply: {last_text[:120]!r}")
        assert "pong" in last_text.lower(), f"no 'pong' in reply: {last_text!r}"

        print("[7] go back")
        page.locator("[data-testid='back-btn']").click()
        page.wait_for_selector("[data-testid='project-list']", timeout=5000)
        # verify resume badge appears for SIBEDAS now
        resume_badge = page.locator("[data-testid='project-item-1']").locator("text=resume").count()
        print(f"    resume badge present: {resume_badge}")
        page.screenshot(path=str(ARTIFACTS / "04-back-list-with-resume.png"), full_page=True)

        browser.close()

    if errors:
        print(f"\n--- ERRORS ({len(errors)}) ---")
        for e in errors:
            print(e)
        sys.exit(1)

    suspicious = [m for m in console_msgs if m.startswith("[error]") or m.startswith("[warning]")]
    if suspicious:
        print(f"\n--- CONSOLE WARN/ERROR ({len(suspicious)}) ---")
        for m in suspicious:
            print(m)

    print("\n✅ E2E passed. Screenshots in test-artifacts/")

if __name__ == "__main__":
    main()
