"""Headless screenshot of MACS agentic-hell session showing safety_warning UI."""
import asyncio
import sys
from playwright.async_api import async_playwright

COOKIE_FILE = "/tmp/macs-claude-cookie.txt"
BASE = "http://100.81.47.91:8101"
OUT = "/Users/shaka-mac-mini/coding-projects/macs/web/test-artifacts/agentic-stress/safety-warning-ui.png"


def read_cookie() -> str:
    for ln in open(COOKIE_FILE):
        s = ln.strip()
        if not s:
            continue
        if s.startswith("#HttpOnly_"):
            s = s[len("#HttpOnly_"):]
        elif s.startswith("#"):
            continue
        parts = s.split("\t")
        if len(parts) >= 7 and parts[5] == "pw_session":
            return parts[6]
    raise SystemExit("no pw_session cookie")


async def main():
    cookie = read_cookie()
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1440, "height": 900})
        await context.add_cookies([{
            "name": "pw_session",
            "value": cookie,
            "domain": "100.81.47.91",
            "path": "/",
            "httpOnly": True,
            "secure": False,
            "sameSite": "Lax",
        }])
        page = await context.new_page()
        page.on("console", lambda m: print(f"  [console.{m.type}] {m.text[:200]}"))
        page.on("pageerror", lambda e: print(f"  [pageerror] {str(e)[:200]}"))

        print("navigating…")
        await page.goto(BASE + "/", wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(1000)

        print("clicking agentic-hell…")
        btn = page.locator("text=/agentic.?hell/i").first
        await btn.wait_for(timeout=8000)
        await btn.click()
        await page.wait_for_timeout(1500)

        # Scroll to latest safety_warning
        count = await page.evaluate(
            "() => { const els = document.querySelectorAll('[data-testid^=\"safety-warning-\"]');"
            "if (els.length) els[els.length-1].scrollIntoView({block:'center'}); return els.length; }"
        )
        print(f"safety_warning elements on page: {count}")
        await page.wait_for_timeout(500)

        await page.screenshot(path=OUT, full_page=False)
        print(f"saved → {OUT}")
        await browser.close()
        return count


count = asyncio.run(main())
sys.exit(0 if count > 0 else 2)
