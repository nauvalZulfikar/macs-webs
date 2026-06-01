#!/usr/bin/env python3
"""CLI entry point for the browser agent."""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from agent import Agent


def main():
    p = argparse.ArgumentParser(
        prog="browser-agent",
        description="Autonomous browser agent (browser-use engine + local Ollama + Claude judge).",
    )
    p.add_argument("goal", help="What the agent should accomplish (natural language).")
    p.add_argument("--url", help="Optional start URL.")
    p.add_argument("--profile", help="Browser profile name (persistent cookies).")
    p.add_argument("--security", action="store_true",
                   help="Run a passive security probe + Claude judgment at the end.")
    p.add_argument("--config", default=str(Path(__file__).parent / "config.yaml"))
    args = p.parse_args()

    agent = Agent(args.config)
    result = asyncio.run(agent.run(
        goal=args.goal,
        start_url=args.url,
        profile=args.profile,
        security_audit=args.security,
    ))
    return 0 if result.get("status") == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
