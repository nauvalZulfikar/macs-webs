"""Index + serve browser-agent runs (history.json based — that's what's actually
captured per run, not screenshots)."""
import json
import time
from pathlib import Path
from typing import Optional, List

RUNS_DIR = Path(
    "/Users/shaka-mac-mini/coding-projects/macs/agents/browser-agent/runs"
)


def list_recent_runs(since_epoch: Optional[float] = None) -> List[dict]:
    if not RUNS_DIR.is_dir():
        return []
    out = []
    for d in RUNS_DIR.iterdir():
        if not d.is_dir():
            continue
        try:
            st = d.stat()
        except OSError:
            continue
        if since_epoch and st.st_mtime < since_epoch:
            continue
        h = d / "history.json"
        r = d / "result.json"
        if not h.exists() and not r.exists():
            continue
        out.append({
            "run_id": d.name,
            "mtime": st.st_mtime,
            "has_history": h.exists(),
            "has_result": r.exists(),
        })
    out.sort(key=lambda x: x["mtime"], reverse=True)
    return out


def list_screenshots(run_id: str) -> list[dict]:
    d = RUNS_DIR / run_id / "screenshots"
    if not d.is_dir():
        return []
    out = []
    for p in sorted(d.iterdir()):
        if p.suffix.lower() != ".png":
            continue
        try:
            st = p.stat()
            out.append({"filename": p.name, "mtime": st.st_mtime, "size": st.st_size})
        except OSError:
            continue
    return out


def screenshot_path(run_id: str, filename: str) -> Optional[Path]:
    if ".." in filename or "/" in filename:
        return None
    p = RUNS_DIR / run_id / "screenshots" / filename
    if not p.is_file():
        # Fallback: top-level latest
        if filename == "screenshot-latest.png":
            alt = RUNS_DIR / run_id / "screenshot-latest.png"
            if alt.is_file():
                return alt
        return None
    return p


def latest_screenshot_path(run_id: str) -> Optional[Path]:
    """Return the most recent screenshot in the run dir."""
    p = RUNS_DIR / run_id / "screenshot-latest.png"
    if p.is_file():
        return p
    d = RUNS_DIR / run_id / "screenshots"
    if d.is_dir():
        latest = None
        for f in d.iterdir():
            if f.suffix.lower() != ".png":
                continue
            if latest is None or f.stat().st_mtime > latest.stat().st_mtime:
                latest = f
        return latest
    return None


def run_manifest(run_id: str) -> Optional[dict]:
    d = RUNS_DIR / run_id
    if not d.is_dir():
        return None
    history_path = d / "history.json"
    result_path = d / "result.json"
    steps = []
    last_action = None
    current_url = None
    screenshots = list_screenshots(run_id)
    latest_screenshot = (
        f"/api/browser-runs/{run_id}/screenshot/screenshot-latest.png"
        if (d / "screenshot-latest.png").is_file()
        else (f"/api/browser-runs/{run_id}/screenshot/{screenshots[-1]['filename']}" if screenshots else None)
    )
    if history_path.exists():
        try:
            data = json.loads(history_path.read_text())
            raw_steps = data.get("history", [])
            for i, st in enumerate(raw_steps):
                mo = st.get("model_output", {}) or {}
                action = mo.get("action") or []
                action_str = ""
                if isinstance(action, list) and action:
                    first = action[0]
                    if isinstance(first, dict):
                        keys = [k for k in first.keys() if first[k] is not None] or list(first.keys())
                        if keys:
                            action_str = keys[0]
                            v = first.get(action_str)
                            if isinstance(v, dict):
                                summary = next(
                                    (str(v[k])[:80] for k in ("url", "text", "selector", "index") if k in v),
                                    "",
                                )
                                if summary:
                                    action_str = f"{action_str}({summary})"
                last_action = action_str or last_action
                results = st.get("result") or []
                content = ""
                for r in results:
                    if isinstance(r, dict):
                        c = r.get("extracted_content") or ""
                        if c:
                            content = c[:200]
                            if "Navigated to " in c or "Navigate to " in c:
                                # Try to capture url
                                import re
                                m = re.search(r"https?://\S+", c)
                                if m:
                                    current_url = m.group(0)
                            break
                steps.append({
                    "index": i,
                    "memory": (mo.get("memory") or "")[:140],
                    "next_goal": (mo.get("next_goal") or "")[:140],
                    "action": action_str,
                    "extracted": content,
                })
        except Exception as e:
            steps = []
    final = {}
    if result_path.exists():
        try:
            final = json.loads(result_path.read_text())
        except Exception:
            final = {}
    return {
        "run_id": run_id,
        "steps": steps,
        "current_url": current_url or (final.get("urls_visited") or [None])[-1],
        "last_action": last_action,
        "status": final.get("status", "running" if not result_path.exists() else "done"),
        "answer": final.get("answer", ""),
        "steps_taken": final.get("steps_taken", len(steps)),
        "screenshots": screenshots,
        "latest_screenshot": latest_screenshot,
    }
