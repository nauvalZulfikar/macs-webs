"""Subprocess wrapper for `claude -p ...` headless mode with stream-json output.

Idle-timeout + auto-retry behavior:
- IDLE_TIMEOUT (default 60s): kill subprocess if no stdout for that long
- MAX_RETRIES (default 2): on idle timeout, restart claude with --resume <last_session_id_seen>
  and the same user message. Total attempts = MAX_RETRIES + 1.
- A synthetic {"type":"retry","attempt":N,"reason":...} event is yielded between attempts so
  the UI can show the recovery.
"""
import asyncio
import json
import os
import signal
from typing import AsyncIterator, Optional
from pathlib import Path

IDLE_TIMEOUT = int(os.environ.get("CLAUDE_IDLE_TIMEOUT", "60"))
MAX_RETRIES = int(os.environ.get("CLAUDE_MAX_RETRIES", "2"))


async def _run_once(
    cwd: Path,
    message: str,
    session_id: Optional[str],
    elevated: bool,
) -> AsyncIterator[dict]:
    """One subprocess attempt. Yields events. On idle timeout, yields a
    {"type":"_idle_timeout","session_id":<last_seen>} sentinel and returns."""
    cmd = ["claude", "-p", message, "--output-format", "stream-json", "--verbose"]
    if session_id:
        cmd += ["--resume", session_id]
    if elevated:
        cmd += ["--permission-mode", "bypassPermissions"]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        preexec_fn=os.setsid,
    )

    last_seen_session = session_id
    try:
        assert proc.stdout is not None
        while True:
            try:
                raw_line = await asyncio.wait_for(proc.stdout.readline(), timeout=IDLE_TIMEOUT)
            except asyncio.TimeoutError:
                # Kill process group, surface sentinel for retry decision upstream
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                except (ProcessLookupError, PermissionError):
                    pass
                yield {"type": "_idle_timeout", "session_id": last_seen_session}
                return
            if not raw_line:  # EOF
                break
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            try:
                evt = json.loads(line)
            except json.JSONDecodeError:
                evt = {"type": "raw", "text": line}
            sid = evt.get("session_id")
            if sid:
                last_seen_session = sid
            yield evt
    except asyncio.CancelledError:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass
        raise
    finally:
        if proc.returncode is None:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
        try:
            await asyncio.wait_for(proc.wait(), timeout=2)
        except asyncio.TimeoutError:
            pass


async def stream_chat(
    project_path: str,
    message: str,
    session_id: Optional[str] = None,
    elevated: bool = False,
) -> AsyncIterator[dict]:
    """Stream events from `claude -p`. On idle timeout, automatically retries with
    --resume <last_session_id> and the same message, up to MAX_RETRIES times."""
    cwd = Path(project_path).expanduser().resolve()
    if not cwd.is_dir():
        yield {"type": "error", "error": f"Project path not found: {cwd}"}
        return

    current_session = session_id
    attempt = 0
    while True:
        attempt += 1
        idle_hit = False
        async for evt in _run_once(cwd, message, current_session, elevated):
            if evt.get("type") == "_idle_timeout":
                current_session = evt.get("session_id") or current_session
                idle_hit = True
                break
            yield evt

        if not idle_hit:
            return  # normal completion

        if attempt > MAX_RETRIES:
            yield {
                "type": "error",
                "error": f"claude idle {IDLE_TIMEOUT}s × {attempt} attempts — giving up",
            }
            return

        yield {
            "type": "retry",
            "attempt": attempt + 1,
            "max_attempts": MAX_RETRIES + 1,
            "reason": f"idle {IDLE_TIMEOUT}s — restarting with --resume",
            "session_id": current_session,
        }
        # small breather before retry
        await asyncio.sleep(1)
