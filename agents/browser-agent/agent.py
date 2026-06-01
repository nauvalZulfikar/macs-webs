"""Thin orchestrator: browser-use Agent + security probe + Claude judge."""
import asyncio
import base64
import json
import os
import time
from pathlib import Path
from typing import Any

import yaml
from browser_use import Agent as BUAgent
from browser_use.browser.events import ScreenshotEvent
from browser_use.browser.profile import BrowserProfile
from browser_use.browser.session import BrowserSession
from browser_use.llm import ChatOllama
from rich.console import Console
from rich.panel import Panel

from security import (
    JUDGE_SYSTEM,
    build_judge_prompt,
    run_security_probe,
)


# stderr, not stdout: when this module runs under the MCP stdio server, stdout
# is the JSON-RPC channel. Rich rules/panels on stdout corrupt the protocol
# ("Unrecognized token '─'") and drop the connection. stderr stays visible for
# the CLI path too.
console = Console(stderr=True)


def _load_llm(spec: str):
    """spec format: 'provider:model' (ollama:qwen3:8b, claude:claude-opus-4-7)."""
    provider, _, model = spec.partition(":")
    if provider == "ollama":
        return ChatOllama(model=model, host=os.getenv("OLLAMA_HOST", "http://localhost:11434"))
    if provider == "claude":
        from browser_use.llm import ChatAnthropic
        return ChatAnthropic(model=model)
    raise ValueError(f"unknown llm provider: {spec}")


class Agent:
    def __init__(self, config_path: str = "config.yaml"):
        with open(config_path) as f:
            self.cfg = yaml.safe_load(f)
        self.runs_dir = Path(self.cfg["memory"]["runs_dir"])
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.max_steps = self.cfg["agent"]["max_steps"]

    async def run(
        self,
        goal: str,
        start_url: str | None = None,
        profile: str | None = None,
        security_audit: bool = False,
    ) -> dict[str, Any]:
        run_id = int(time.time())
        run_dir = self.runs_dir / f"run-{run_id}"
        run_dir.mkdir(exist_ok=True)
        console.rule(f"[bold cyan]Run {run_id}[/] — {goal}")

        # LLMs
        main_llm = _load_llm(self.cfg["models"]["main"])
        page_llm = _load_llm(self.cfg["models"].get("page_extraction", self.cfg["models"]["main"]))
        judge_spec = self.cfg["models"].get("judge")
        judge_llm = _load_llm(judge_spec) if (judge_spec and os.getenv("ANTHROPIC_API_KEY")) else None

        # Persistent browser profile
        profile_dir = Path(self.cfg["browser"]["storage_dir"]) / (profile or self.cfg["browser"].get("default_profile", "default"))
        profile_dir.mkdir(parents=True, exist_ok=True)
        bp = BrowserProfile(
            user_data_dir=str(profile_dir),
            headless=self.cfg["browser"].get("headless", False),
            viewport=self.cfg["browser"].get("viewport"),
        )
        session = BrowserSession(browser_profile=bp)

        task = goal if not start_url else f"Open {start_url} then: {goal}"

        bu_agent = BUAgent(
            task=task,
            llm=main_llm,
            page_extraction_llm=page_llm,
            judge_llm=judge_llm,
            use_judge=bool(judge_llm),
            browser_session=session,
            save_conversation_path=str(run_dir / "conversation"),
            max_actions_per_step=self.cfg["agent"].get("max_actions_per_step", 3),
            use_vision=self.cfg["agent"].get("use_vision", False),
            use_thinking=self.cfg["agent"].get("use_thinking", False),
            flash_mode=self.cfg["agent"].get("flash_mode", True),
            enable_planning=self.cfg["agent"].get("enable_planning", False),
            llm_timeout=self.cfg["agent"].get("llm_timeout", 180),
            step_timeout=self.cfg["agent"].get("step_timeout", 300),
            calculate_cost=False,
            generate_gif=False,
        )

        final: dict[str, Any] = {"run_id": run_id, "run_dir": str(run_dir), "status": "incomplete"}

        # Live screenshot loop — runs alongside bu_agent.run() so MACS can
        # surface progress in the chat. Each tick captures the active page to
        # `<run_dir>/screenshot-live.png` (most recent only) + numbered history.
        stop_screenshot = asyncio.Event()
        screenshots_dir = run_dir / "screenshots"
        screenshots_dir.mkdir(exist_ok=True)

        async def _screenshot_loop():
            i = 0
            while not stop_screenshot.is_set():
                try:
                    # browser-use 0.12 drives the browser purely over CDP — there is
                    # no Playwright `page` object. Capture via a ScreenshotEvent on
                    # the session's event bus (ScreenshotWatchdog → Page.captureScreenshot).
                    shot = session.event_bus.dispatch(ScreenshotEvent(full_page=False))
                    await asyncio.wait_for(shot, timeout=10.0)
                    b64 = await shot.event_result()
                    if b64:
                        png = base64.b64decode(b64)
                        # Numbered for replay
                        (screenshots_dir / f"step-{i:04d}.png").write_bytes(png)
                        # Latest pointer
                        (run_dir / "screenshot-latest.png").write_bytes(png)
                        i += 1
                except Exception:
                    pass
                # 3s cadence; each shot is awaited before sleeping so at most one is
                # ever in flight — it can't stack up or flood the event bus.
                try:
                    await asyncio.wait_for(stop_screenshot.wait(), timeout=3.0)
                except asyncio.TimeoutError:
                    pass

        screenshot_task = asyncio.create_task(_screenshot_loop())
        try:
            history = await bu_agent.run(max_steps=self.max_steps)
            final["status"] = "ok" if history.is_done() else "incomplete"
            final["answer"] = history.final_result() or ""
            final["steps_taken"] = len(history.history)
            final["urls_visited"] = history.urls()
            (run_dir / "history.json").write_text(history.model_dump_json(indent=2))

            console.print(Panel(
                final["answer"] or "(no answer)",
                title=f"Answer ({final['steps_taken']} steps)",
                border_style="green" if final["status"] == "ok" else "yellow",
            ))

            if security_audit:
                console.rule("[bold magenta]Security Audit[/]")
                page = await session.get_current_page()
                probe = await run_security_probe(page)
                (run_dir / "security-probe.json").write_text(json.dumps(probe, indent=2))
                final["security_probe"] = probe

                if judge_llm:
                    notes = "\n".join(
                        f"step {i+1}: {h.model_output.action if h.model_output else '?'}"
                        for i, h in enumerate(history.history[:20])
                    )
                    from browser_use.llm.messages import UserMessage, SystemMessage
                    resp = await judge_llm.ainvoke([
                        SystemMessage(content=JUDGE_SYSTEM),
                        UserMessage(content=build_judge_prompt(goal, probe, notes)),
                    ])
                    report = resp.completion if hasattr(resp, "completion") else str(resp)
                    (run_dir / "security-report.md").write_text(report)
                    final["security_report"] = report
                    console.print(Panel(report, title="Security Report", border_style="magenta"))
                else:
                    console.print("[yellow]ANTHROPIC_API_KEY not set — skipping Claude judge[/]")

        except Exception as e:
            final["error"] = str(e)
            console.print(f"[red]agent error:[/] {e}")
        finally:
            stop_screenshot.set()
            try:
                await asyncio.wait_for(screenshot_task, timeout=3.0)
            except Exception:
                screenshot_task.cancel()
            try:
                await session.close()
            except Exception:
                pass

        (run_dir / "result.json").write_text(json.dumps({
            k: v for k, v in final.items() if k != "security_report"
        }, indent=2, default=str))
        return final
