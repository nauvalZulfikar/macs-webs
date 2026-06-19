"""Read Claude Code's native session storage (~/.claude/projects/<encoded>/<sid>.jsonl)."""
import json
import os
import re
from pathlib import Path
from typing import Dict, List, Optional


PROJECTS_ROOT = Path.home() / ".claude" / "projects"

# Strip MACS-injected preamble blocks from user messages before returning to UI.
# Backend wraps every user message with <safety>...</safety><responsiveness>...
# </responsiveness><system-context>...</system-context> + the real user text.
# The UI should display only the real user text — not policy wrappers.
_PREAMBLE_STRIP = re.compile(
    r"^\s*(?:<safety>.*?</safety>\s*"
    r"|<responsiveness>.*?</responsiveness>\s*"
    r"|<state-contract>.*?</state-contract>\s*"
    r"|<system-context>.*?</system-context>\s*)+",
    re.DOTALL | re.IGNORECASE,
)


def strip_injected_preamble(text: str) -> str:
    """Remove MACS-injected <safety>/<responsiveness>/<system-context> wrappers."""
    if not text:
        return text
    return _PREAMBLE_STRIP.sub("", text).lstrip()


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
                        raw = None
                        if isinstance(content, str):
                            raw = content
                        elif isinstance(content, list):
                            for blk in content:
                                if blk.get("type") == "text":
                                    raw = blk.get("text", "")
                                    break
                        if raw is not None:
                            first_user = strip_injected_preamble(raw)[:200]
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
                    messages.append({"role": "user", "text": strip_injected_preamble(content)})
                elif isinstance(content, list):
                    # skip if only tool_result (no user-typed text)
                    text_blocks = [b.get("text", "") for b in content if b.get("type") == "text"]
                    if text_blocks:
                        messages.append({"role": "user", "text": strip_injected_preamble("".join(text_blocks))})
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


# Valid Claude Code session ids are uuids; restrict to a safe charset so a
# crafted session_id can't escape the session dir via path traversal.
_SAFE_SID = re.compile(r"^[A-Za-z0-9._-]+$")


# Match `Task #171 created successfully` (or just `Task #171`) in tool_result text
_TASK_ID_RE = re.compile(r"Task #(\d+)")


def session_stats(project_path: str, session_id: str) -> dict:
    """Aggregate token usage + reconstruct current plan (TaskCreate/TaskUpdate)
    from a Claude Code JSONL transcript.

    Returns:
        {
          "session_id": str,
          "tokens": {
              "input": int,            # input_tokens summed
              "cache_creation": int,   # cache_creation_input_tokens summed
              "cache_read": int,       # cache_read_input_tokens summed
              "output": int,           # output_tokens summed
              "total": int,            # sum of all 4
              "message_count": int,    # assistant messages with usage info
          },
          "plan": {
              "tasks": [{"id","subject","status","ts"}],
              "counts": {"pending","in_progress","completed","total"},
          },
          "last_activity_ts": str|None,
        }

    Returns zero/empty values if session file does not exist."""
    if not session_id or not _SAFE_SID.match(session_id):
        return _empty_stats(session_id)

    sdir = session_dir(project_path)
    f = (sdir / f"{session_id}.jsonl").resolve()
    if f.parent != sdir.resolve() or not f.is_file():
        return _empty_stats(session_id)

    tok_in = tok_co = tok_cr = tok_out = 0
    msg_count = 0
    last_ts = None

    # tool_use_id -> tool_use input + name (for matching with tool_result later)
    pending_tool_uses: Dict[str, dict] = {}  # tuid -> {"name","input"}
    task_state: Dict[str, dict] = {}  # task_id -> {id, subject, status, ts}

    try:
        with f.open("r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    evt = json.loads(line)
                except json.JSONDecodeError:
                    continue

                ts = evt.get("timestamp")
                if ts:
                    last_ts = ts

                msg = evt.get("message") or {}

                # Token usage (assistant messages with `usage` field)
                usage = msg.get("usage")
                if isinstance(usage, dict):
                    try:
                        tok_in += int(usage.get("input_tokens") or 0)
                        tok_co += int(usage.get("cache_creation_input_tokens") or 0)
                        tok_cr += int(usage.get("cache_read_input_tokens") or 0)
                        tok_out += int(usage.get("output_tokens") or 0)
                        msg_count += 1
                    except (TypeError, ValueError):
                        pass

                content = msg.get("content")
                if not isinstance(content, list):
                    continue

                for blk in content:
                    if not isinstance(blk, dict):
                        continue
                    btype = blk.get("type")
                    if btype == "tool_use":
                        tuid = blk.get("id")
                        name = blk.get("name")
                        if tuid and name in ("TaskCreate", "TaskUpdate"):
                            pending_tool_uses[tuid] = {
                                "name": name,
                                "input": blk.get("input") or {},
                                "ts": ts,
                            }
                    elif btype == "tool_result":
                        tuid = blk.get("tool_use_id")
                        if not tuid or tuid not in pending_tool_uses:
                            continue
                        call = pending_tool_uses.pop(tuid)
                        result_text = ""
                        rc = blk.get("content")
                        if isinstance(rc, str):
                            result_text = rc
                        elif isinstance(rc, list):
                            result_text = "".join(p.get("text", "") for p in rc if isinstance(p, dict))

                        if call["name"] == "TaskCreate":
                            m = _TASK_ID_RE.search(result_text)
                            if m:
                                tid = m.group(1)
                                inp = call["input"]
                                task_state[tid] = {
                                    "id": tid,
                                    "subject": (inp.get("subject") or "").strip() or "(untitled)",
                                    "status": "pending",
                                    "ts": call["ts"],
                                }
                        elif call["name"] == "TaskUpdate":
                            inp = call["input"]
                            tid = inp.get("taskId")
                            if tid and tid in task_state:
                                if "status" in inp and inp["status"]:
                                    task_state[tid]["status"] = inp["status"]
                                if inp.get("subject"):
                                    task_state[tid]["subject"] = inp["subject"]
                                task_state[tid]["ts"] = call["ts"] or task_state[tid].get("ts")
    except OSError:
        return _empty_stats(session_id)

    # Order tasks by numeric id (created order)
    def _sortkey(t):
        try:
            return int(t["id"])
        except (TypeError, ValueError):
            return 0

    tasks_sorted = sorted(task_state.values(), key=_sortkey)
    # Drop tasks that have been deleted
    tasks_visible = [t for t in tasks_sorted if t.get("status") != "deleted"]

    counts = {"pending": 0, "in_progress": 0, "completed": 0, "total": len(tasks_visible)}
    for t in tasks_visible:
        s = t.get("status")
        if s in counts:
            counts[s] += 1

    return {
        "session_id": session_id,
        "tokens": {
            "input": tok_in,
            "cache_creation": tok_co,
            "cache_read": tok_cr,
            "output": tok_out,
            "total": tok_in + tok_co + tok_cr + tok_out,
            "message_count": msg_count,
        },
        "plan": {
            "tasks": tasks_visible,
            "counts": counts,
        },
        "last_activity_ts": last_ts,
    }


def _empty_stats(session_id: Optional[str]) -> dict:
    return {
        "session_id": session_id,
        "tokens": {
            "input": 0,
            "cache_creation": 0,
            "cache_read": 0,
            "output": 0,
            "total": 0,
            "message_count": 0,
        },
        "plan": {
            "tasks": [],
            "counts": {"pending": 0, "in_progress": 0, "completed": 0, "total": 0},
        },
        "last_activity_ts": None,
    }


def get_chat_count(project_path: str) -> int:
    """Return count of .md files directly inside {project_path}/.macs/chats/.

    Returns 0 if the directory doesn't exist, is empty, the project_path
    is invalid (None/non-str), or a parent path component is inaccessible.
    Symlinks with a .md extension count; subdirectories are not recursed.
    """
    try:
        chats_dir = Path(project_path) / ".macs" / "chats"
    except TypeError:
        return 0
    try:
        if not chats_dir.is_dir():
            return 0
        return sum(
            1 for p in chats_dir.iterdir() if p.suffix == ".md" and p.is_file()
        )
    except OSError:
        return 0


def get_chat_total_bytes(project_path: str) -> int:
    """Return total bytes of all .md files directly inside {project_path}/.macs/chats/.

    Returns 0 if the directory does not exist, is empty, or has no .md files.
    Symlinks are followed (target size used); subdirectories are not recursed.
    """
    chats_dir = Path(project_path) / ".macs" / "chats"
    if not chats_dir.is_dir():
        return 0
    return sum(
        p.stat().st_size
        for p in chats_dir.iterdir()
        if p.suffix == ".md" and p.is_file()
    )


def delete_session(project_path: str, session_id: str) -> bool:
    """Delete a project's `.jsonl` session file. Returns True if removed.

    Rejects session_ids containing path separators / traversal, and verifies
    the resolved file actually sits inside the project's session dir."""
    if not session_id or not _SAFE_SID.match(session_id):
        return False
    sdir = session_dir(project_path)
    f = (sdir / f"{session_id}.jsonl").resolve()
    # Defense-in-depth: file must live directly under the session dir.
    if f.parent != sdir.resolve() or not f.is_file():
        return False
    try:
        f.unlink()
        return True
    except OSError:
        return False
