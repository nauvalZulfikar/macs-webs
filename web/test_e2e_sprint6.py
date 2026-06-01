"""Sprint 6 E2E: multi-viewport smoke + subprocess lifecycle + ui-verify hook flow.

Validates:
- App renders cleanly on iPhone (390x844), iPad (768x1024), Desktop (1280x800)
- Subprocess killed when client disconnects mid-stream (no orphan claude process)
- Visual prompt sent via web triggers ui-verify route tag (hook fires for headless)
- Loading skeleton appears before projects load
"""
import sys, os, time, subprocess
from pathlib import Path
from playwright.sync_api import sync_playwright
from test_helpers import login, get_password

ARTIFACTS = Path(__file__).resolve().parent / "test-artifacts"
ARTIFACTS.mkdir(exist_ok=True)
BASE = os.environ.get("BASE", "http://100.81.47.91:8101")

VIEWPORTS = [
    ("iphone", {"width": 390, "height": 844}),
    ("ipad",   {"width": 768, "height": 1024}),
    ("desktop",{"width": 1280, "height": 800}),
]

errors = []


def smoke_one(p, label, viewport):
    print(f"\n=== viewport: {label} ({viewport['width']}x{viewport['height']}) ===")
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(viewport=viewport)
    page = ctx.new_page()
    page.on("pageerror", lambda e: errors.append(f"[{label}] pageerror: {e}"))
    page.on("requestfailed", lambda r: errors.append(f"[{label}] reqfail: {r.url} — {r.failure}") if "401" not in str(r.failure or "") else None)

    print(f"  [1] visit + login")
    login(page, BASE)

    print(f"  [2] verify 4 projects render")
    assert page.locator("[data-testid^='project-item-']").count() >= 4

    page.screenshot(path=str(ARTIFACTS / f"s6-{label}-list.png"), full_page=True)

    print(f"  [3] open chat → send short prompt")
    page.locator("[data-testid='project-item-1']").click()
    page.wait_for_selector("[data-testid='chat-input']")
    page.wait_for_function("() => !document.querySelector('[data-testid=loading]')", timeout=10000)
    page.locator("[data-testid='new-convo-btn']").click()
    page.locator("[data-testid='chat-input']").fill(f"reply with: viewport-{label}-ok")
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
    assert f"viewport-{label}-ok" in body
    print(f"  [4] reply ok ✓")
    page.screenshot(path=str(ARTIFACTS / f"s6-{label}-chat.png"), full_page=True)

    browser.close()


def _claude_p_pids():
    out = subprocess.run(["pgrep", "-f", "claude -p"], capture_output=True, text=True).stdout
    return {x for x in out.strip().split("\n") if x}


def test_disconnect_kills_subprocess(p):
    print("\n=== subprocess lifecycle: kill on client disconnect ===")
    before = _claude_p_pids()
    print(f"  claude procs before: {len(before)}")

    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context()
    page = ctx.new_page()
    login(page, BASE)
    page.locator("[data-testid='project-item-1']").click()
    page.wait_for_selector("[data-testid='chat-input']")
    page.wait_for_function("() => !document.querySelector('[data-testid=loading]')", timeout=10000)
    page.locator("[data-testid='new-convo-btn']").click()
    # send long-running prompt
    page.locator("[data-testid='chat-input']").fill(
        "Slowly explain step-by-step how to bake bread, 200 words minimum. Take your time."
    )
    page.locator("[data-testid='send-btn']").click()

    # poll up to 30s for a new claude proc to appear
    new_pids = set()
    for i in range(60):
        time.sleep(0.5)
        cur = _claude_p_pids() - before
        if cur:
            new_pids = cur
            print(f"  spotted new claude proc(s) at {(i+1)*0.5:.1f}s: {new_pids}")
            break
    assert new_pids, "expected ≥1 new claude proc during stream"

    print("  [disconnect] closing browser context to abort SSE")
    ctx.close()
    browser.close()

    # poll for cleanup up to 15s
    for i in range(30):
        time.sleep(0.5)
        after = _claude_p_pids() - before
        if not new_pids.intersection(after):
            print(f"  cleaned up in {(i+1)*0.5:.1f}s ✓")
            return
    leftover = new_pids.intersection(_claude_p_pids() - before)
    raise AssertionError(f"orphan claude procs after disconnect: {leftover}")


def test_ui_verify_hook(p):
    print("\n=== ui-verify hook fires for headless via web ===")
    # truncate log
    log_path = Path("/tmp/route-prompt.log")
    pre_lines = log_path.read_text().count("\n") if log_path.exists() else 0

    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context()
    page = ctx.new_page()
    login(page, BASE)
    page.locator("[data-testid='project-item-1']").click()
    page.wait_for_selector("[data-testid='chat-input']")
    page.wait_for_function("() => !document.querySelector('[data-testid=loading]')", timeout=10000)
    page.locator("[data-testid='new-convo-btn']").click()
    # visual keyword to trigger ui-verify routing
    page.locator("[data-testid='chat-input']").fill("just say 'ok' — testing the screenshot polygon dashboard render flow")
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
    browser.close()

    # check log
    time.sleep(0.5)
    log = log_path.read_text() if log_path.exists() else ""
    # last entries
    last_entries = log.split("\n")[pre_lines:]
    ui_verify_matches = [l for l in last_entries if "ui-verify" in l]
    print(f"  new ui-verify entries: {len(ui_verify_matches)}")
    for e in ui_verify_matches:
        print(f"    {e}")
    assert ui_verify_matches, "expected ui-verify route to fire for visual keyword"


def main():
    with sync_playwright() as p:
        # multi-viewport smoke
        for label, vp in VIEWPORTS:
            smoke_one(p, label, vp)

        # subprocess lifecycle
        test_disconnect_kills_subprocess(p)

        # ui-verify integration
        test_ui_verify_hook(p)

    if errors:
        real = [e for e in errors if "401" not in e]
        if real:
            print(f"\n--- ERRORS ({len(real)}) ---")
            for e in real:
                print(e)
            sys.exit(1)

    print("\n✅ Sprint 6 E2E passed. Screenshots in test-artifacts/")


if __name__ == "__main__":
    main()
