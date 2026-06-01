"""Read Claude Code's native session storage (~/.claude/projects/<encoded>/<sid>.jsonl)."""
import json
import os
from pathlib import Path
from typing import List, Optional


PROJECTS_ROOT = Path.home() / ".claude" / "projects"


def encode_path(project_path: str) -> str:
    """/Users/shaka-mac-mini/SIBEDAS → -Users-shaka-mac-mini-SIBEDAS

    NOTE: Claude Code also collapses underscores to dashes when generating
    the on-disk folder name (e.g. `web_ptfl` → `web-ptfl`). Callers should
    use `session_dir()` which probes both variants.
    """
    return project_path.replace("/", "-")


def session_dir(project_path: str) -> Path:
    """Return the directory Claude Code uses for this project's sessions.

    Tries the literal encoding first; falls back to the underscore-collapsed
    variant that Claude Code uses internally."""
    primary = PROJECTS_ROOT / encode_path(project_path)
    if primary.is_dir():
        return primary
    # Claude Code collapses `_` → `-` in the encoded path component
    collapsed = PROJECTS_ROOT / encode_path(project_path).replace("_", "-")
    if collapsed.is_dir():
        return collapsed
    return primary  # may not exist yet; caller handles


def list_sessions(project_path: str) -> List[dict]:
    """List all .jsonl sessions for a project, newest first.

    Each entry: {session_id, first_user_message, last_modified, message_count}
    """
    sdir = session_dir(project_path)
    if not sdir.is_dir():
        return []
    out = []
    for f in sdir.glob("*.jsonl"):
        try:
            stat = f.stat()
            first_user = None
            count = 0
            with f.open("r", encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    try:
                        evt = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    t = evt.get("type")
                    if t in ("user", "assistant"):
                        count += 1
                    if t == "user" and first_user is None:
                        msg = evt.get("message", {})
                        content = msg.get("content")
                        if isinstance(content, str):
                            first_user = content[:200]
                        elif isinstance(content, list):
                            for blk in content:
                                if blk.get("type") == "text":
                                    first_user = blk.get("text", "")[:200]
                                    break
            if first_user is None:
                first_user = "(no user message)"
            out.append({
                "session_id": f.stem,
                "first_user_message": first_user,
                "last_modified": stat.st_mtime,
                "message_count": count,
            })
        except OSError:
            continue
    out.sort(key=lambda x: x["last_modified"], reverse=True)
    return out


def load_session(project_path: str, session_id: str) -> List[dict]:
    """Parse a .jsonl session into chat-ready messages.

    Returns list of {role, text, toolUses, cost, durationMs}.
    """
    sdir = session_dir(project_path)
    f = sdir / f"{session_id}.jsonl"
    if not f.is_file():
        return []

    messages: List[dict] = []
    tool_results: dict = {}  # tool_use_id -> result

    # First pass: collect tool_result content
    with f.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                evt = json.loads(line)
            except json.JSONDecodeError:
                continue
            if evt.get("type") == "user":
                content = evt.get("message", {}).get("content")
                if isinstance(content, list):
                    for blk in content:
                        if blk.get("type") == "tool_result":
                            tid = blk.get("tool_use_id")
                            c = blk.get("content")
                            if isinstance(c, str):
                                tool_results[tid] = c
                            elif isinstance(c, list):
                                tool_results[tid] = "".join(p.get("text", "") for p in c)

    # Second pass: build messages
    with f.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                evt = json.loads(line)
            except json.JSONDecodeError:
                continue
            t = evt.get("type")
            if t == "user":
                content = evt.get("message", {}).get("content")
                if isinstance(content, str):
                    messages.append({"role": "user", "text": content})
                elif isinstance(content, list):
                    # skip if only tool_result (no user-typed text)
                    text_blocks = [b.get("text", "") for b in content if b.get("type") == "text"]
                    if text_blocks:
                        messages.append({"role": "user", "text": "".join(text_blocks)})
            elif t == "assistant":
                msg_content = evt.get("message", {}).get("content", [])
                text = ""
                tool_uses = []
                for blk in msg_content:
                    if blk.get("type") == "text":
                        text += blk.get("text", "")
                    elif blk.get("type") == "tool_use":
                        tool_uses.append({
                            "id": blk.get("id"),
                            "name": blk.get("name"),
                            "input": blk.get("input"),
                            "result": tool_results.get(blk.get("id")),
                        })
                # merge into previous assistant if streaming continuation? For simplicity, append.
                if text or tool_uses:
                    messages.append({
                        "role": "assistant",
                        "text": text,
                        "toolUses": tool_uses,
                    })

    return messages
