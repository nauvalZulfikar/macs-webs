"""Executor: turns planner actions into Playwright operations."""
import fnmatch
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from playwright.async_api import Page, async_playwright, BrowserContext


class BrowserSession:
    def __init__(self, cfg: dict[str, Any], profile: str | None = None):
        self.cfg = cfg["browser"]
        self.safety = cfg.get("safety", {})
        self.profile = profile or self.cfg.get("default_profile", "default")
        self.storage_dir = Path(self.cfg["storage_dir"]) / self.profile
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._pw = None
        self._ctx: BrowserContext | None = None
        self.page: Page | None = None
        self.network_log: list[dict[str, Any]] = []

    async def start(self):
        self._pw = await async_playwright().start()
        self._ctx = await self._pw.chromium.launch_persistent_context(
            user_data_dir=str(self.storage_dir),
            headless=self.cfg.get("headless", False),
            viewport=self.cfg.get("viewport"),
            user_agent=self.cfg.get("user_agent"),
        )
        self.page = self._ctx.pages[0] if self._ctx.pages else await self._ctx.new_page()
        self.page.on("response", self._on_response)

    async def stop(self):
        if self._ctx:
            await self._ctx.close()
        if self._pw:
            await self._pw.stop()

    def _on_response(self, response):
        try:
            self.network_log.append({
                "url": response.url,
                "status": response.status,
                "type": response.request.resource_type,
                "method": response.request.method,
            })
            if len(self.network_log) > 500:
                self.network_log = self.network_log[-300:]
        except Exception:
            pass

    def _domain_blocked(self, url: str) -> bool:
        host = urlparse(url).hostname or ""
        for pat in self.safety.get("block_domains", []):
            if fnmatch.fnmatch(host, pat):
                return True
        allow = self.safety.get("allow_domains") or []
        if allow and not any(fnmatch.fnmatch(host, p) for p in allow):
            return True
        return False

    # --- actions ----------------------------------------------------------
    async def goto(self, url: str) -> dict[str, Any]:
        if self._domain_blocked(url):
            return {"ok": False, "error": f"domain blocked: {url}"}
        try:
            resp = await self.page.goto(url, wait_until="domcontentloaded", timeout=20000)
            return {"ok": True, "status": resp.status if resp else None}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    async def click(self, ref: str) -> dict[str, Any]:
        try:
            await self.page.click(f'[data-agent-ref="{ref}"]', timeout=8000)
            await self.page.wait_for_load_state("domcontentloaded", timeout=10000)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    async def fill(self, ref: str, text: str) -> dict[str, Any]:
        try:
            await self.page.fill(f'[data-agent-ref="{ref}"]', text, timeout=8000)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    async def press(self, key: str) -> dict[str, Any]:
        try:
            await self.page.keyboard.press(key)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    async def scroll(self, dy: int = 600) -> dict[str, Any]:
        await self.page.mouse.wheel(0, dy)
        return {"ok": True}

    async def wait(self, seconds: float) -> dict[str, Any]:
        await self.page.wait_for_timeout(int(seconds * 1000))
        return {"ok": True}

    async def screenshot(self, path: str) -> dict[str, Any]:
        await self.page.screenshot(path=path, full_page=False)
        return {"ok": True, "path": path}

    async def extract_text(self, selector: str | None = None) -> dict[str, Any]:
        try:
            if selector:
                el = await self.page.query_selector(selector)
                text = await el.inner_text() if el else ""
            else:
                text = await self.page.inner_text("body")
            return {"ok": True, "text": text[:8000]}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    async def dispatch(self, action: str, args: dict[str, Any]) -> dict[str, Any]:
        fn = {
            "goto": lambda: self.goto(args["url"]),
            "click": lambda: self.click(args["ref"]),
            "fill": lambda: self.fill(args["ref"], args["text"]),
            "press": lambda: self.press(args["key"]),
            "scroll": lambda: self.scroll(args.get("dy", 600)),
            "wait": lambda: self.wait(args.get("seconds", 1.0)),
            "screenshot": lambda: self.screenshot(args["path"]),
            "extract_text": lambda: self.extract_text(args.get("selector")),
        }.get(action)
        if not fn:
            return {"ok": False, "error": f"unknown action: {action}"}
        return await fn()
