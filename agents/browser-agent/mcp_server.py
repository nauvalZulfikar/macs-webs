"""MCP server exposing the browser-agent (browser-use engine) as tools.

Tools:
  - browse_autonomous: drive a browser toward a natural-language goal
  - analyze_login_security: passive security audit of a login/auth page
  - extract_page_data: navigate then return page text + security probe
  - list_runs: list recent run directories
"""
import asyncio
import json
import sys
from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

sys.path.insert(0, str(Path(__file__).parent))

from agent import Agent


CONFIG_PATH = str(Path(__file__).parent / "config.yaml")
RUNS_DIR = Path(__file__).parent / "runs"
app = Server("browser-agent")


@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="browse_autonomous",
            description=(
                "Drive a real browser autonomously toward a natural-language goal "
                "(click, fill forms, login, scroll, multi-step). Engine: browser-use + "
                "local Ollama (qwen3:8b). Persistent profiles keep cookies/sessions. "
                "Use when the task needs JS-rendered content, post-login state, or "
                "multi-step interaction. Returns final answer + run_id."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "goal": {"type": "string", "description": "What to accomplish in natural language."},
                    "start_url": {"type": "string", "description": "Optional starting URL."},
                    "profile": {"type": "string", "description": "Browser profile name (persistent cookies). Default: 'default'."},
                },
                "required": ["goal"],
            },
        ),
        Tool(
            name="analyze_login_security",
            description=(
                "Passive security audit of a login/auth page. Probes forms, CSRF tokens, "
                "CAPTCHA, autocomplete, external scripts, mixed content, CSP. "
                "Returns structured probe + (if ANTHROPIC_API_KEY) a Claude risk report. "
                "Read-only — does not submit credentials."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Login page URL."},
                    "profile": {"type": "string", "description": "Browser profile (optional)."},
                },
                "required": ["url"],
            },
        ),
        Tool(
            name="extract_page_data",
            description=(
                "Navigate to a URL and return page content + security probe. "
                "Lightweight scrape — no autonomous reasoning loop."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "profile": {"type": "string"},
                },
                "required": ["url"],
            },
        ),
        Tool(
            name="list_runs",
            description="List recent agent runs (directories under runs/).",
            inputSchema={
                "type": "object",
                "properties": {"limit": {"type": "integer", "description": "Max rows. Default 10."}},
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name == "browse_autonomous":
        agent = Agent(CONFIG_PATH)
        result = await agent.run(
            goal=arguments["goal"],
            start_url=arguments.get("start_url"),
            profile=arguments.get("profile"),
            security_audit=False,
        )
        return [TextContent(type="text", text=json.dumps({
            "status": result.get("status"),
            "answer": result.get("answer"),
            "steps_taken": result.get("steps_taken"),
            "urls_visited": result.get("urls_visited"),
            "run_id": result.get("run_id"),
            "run_dir": result.get("run_dir"),
        }, indent=2, default=str))]

    if name == "analyze_login_security":
        agent = Agent(CONFIG_PATH)
        result = await agent.run(
            goal=(
                "Open the page and observe the login form (do NOT submit credentials). "
                "Confirm the form is visible, then finish."
            ),
            start_url=arguments["url"],
            profile=arguments.get("profile"),
            security_audit=True,
        )
        return [TextContent(type="text", text=json.dumps({
            "status": result.get("status"),
            "run_id": result.get("run_id"),
            "run_dir": result.get("run_dir"),
            "security_probe": result.get("security_probe"),
            "security_report": result.get("security_report"),
        }, indent=2, default=str))]

    if name == "extract_page_data":
        from browser_use.browser.profile import BrowserProfile
        from browser_use.browser.session import BrowserSession
        from security import run_security_probe
        import yaml as _y
        with open(CONFIG_PATH) as f:
            cfg = _y.safe_load(f)
        profile_dir = Path(cfg["browser"]["storage_dir"]) / (arguments.get("profile") or cfg["browser"].get("default_profile", "default"))
        profile_dir.mkdir(parents=True, exist_ok=True)
        bp = BrowserProfile(
            user_data_dir=str(profile_dir),
            headless=cfg["browser"].get("headless", False),
            viewport=cfg["browser"].get("viewport"),
        )
        sess = BrowserSession(browser_profile=bp)
        await sess.start()
        try:
            page = await sess.get_current_page()
            await page.goto(arguments["url"], wait_until="domcontentloaded")
            text = (await page.inner_text("body"))[:8000]
            title = await page.title()
            probe = await run_security_probe(page)
            return [TextContent(type="text", text=json.dumps({
                "url": arguments["url"],
                "title": title,
                "text": text,
                "security_probe": probe,
            }, indent=2)[:30000])]
        finally:
            await sess.close()

    if name == "list_runs":
        limit = int(arguments.get("limit", 10))
        runs = sorted([d for d in RUNS_DIR.glob("run-*") if d.is_dir()], reverse=True)[:limit]
        out = []
        for d in runs:
            r = d / "result.json"
            data = json.loads(r.read_text()) if r.exists() else {}
            out.append({
                "run_dir": str(d),
                "run_id": data.get("run_id"),
                "status": data.get("status"),
                "answer": (data.get("answer") or "")[:200],
                "steps": data.get("steps_taken"),
            })
        return [TextContent(type="text", text=json.dumps(out, indent=2))]

    return [TextContent(type="text", text=json.dumps({"error": f"unknown tool: {name}"}))]


async def main():
    async with stdio_server() as (rs, ws):
        # stdio_server has now captured the real stdout (fd 1) for the JSON-RPC
        # channel. Repoint Python's stdout at stderr so any stray library output
        # (rich, browser_use, print) can't inject non-JSON bytes into the stream
        # and kill the connection. MCP keeps using its own captured wrapper.
        sys.stdout = sys.stderr
        await app.run(rs, ws, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
