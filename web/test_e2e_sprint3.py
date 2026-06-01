"""Sprint 3 E2E: session continuity + history sidebar.

Validates:
- Active session pre-loads on chat mount
- History drawer lists past sessions
- Click old session loads its messages
- New conversation button creates fresh session_id
"""
import sys
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
        ctx = browser.new_context(viewport={"width": 390, "height": 844})
        page = ctx.new_page()

        page.on("console", lambda m: console_msgs.append(f"[{m.type}] {m.text}"))
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.on("requestfailed", lambda r: errors.append(f"reqfail: {r.url} — {r.failure}"))

        print(f"[1] navigate {BASE} + login")
        login(page, BASE)

        print("[2] open SIBEDAS (active session should auto-load)")
        page.wait_for_selector("[data-testid='project-list']")
        page.locator("[data-testid='project-item-1']").click()
        page.wait_for_selector("[data-testid='chat-input']")
        # Wait for messages to load OR loading state to clear
        page.wait_for_function(
            "() => !document.querySelector('[data-testid=loading]')",
            timeout=10000,
        )

        # Should see at least the previous "pong" conversation auto-loaded
        prev_msg_count = page.locator("[data-testid='messages'] li").count()
        print(f"    auto-loaded {prev_msg_count} prior messages")
        assert prev_msg_count >= 2, f"expected previous messages auto-loaded, got {prev_msg_count}"
        page.screenshot(path=str(ARTIFACTS / "s3-01-resumed-chat.png"), full_page=True)

        print("[3] open History drawer")
        page.locator("[data-testid='history-btn']").click()
        page.wait_for_selector("[data-testid='history-drawer']")
        # wait for sessions list to load
        page.wait_for_function(
            "() => document.querySelectorAll('[data-testid^=session-item-]').length > 0",
            timeout=10000,
        )
        sessions = page.locator("[data-testid^='session-item-']").count()
        print(f"    history shows {sessions} session(s)")
        assert sessions >= 1, "expected at least 1 history entry"
        page.screenshot(path=str(ARTIFACTS / "s3-02-history-open.png"), full_page=True)

        print("[4] close drawer, click 'New' for fresh session")
        # close drawer
        page.locator("[data-testid='history-overlay']").click(position={"x": 10, "y": 100})
        page.wait_for_function(
            "() => !document.querySelector('[data-testid=history-drawer]')",
            timeout=3000,
        )
        page.locator("[data-testid='new-convo-btn']").click()
        # messages should be cleared, 'new' badge visible
        cleared_count = page.locator("[data-testid='messages'] li").count()
        assert cleared_count == 0, f"expected 0 messages after new, got {cleared_count}"
        new_badge = page.locator("text=new").count()
        print(f"    cleared: {cleared_count} msgs, new badge: {new_badge}")
        page.screenshot(path=str(ARTIFACTS / "s3-03-new-convo.png"), full_page=True)

        print("[5] send fresh message → creates new session_id")
        page.locator("[data-testid='chat-input']").fill("reply with: marker-sprint-3")
        page.locator("[data-testid='send-btn']").click()
        page.wait_for_function(
            """() => {
                const msgs = document.querySelectorAll('[data-testid=messages] li');
                if (msgs.length < 2) return false;
                const last = msgs[msgs.length - 1];
                if (!last || last.querySelector('.animate-pulse')) return false;
                // also wait for pending=false (Send button visible, not Stop)
                return !!document.querySelector('[data-testid=send-btn]');
            }""",
            timeout=90000,
        )
        last_text = page.locator("[data-testid='messages'] li").last.inner_text()
        print(f"    reply: {last_text[:80]!r}")
        assert "marker-sprint-3" in last_text, f"missing marker in reply: {last_text!r}"
        page.screenshot(path=str(ARTIFACTS / "s3-04-fresh-reply.png"), full_page=True)

        print("[6] re-open History → should now have 2 sessions")
        page.locator("[data-testid='history-btn']").click()
        page.wait_for_selector("[data-testid='history-drawer']")
        page.wait_for_function(
            "() => document.querySelectorAll('[data-testid^=session-item-]').length >= 2",
            timeout=10000,
        )
        new_count = page.locator("[data-testid^='session-item-']").count()
        print(f"    history now: {new_count} sessions")
        assert new_count >= 2, f"expected ≥2 sessions, got {new_count}"
        page.screenshot(path=str(ARTIFACTS / "s3-05-history-2-sessions.png"), full_page=True)

        print("[7] click the OLDER session (the 'pong' one)")
        # find session whose first_user_message is the pong prompt — not by index (sessions accumulate across runs)
        target = page.locator("[data-testid^='session-item-']").filter(has_text="say only the word pong").first
        target_count = target.count()
        print(f"    target session matches: {target_count}")
        page.screenshot(path=str(ARTIFACTS / "s3-06a-pre-click.png"), full_page=True)
        target.click()
        # wait for messages to switch
        page.wait_for_function(
            """() => {
                const msgs = document.querySelectorAll('[data-testid=messages] li');
                return msgs.length >= 4;
            }""",
            timeout=15000,
        )
        msg_count = page.locator("[data-testid='messages'] li").count()
        print(f"    loaded older session: {msg_count} messages")
        assert msg_count >= 4, f"expected old session restored, got {msg_count}"
        body_text = page.locator("[data-testid='messages']").inner_text()
        assert "pong" in body_text.lower(), "expected 'pong' in restored session"
        page.screenshot(path=str(ARTIFACTS / "s3-06-switched-back.png"), full_page=True)

        browser.close()

    if errors:
        print(f"\n--- ERRORS ({len(errors)}) ---")
        for e in errors:
            print(e)
        sys.exit(1)

    suspicious = [m for m in console_msgs if m.startswith("[error]")]
    if suspicious:
        print(f"\n--- CONSOLE ERRORS ({len(suspicious)}) ---")
        for m in suspicious:
            print(m)
        sys.exit(1)

    print("\n✅ Sprint 3 E2E passed. Screenshots in test-artifacts/")

if __name__ == "__main__":
    main()
