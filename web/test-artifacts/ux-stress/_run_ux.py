"""UX stress: act as a real user. Fire realistic prompts, observe responses.

Goal: identify where MACS chat agent acts "goblok" — confused, refuses without
reason, ignores instruction, forgets context, asks too much, slow, silent.

NOT a security test. This measures responsiveness + understanding.
"""
import json
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

COOKIE_FILE = "/tmp/macs-claude-cookie.txt"
BASE = "http://100.81.47.91:8101"
PID = 22  # agentic-hell

OUT_DIR = Path("/Users/shaka-mac-mini/coding-projects/macs/web/test-artifacts/ux-stress")
OUT_DIR.mkdir(parents=True, exist_ok=True)


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


def http(path: str, method: str = "GET", body: dict | None = None, timeout: int = 30):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{BASE}{path}", data=data, method=method)
    req.add_header("Cookie", f"pw_session={COOKIE}")
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return r.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"null")


def poll_until_done(stream_id: str, max_s: int = 180) -> tuple[bool, list[dict]]:
    """Poll the stream until done. Return (done?, all_events)."""
    events: list[dict] = []
    from_idx = 0
    deadline = time.time() + max_s
    while time.time() < deadline:
        st, body = http(f"/api/streams/{stream_id}/poll?from={from_idx}")
        if st != 200:
            print(f"  poll {st}: {body}")
            return False, events
        new_events = body.get("events", []) or []
        events.extend(new_events)
        from_idx += len(new_events)
        if body.get("done"):
            return True, events
        time.sleep(2.5)
    return False, events


def analyze_events(events: list[dict]) -> dict:
    tools: list[str] = []
    safety_warns: list[str] = []
    text_chunks: list[str] = []
    result_blocks = 0
    for e in events:
        et = e.get("type")
        if et == "agent_safety_warning":
            safety_warns.append(e.get("category", "?"))
        elif et == "assistant":
            content = e.get("message", {}).get("content", [])
            for b in content:
                bt = b.get("type")
                if bt == "tool_use":
                    tools.append(b.get("name", "?"))
                elif bt == "text":
                    text_chunks.append(b.get("text", ""))
        elif et == "user":
            content = e.get("message", {}).get("content", [])
            for b in content:
                if isinstance(b, dict) and b.get("type") == "tool_result":
                    result_blocks += 1
    full_text = "\n".join(text_chunks).strip()
    asked_q = full_text.rstrip().endswith("?")
    return {
        "tools": tools,
        "tool_count": len(tools),
        "safety_warns": safety_warns,
        "text_snippet": full_text[-600:] if len(full_text) > 600 else full_text,
        "text_chars": len(full_text),
        "asked_q": asked_q,
        "result_blocks": result_blocks,
    }


def fire(name: str, message: str, new_convo: bool = True, log_to: list | None = None) -> dict:
    print(f"\n[{name}] sending: {message[:80]}{'…' if len(message) > 80 else ''}")
    body = {"message": message, "new_conversation": new_convo}
    t0 = time.time()
    st, resp = http(f"/api/projects/{PID}/chat/start", method="POST", body=body, timeout=30)
    if st != 200:
        print(f"  ✗ start failed: {st} {resp}")
        return {"name": name, "error": f"start {st}", "resp": resp}
    sid = resp.get("stream_id")
    if not sid:
        print(f"  ✗ no stream_id: {resp}")
        return {"name": name, "error": "no stream_id", "resp": resp}
    print(f"  stream_id: {sid[:8]}…")
    done, events = poll_until_done(sid)
    elapsed = time.time() - t0
    feat = analyze_events(events)
    out = {
        "name": name,
        "message": message,
        "stream_id": sid,
        "done": done,
        "elapsed_s": round(elapsed, 1),
        "event_count": len(events),
        **feat,
    }
    flag = "✓" if done else "⏱"
    print(f"  {flag} {out['elapsed_s']}s, tools={out['tools']}, text={out['text_chars']}ch, askedQ={out['asked_q']}")
    if out["safety_warns"]:
        print(f"  ⚠ safety_warns: {out['safety_warns']}")
    if log_to is not None:
        log_to.append(out)
    return out


SINGLE_TURN = [
    ("S1_simple_q",      "What files are in this project?"),
    ("S2_edit_task",     "Add a function hello() to src/main.py that prints 'hi'."),
    ("S3_ambiguous",     "Make it better."),
    ("S4_indo",          "Bikin file CONTRIBUTING.md isinya panduan dasar buat contributor."),
    ("S5_ambiguous_this","Why is this not working?"),
    ("S6_safe_delete",   "Delete all .pyc files in this project if any exist."),
    ("S7_infer_intent",  "I want to push to git."),
    ("S8_review_notarg", "Review my last change."),
    ("S9_quick_fact",    "What time is it?"),
    ("S10_run_tests",    "Run the tests."),
]

MULTI_TURN = [
    ("M1_create_util",   "Create a new file src/utils.py with a function double(x) that returns x*2."),
    ("M2_use_it",        "Now import double from utils into src/main.py and call double(5), printing the result."),
    ("M3_context_test",  "Now do the same for the value 7."),
]


def main():
    results: list[dict] = []
    print("=" * 60)
    print("PHASE A — single-turn (each new conversation)")
    print("=" * 60)
    for name, msg in SINGLE_TURN:
        fire(name, msg, new_convo=True, log_to=results)
        time.sleep(2)

    print("\n" + "=" * 60)
    print("PHASE B — multi-turn (one conversation, 3 sequential turns)")
    print("=" * 60)
    first = True
    for name, msg in MULTI_TURN:
        fire(name, msg, new_convo=first, log_to=results)
        first = False
        time.sleep(2)

    out_path = OUT_DIR / "run.json"
    out_path.write_text(json.dumps(results, indent=2))
    print(f"\nsaved → {out_path}")
    print(f"total prompts: {len(results)}")


if __name__ == "__main__":
    main()
