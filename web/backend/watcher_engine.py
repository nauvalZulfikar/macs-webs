"""WatcherEngine: persistent autonomous triggers that spawn chat streams.

Triggers supported:
  - file_change: watchdog FSEvents on given globs/paths
  - cron: croniter spec
  - test_loop: periodic subprocess run, fire on non-zero exit

Each fire calls into the same _spawn_stream() flow used by chat_start so the
agent stream lands in the in-memory registry and the WatcherFire row tracks it.
"""
import asyncio
import json
import os
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    _WATCHDOG = True
except ImportError:
    _WATCHDOG = False

try:
    from croniter import croniter
    _CRONITER = True
except ImportError:
    _CRONITER = False


class _SupervisorState:
    def __init__(self):
        self.task: Optional[asyncio.Task] = None
        self.observer = None
        self.last_fire = 0.0


class WatcherEngine:
    """Singleton; started in FastAPI startup."""

    def __init__(self):
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self._supervisors: dict[int, _SupervisorState] = {}
        self._spawn_cb: Optional[Callable] = None
        self._fire_cb: Optional[Callable] = None
        self._lock = threading.Lock()

    def set_spawn_callback(self, cb: Callable):
        """cb(project_id, prompt, elevated, watcher_id, watcher_fire_id) → stream_id|None.
        Will be called in the asyncio loop."""
        self._spawn_cb = cb

    def set_fire_callback(self, cb: Callable):
        """cb(watcher_id, trigger_info: dict) → fire_id. Synchronous DB write."""
        self._fire_cb = cb

    def start(self, loop: asyncio.AbstractEventLoop, watchers: list):
        self.loop = loop
        for w in watchers:
            if w.enabled:
                self.bind(w)

    def stop(self):
        with self._lock:
            for sup in self._supervisors.values():
                try:
                    if sup.observer:
                        sup.observer.stop()
                except Exception:
                    pass
                if sup.task and not sup.task.done():
                    sup.task.cancel()
            self._supervisors.clear()

    def bind(self, watcher):
        with self._lock:
            self._unbind_unlocked(watcher.id)
            sup = _SupervisorState()
            self._supervisors[watcher.id] = sup
            cfg = json.loads(watcher.trigger_config or "{}")
            project_path = cfg.get("project_path") or ""
            if watcher.trigger_type == "file_change" and _WATCHDOG:
                sup.observer = self._spawn_file_observer(watcher, project_path, cfg)
            elif watcher.trigger_type == "cron" and _CRONITER:
                sup.task = asyncio.run_coroutine_threadsafe(
                    self._cron_loop(watcher, cfg), self.loop
                )
            elif watcher.trigger_type == "test_loop":
                sup.task = asyncio.run_coroutine_threadsafe(
                    self._test_loop(watcher, project_path, cfg), self.loop
                )

    def unbind(self, watcher_id: int):
        with self._lock:
            self._unbind_unlocked(watcher_id)

    def _unbind_unlocked(self, watcher_id: int):
        sup = self._supervisors.pop(watcher_id, None)
        if not sup:
            return
        try:
            if sup.observer:
                sup.observer.stop()
        except Exception:
            pass
        if sup.task:
            try:
                sup.task.cancel()
            except Exception:
                pass

    def _spawn_file_observer(self, watcher, project_path: str, cfg: dict):
        if not _WATCHDOG:
            return None
        paths = cfg.get("paths") or [project_path or "."]
        debounce_s = float(cfg.get("debounce_s", 2.0))
        observer = Observer()
        sup = self._supervisors.get(watcher.id)

        engine = self

        class Handler(FileSystemEventHandler):
            def __init__(self):
                self._timer: Optional[threading.Timer] = None
                self._buffered_paths: list[str] = []

            def _debounced_fire(self):
                with engine._lock:
                    if sup is None or sup.last_fire and (time.time() - sup.last_fire) < 1.0:
                        return
                    if sup is not None:
                        sup.last_fire = time.time()
                paths = list(self._buffered_paths)
                self._buffered_paths = []
                engine._dispatch_fire(
                    watcher, {"trigger": "file_change", "paths": paths[:20]},
                )

            def _trigger(self, ev):
                if ev.is_directory:
                    return
                self._buffered_paths.append(ev.src_path)
                if self._timer:
                    self._timer.cancel()
                self._timer = threading.Timer(debounce_s, self._debounced_fire)
                self._timer.daemon = True
                self._timer.start()

            on_created = _trigger
            on_modified = _trigger
            on_moved = _trigger

        h = Handler()
        for p in paths:
            try:
                pp = Path(p).expanduser().resolve()
                if pp.is_dir():
                    observer.schedule(h, str(pp), recursive=True)
                elif pp.parent.is_dir():
                    observer.schedule(h, str(pp.parent), recursive=False)
            except Exception:
                continue
        observer.daemon = True
        observer.start()
        return observer

    async def _cron_loop(self, watcher, cfg: dict):
        spec = cfg.get("spec", "*/30 * * * *")
        try:
            it = croniter(spec, datetime.utcnow())
        except Exception:
            return
        while True:
            next_t = it.get_next(datetime)
            delay = (next_t - datetime.utcnow()).total_seconds()
            if delay > 0:
                await asyncio.sleep(delay)
            self._dispatch_fire(watcher, {"trigger": "cron", "spec": spec})

    async def _test_loop(self, watcher, project_path: str, cfg: dict):
        cmd = cfg.get("cmd", "")
        interval = int(cfg.get("interval_s", 600))
        if not cmd:
            return
        while True:
            try:
                proc = await asyncio.create_subprocess_shell(
                    cmd,
                    cwd=project_path or None,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await proc.communicate()
                if proc.returncode != 0:
                    self._dispatch_fire(
                        watcher,
                        {
                            "trigger": "test_loop",
                            "cmd": cmd,
                            "exit_code": proc.returncode,
                            "stderr_tail": stderr.decode("utf-8", "replace")[-2000:],
                        },
                    )
            except Exception as e:
                self._dispatch_fire(
                    watcher,
                    {"trigger": "test_loop", "error": str(e)},
                )
            await asyncio.sleep(interval)

    def _dispatch_fire(self, watcher, trigger_info: dict):
        """Bridge from worker thread → asyncio loop for spawn."""
        if not self._spawn_cb or not self.loop:
            return
        fire_id = None
        if self._fire_cb:
            try:
                fire_id = self._fire_cb(watcher.id, trigger_info)
            except Exception:
                pass
        try:
            asyncio.run_coroutine_threadsafe(
                self._spawn_cb(
                    watcher.project_id,
                    self._format_prompt(watcher, trigger_info),
                    watcher.elevated,
                    watcher.id,
                    fire_id,
                ),
                self.loop,
            )
        except Exception:
            pass

    @staticmethod
    def _format_prompt(watcher, trigger_info: dict) -> str:
        prompt = watcher.action_prompt
        ctx = json.dumps(trigger_info, indent=2)[:2000]
        return f"{prompt}\n\n--- triggered by ---\n{ctx}"


engine = WatcherEngine()
