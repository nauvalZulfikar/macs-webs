"""Phase 5 smoke: open Tasks drawer in UI, add task, verify persists across reload."""
import asyncio
from playwright.async_api import async_playwright

COOKIE_FILE = "/tmp/macs-claude-cookie.txt"
BASE = "http://100.81.47.91:8101"
OUT = "/Users/shaka-mac-mini/coding-projects/macs/web/test-artifacts/phase-tests/phase5-tasks.png"


def read_cookie() -> str:
    for ln in open(COOKIE_FILE):
        s = ln.strip()
        if not s: continue
        if s.startswith("#HttpOnly_"): s = s[len("#HttpOnly_"):]
        elif s.startswith("#"): continue
        parts = s.split("\t")
        if len(parts) >= 7 and parts[5] == "pw_session": return parts[6]
    raise SystemExit("no pw_session cookie")


async def main():
    cookie = read_cookie()
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1440, "height": 900})
        await ctx.add_cookies([{
            "name": "pw_session", "value": cookie,
            "domain": "100.81.47.91", "path": "/", "httpOnly": True,
            "secure": False, "sameSite": "Lax",
        }])
        page = await ctx.new_page()

        await page.goto(BASE + "/", wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(800)

        print("opening agentic-hell…")
        await page.locator("text=/agentic.?hell/i").first.click()
        await page.wait_for_timeout(1200)

        print("clicking Tasks button…")
        await page.locator("[data-testid='tasks-btn']").click()
        await page.wait_for_selector("[data-testid='tasks-drawer']", timeout=5000)
        print("  ✓ drawer opened")

        print("adding task 'phase 5 verify'…")
        await page.locator("[data-testid='new-task-input']").fill("phase 5 verify task")
        await page.locator("[data-testid='add-task-btn']").click()
        await page.wait_for_timeout(500)

        # Count tasks in drawer
        count = await page.locator("[data-testid^='task-']").count()
        print(f"  visible tasks: {count}")
        if count == 0:
            print("✗ FAIL — no task rendered")
            await page.screenshot(path=OUT)
            return

        await page.screenshot(path=OUT)
        print(f"  saved → {OUT}")

        print("reload to test persistence…")
        await page.reload(wait_until="networkidle")
        await page.wait_for_timeout(1000)
        await page.locator("text=/agentic.?hell/i").first.click()
        await page.wait_for_timeout(1200)
        await page.locator("[data-testid='tasks-btn']").click()
        await page.wait_for_selector("[data-testid='tasks-drawer']", timeout=5000)
        await page.wait_for_timeout(500)
        count2 = await page.locator("[data-testid^='task-']").count()
        print(f"  after reload tasks: {count2}")
        if count2 >= 1:
            print("✅ PASS — task survived reload")
        else:
            print("✗ FAIL — task disappeared after reload")

        await browser.close()


asyncio.run(main())
