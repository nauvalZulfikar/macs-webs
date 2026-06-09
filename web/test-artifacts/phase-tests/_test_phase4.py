"""Phase 4 smoke test: pick a project WITHOUT .macs/STATE.md, fire a mutating
turn, then verify backend created+appended to .macs/STATE.md."""
import json
import os
import shutil
import time
import urllib.request
from pathlib import Path

COOKIE_FILE = "/tmp/macs-claude-cookie.txt"
BASE = "http://100.81.47.91:8101"
PID = 22  # agentic-hell
PROJECT_PATH = "/Users/shaka-mac-mini/coding-projects/agentic-hell"
STATE_PATH = Path(PROJECT_PATH) / ".macs" / "STATE.md"


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


COOKIE = read_cookie()


def http(path, method="GET", body=None, timeout=30):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{BASE}{path}", data=data, method=method)
    req.add_header("Cookie", f"pw_session={COOKIE}")
    if data:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        return r.status, json.loads(raw) if raw else None


def poll_until_done(stream_id, max_s=180):
    events = []
    from_idx = 0
    deadline = time.time() + max_s
    while time.time() < deadline:
        st, body = http(f"/api/streams/{stream_id}/poll?from={from_idx}")
        new = body.get("events", []) or []
        events.extend(new)
        from_idx += len(new)
        if body.get("done"):
            return True, events
        time.sleep(2.5)
    return False, events


def main():
    # Reset: remove existing STATE.md to test fresh creation
    if STATE_PATH.exists():
        shutil.move(STATE_PATH, str(STATE_PATH) + ".pre-phase4")
        print(f"moved existing STATE.md → STATE.md.pre-phase4")
    else:
        print("no pre-existing STATE.md")

    msg = "Bikin file src/phase4_test.py isinya 'print(\"hello phase4\")'. Replace content if exists."
    print(f"\nfiring: {msg}")
    st, resp = http(f"/api/projects/{PID}/chat/start", method="POST",
                    body={"message": msg, "new_conversation": True}, timeout=30)
    sid = resp["stream_id"]
    print(f"stream: {sid[:8]}")
    done, events = poll_until_done(sid)
    print(f"done={done} events={len(events)}")

    # Pull final agent text
    text = ""
    for e in events:
        if e.get("type") == "assistant":
            for b in (e.get("message", {}) or {}).get("content", []) or []:
                if b.get("type") == "text":
                    text += b.get("text", "") + "\n"

    has_status_block = "STATUS:" in text and ("done:" in text or "Done:" in text.lower())
    print(f"\nSTATUS block in agent reply: {has_status_block}")
    if has_status_block:
        # Print the STATUS block portion
        import re
        m = re.search(r"STATUS:\s*\n(?:.*?\n){2,8}PERSISTED:.*?(?=\n\n|\Z)", text, re.DOTALL)
        if m:
            print("---STATUS BLOCK FROM AGENT---")
            print(m.group(0))
            print("----------------------------")

    # Wait a beat for backend to write STATE.md
    time.sleep(1)

    # Verify STATE.md created + has content
    if STATE_PATH.exists():
        print(f"\n✅ STATE.md EXISTS at {STATE_PATH}")
        content = STATE_PATH.read_text()
        print(f"---STATE.md content (last 800 chars)---")
        print(content[-800:])
        print(f"---end---")
        if "phase4_test.py" in content or "ts:" in content:
            print("✅ PASS — STATE.md has entry from this turn")
        else:
            print("⚠️ STATE.md exists but no recognizable entry")
    else:
        print(f"\n❌ FAIL — STATE.md not created at {STATE_PATH}")


if __name__ == "__main__":
    main()
