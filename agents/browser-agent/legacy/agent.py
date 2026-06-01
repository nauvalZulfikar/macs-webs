"""Main orchestrator — perception → planner → executor loop."""
import asyncio
import time
from pathlib import Path
from typing import Any

import yaml
from rich.console import Console
from rich.panel import Panel

from executor import BrowserSession
from memory import Memory
from models import ModelRouter
import perception
import planner


console = Console()


class Agent:
    def __init__(self, config_path: str = "config.yaml"):
        with open(config_path) as f:
            self.cfg = yaml.safe_load(f)
        self.router = ModelRouter(self.cfg["models"])
        self.memory = Memory(self.cfg["memory"]["db_path"])
        self.runs_dir = Path(self.cfg["memory"]["runs_dir"])
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.max_steps = self.cfg["agent"]["max_steps"]
        self.shot_each_step = self.cfg["agent"]["screenshot_on_step"]

    async def run(
        self,
        goal: str,
        start_url: str | None = None,
        profile: str | None = None,
        security_audit: bool = False,
    ) -> dict[str, Any]:
        run_id = self.memory.start_run(goal)
        run_dir = self.runs_dir / f"run-{run_id:05d}"
        run_dir.mkdir(exist_ok=True)
        console.rule(f"[bold cyan]Run #{run_id}[/] — {goal}")

        sess = BrowserSession(self.cfg, profile=profile)
        await sess.start()
        history: list[dict[str, Any]] = []
        final: dict[str, Any] = {"status": "incomplete", "answer": None, "run_id": run_id, "run_dir": str(run_dir)}

        try:
            if start_url:
                r = await sess.goto(start_url)
                history.append({"idx": 0, "action": "goto", "args": {"url": start_url}, "result": r})
                self.memory.log_step(run_id, 0, start_url, "goto", {"url": start_url}, r, model=None)

            for step in range(1, self.max_steps + 1):
                snap = await perception.snapshot(sess.page)
                snap_text = perception.format_snapshot_for_llm(snap)
                shot_path = None
                if self.shot_each_step:
                    shot_path = str(run_dir / f"step-{step:02d}.png")
                    await sess.screenshot(shot_path)

                try:
                    plan, tier = await planner.next_action(
                        self.router, goal, snap_text, history,
                    )
                except Exception as e:
                    console.print(f"[red]planner error:[/] {e}")
                    final["error"] = str(e)
                    break

                action = plan.get("action", "")
                args = plan.get("args", {}) or {}
                console.print(Panel.fit(
                    f"[bold]step {step}[/] ({tier}) [yellow]{action}[/] {args}\n[dim]{plan.get('thought','')}[/dim]",
                    border_style="cyan",
                ))

                if action == "finish":
                    final["status"] = "ok"
                    final["answer"] = args.get("answer", "")
                    history.append({"idx": step, "action": action, "args": args, "result": {"ok": True}})
                    self.memory.log_step(run_id, step, snap["url"], action, args, {"answer": final["answer"]}, model=tier)
                    break

                if action == "screenshot":
                    args.setdefault("path", str(run_dir / f"manual-{step:02d}.png"))

                result = await sess.dispatch(action, args)
                history.append({"idx": step, "action": action, "args": args, "result": result})
                self.memory.log_step(run_id, step, snap["url"], action, args, result, model=tier)

                if not result.get("ok"):
                    console.print(f"[yellow]action failed:[/] {result.get('error')}")

            else:
                console.print(f"[yellow]max_steps reached ({self.max_steps}) — stopping[/]")

            if security_audit:
                probe = await perception.security_probe(sess.page)
                console.rule("[bold magenta]Security Audit[/]")
                notes = "\n".join(
                    f"step {h['idx']}: {h['action']} {h.get('args',{})} -> {h.get('result',{}).get('ok')}"
                    for h in history
                )
                report = self.router.call(
                    tier="judge",
                    system=planner.JUDGE_SYSTEM,
                    user=planner.judge_prompt(goal, probe, notes),
                )
                console.print(Panel(report, title="Security Report", border_style="magenta"))
                (run_dir / "security-report.md").write_text(report)
                (run_dir / "security-probe.json").write_text(__import__("json").dumps(probe, indent=2))
                final["security_report"] = report
                final["security_probe"] = probe

            # Save network log
            (run_dir / "network.json").write_text(
                __import__("json").dumps(sess.network_log[-200:], indent=2)
            )

        finally:
            await sess.stop()
            self.memory.end_run(run_id, final["status"], final.get("answer"))
            self.memory.close()

        console.rule(f"[bold green]Done[/] — {final['status']}")
        if final.get("answer"):
            console.print(Panel(final["answer"], title="Answer", border_style="green"))
        return final


async def _amain(args):
    agent = Agent(args.config)
    await agent.run(
        goal=args.goal,
        start_url=args.url,
        profile=args.profile,
        security_audit=args.security,
    )
