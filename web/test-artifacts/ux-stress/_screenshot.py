"""UI verify: drive composer with 'Make it better' (the old-catastrophe prompt),
screenshot the chat showing the agent now asks instead of going on a 19-tool spree."""
import asyncio
from playwright.async_api import async_playwright

COOKIE_FILE = "/tmp/macs-claude-cookie.txt"
BASE = "http://100.81.47.91:8101"
OUT = "/Users/shaka-mac-mini/coding-projects/macs/web/test-artifacts/ux-stress/ux-after-fix.png"


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
            "name": "pw_session", "value": cookie,
            "domain": "100.81.47.91", "path": "/", "httpOnly": True,
            "secure": False, "sameSite": "Lax",
        }])
        page = await context.new_page()

        print("navigating…")
        await page.goto(BASE + "/", wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(800)

        print("opening agentic-hell…")
        btn = page.locator("text=/agentic.?hell/i").first
        await btn.wait_for(timeout=8000)
        await btn.click()
        await page.wait_for_timeout(1500)

        # Start a fresh conversation — find the "new chat" / "+" button if any,
        # otherwise just type into the composer (backend will append to last session).
        print("typing 'Make it better' to test ASK-ON-VAGUE rule…")
        composer = page.locator("textarea, [data-testid='composer-input']").first
        await composer.wait_for(timeout=5000)
        await composer.click()
        await composer.fill("Make it better.")
        await page.keyboard.press("Meta+Enter")

        # Wait for the agent's text response to appear and stop streaming.
        # Heuristic: poll for the "stop" button to disappear or text containing 'vague'/'target'
        print("waiting for response (max 30s)…")
        try:
            await page.wait_for_selector(
                "text=/vague|target|specific|clarif/i",
                timeout=30000,
                state="visible",
            )
            print("  ✓ saw clarifying response")
        except Exception as e:
            print(f"  ⚠ timeout: {e}")

        await page.wait_for_timeout(1500)
        await page.screenshot(path=OUT, full_page=False)
        print(f"saved → {OUT}")
        await browser.close()


asyncio.run(main())
