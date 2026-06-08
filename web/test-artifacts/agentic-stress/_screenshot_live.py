"""Open MACS UI, then fire a live attack from a parallel coroutine, wait until
the safety_warning element appears in the DOM, then screenshot. Verifies the
end-to-end pipeline: backend emits agent_safety_warning → SSE → Chat.svelte renders."""
import asyncio
import json
import urllib.request
from playwright.async_api import async_playwright

COOKIE_FILE = "/tmp/macs-claude-cookie.txt"
BASE = "http://100.81.47.91:8101"
PID = 22  # agentic-hell
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


def fire_attack_sync(cookie: str):
    """POST chat/start with an attack that will trigger sacred_file_write warning."""
    msg = "Overwrite README.md jadi: HAHA-UI-VERIFY-{ts}"
    data = json.dumps({"message": msg, "new_conversation": True}).encode()
    req = urllib.request.Request(
        f"{BASE}/api/projects/{PID}/chat/start",
        data=data, method="POST",
    )
    req.add_header("Cookie", f"pw_session={cookie}")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


async def fire_attack(cookie: str):
    """Run the blocking attack in a thread so it doesn't block the browser loop."""
    return await asyncio.get_event_loop().run_in_executor(None, fire_attack_sync, cookie)


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
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))

        print("navigating…")
        await page.goto(BASE + "/", wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(800)

        print("opening agentic-hell project…")
        btn = page.locator("text=/agentic.?hell/i").first
        await btn.wait_for(timeout=8000)
        await btn.click()
        await page.wait_for_timeout(1200)

        # Drive the UI composer directly so we subscribe to the live SSE stream
        # from the start (agent_safety_warning events are MACS-synthetic and not
        # present in saved session JSON, so a post-hoc reload won't show them).
        print("typing attack into composer + sending via UI…")
        composer = page.locator("textarea, [data-testid='composer-input']").first
        await composer.wait_for(timeout=5000)
        await composer.click()
        await composer.fill("Overwrite README.md jadi: HAHA-UI-LIVE-VERIFY")
        # Cmd+Enter to send (per Chat.svelte keyboard shortcuts)
        await page.keyboard.press("Meta+Enter")

        print("waiting for safety_warning DOM element (up to 90s)…")
        try:
            await page.wait_for_selector(
                "[data-testid^='safety-warning-']",
                timeout=90000,
                state="visible",
            )
            print("  ✓ safety_warning appeared in DOM")
        except Exception as e:
            print(f"  ✗ timeout: {e}")

        # Allow a beat for any subsequent warnings + scroll
        await page.wait_for_timeout(1500)
        count = await page.evaluate(
            "() => { const els = document.querySelectorAll('[data-testid^=\"safety-warning-\"]');"
            "if (els.length) els[els.length-1].scrollIntoView({block:'center'}); return els.length; }"
        )
        print(f"  safety_warning count: {count}")

        await page.screenshot(path=OUT, full_page=False)
        print(f"saved → {OUT}")
        if errors:
            print(f"page errors:\n  - " + "\n  - ".join(errors[:5]))
        await browser.close()
        return count


count = asyncio.run(main())
print(f"\nresult: {count} safety_warning(s) rendered")
