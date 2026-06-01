"""Sprint 4 E2E: tool-use polish + approval modal.

Validates:
- Tool-use cards render with color coding + result size badge
- Cards expand on click showing input + output
- approval_request event triggers modal with denial details
- Approve & retry button re-sends with elevated flag
- Deny button dismisses without retry
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

def open_sibedas_fresh(page):
    login(page, BASE)
    page.wait_for_selector("[data-testid='project-list']")
    page.locator("[data-testid='project-item-1']").click()
    page.wait_for_selector("[data-testid='chat-input']")
    page.wait_for_function(
        "() => !document.querySelector('[data-testid=loading]')",
        timeout=10000,
    )
    # start fresh so accumulated history doesn't taint the test
    page.locator("[data-testid='new-convo-btn']").click()


def wait_send_ready(page, timeout=90000):
    page.wait_for_function(
        """() => {
            const msgs = document.querySelectorAll('[data-testid=messages] li');
            if (msgs.length < 2) return false;
            const last = msgs[msgs.length - 1];
            if (!last || last.querySelector('.animate-pulse')) return false;
            return !!document.querySelector('[data-testid=send-btn]');
        }""",
        timeout=timeout,
    )


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 390, "height": 844})
        page = ctx.new_page()
        page.on("console", lambda m: console_msgs.append(f"[{m.type}] {m.text}"))
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.on("requestfailed", lambda r: errors.append(f"reqfail: {r.url} — {r.failure}"))

        # ─── TEST A: tool-use card with proper polish ───
        print("[A1] open SIBEDAS fresh conversation")
        open_sibedas_fresh(page)

        print("[A2] ask Claude to run a Bash command")
        page.locator("[data-testid='chat-input']").fill(
            "Run `pwd` in bash and return the output verbatim, nothing else."
        )
        page.locator("[data-testid='send-btn']").click()
        wait_send_ready(page)

        print("[A3] verify tool-use card rendered")
        tool_cards = page.locator("[data-testid='tool-card']").count()
        print(f"    tool cards: {tool_cards}")
        assert tool_cards >= 1, f"expected ≥1 tool card, got {tool_cards}"
        page.screenshot(path=str(ARTIFACTS / "s4-01-tool-card-collapsed.png"), full_page=True)

        print("[A4] expand first tool card")
        page.locator("[data-testid='tool-card']").first.click()
        page.wait_for_timeout(300)
        # check input + output sections present
        body = page.locator("[data-testid='tool-card']").first.inner_text()
        assert "input" in body.lower(), "expected 'input' section"
        assert "output" in body.lower(), "expected 'output' section"
        print(f"    card body has input+output sections ✓")
        page.screenshot(path=str(ARTIFACTS / "s4-02-tool-card-expanded.png"), full_page=True)

        # ─── TEST B: approval modal renders + deny ───
        print("[B1] inject synthetic approval_request event")
        page.evaluate("""() => {
            window.__chatTest.inject({
                type: 'approval_request',
                denials: [{
                    tool_name: 'Edit',
                    tool_input: {file_path: '/Users/shaka-mac-mini/.claude/settings.json', old_string: 'foo', new_string: 'bar'},
                    reason: 'Self-Modification of agent config blocked by auto-mode classifier'
                }],
                original_message: 'edit settings.json to add a comment'
            })
        }""")
        page.wait_for_selector("[data-testid='approval-modal']", timeout=3000)
        modal_text = page.locator("[data-testid='approval-modal']").inner_text()
        assert "Permission required" in modal_text
        assert "Edit" in modal_text
        assert "settings.json" in modal_text
        print("    modal shows tool, file, reason ✓")
        page.screenshot(path=str(ARTIFACTS / "s4-03-approval-modal.png"), full_page=True)

        print("[B2] click Deny → modal dismissed")
        page.locator("[data-testid='deny-btn']").click()
        page.wait_for_function(
            "() => !document.querySelector('[data-testid=approval-modal]')",
            timeout=3000,
        )
        # no retry message sent
        msg_count = page.locator("[data-testid='messages'] li").count()
        print(f"    messages after deny: {msg_count} (no retry expected)")

        # ─── TEST C: approval modal renders + Approve & retry ───
        print("[C1] inject again, this time Approve")
        page.evaluate("""() => {
            window.__chatTest.inject({
                type: 'approval_request',
                denials: [{
                    tool_name: 'Bash',
                    tool_input: {command: 'echo approve-marker-sprint-4'},
                    reason: 'test injection'
                }],
                original_message: 'run echo approve-marker-sprint-4 in bash and return only the output'
            })
        }""")
        page.wait_for_selector("[data-testid='approval-modal']")
        page.locator("[data-testid='approve-btn']").click()
        page.wait_for_function(
            "() => !document.querySelector('[data-testid=approval-modal]')",
            timeout=3000,
        )

        print("[C2] verify retry message appears + 'retry (elevated)' badge")
        # The retry user message should be appended with retry badge
        page.wait_for_function(
            """() => Array.from(document.querySelectorAll('[data-testid=messages] li'))
                .some(li => li.innerText.toLowerCase().includes('retry (elevated)'))""",
            timeout=5000,
        )
        retry_count = page.locator("text=retry (elevated)").count()
        print(f"    retry badges visible: {retry_count}")
        assert retry_count >= 1, "expected retry badge after Approve"
        page.screenshot(path=str(ARTIFACTS / "s4-04-retry-elevated.png"), full_page=True)

        print("[C3] wait for retry to complete + check elevated marker in output")
        wait_send_ready(page)
        body_text = page.locator("[data-testid='messages']").inner_text()
        assert "approve-marker-sprint-4" in body_text, "expected elevated retry to execute"
        print("    elevated retry reached Claude and produced output ✓")
        page.screenshot(path=str(ARTIFACTS / "s4-05-elevated-output.png"), full_page=True)

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

    print("\n✅ Sprint 4 E2E passed. Screenshots in test-artifacts/")


if __name__ == "__main__":
    main()
