"""Planner: asks the LLM to pick the next action."""
from typing import Any

from models import ModelRouter


PLANNER_SYSTEM = """You are an autonomous browser agent. You receive:
- A user goal
- A compact snapshot of the current page (elements tagged [refN])
- A history of recent actions

You MUST respond with valid JSON of shape:
{
  "thought": "one sentence on what to do next and why",
  "action": "goto|click|fill|press|scroll|wait|extract_text|screenshot|finish",
  "args": { ...action-specific args... },
  "confidence": 0.0
}

Action argument schemas:
- goto: {"url": "https://..."}
- click: {"ref": "refN"}
- fill: {"ref": "refN", "text": "..."}
- press: {"key": "Enter"}
- scroll: {"dy": 600}
- wait: {"seconds": 1.0}
- extract_text: {"selector": "optional CSS"}
- screenshot: {"path": "<auto>"}
- finish: {"answer": "final answer to the user goal"}

Rules:
- Prefer 'finish' as soon as the goal is achievable.
- Never invent ref ids. Only use refs present in the snapshot.
- If the page seems still loading or empty, choose 'wait' or 'scroll'.
- Keep 'thought' short. Output JSON only — no markdown fences."""


def build_user_prompt(goal: str, snapshot_text: str, history: list[dict[str, Any]], extra: str = "") -> str:
    hist_text = "\n".join(
        f"  step {h['idx']}: {h['action']} {h.get('args', {})} -> {h.get('result', {}).get('ok')}"
        for h in history[-8:]
    ) or "  (none yet)"
    return (
        f"GOAL: {goal}\n\n"
        f"PAGE SNAPSHOT:\n{snapshot_text}\n\n"
        f"HISTORY (last 8 steps):\n{hist_text}\n\n"
        f"{extra}\n"
        "Choose the next action as JSON."
    )


def _is_repeat(history: list[dict[str, Any]]) -> bool:
    if len(history) < 2:
        return False
    a, b = history[-1], history[-2]
    return a.get("action") == b.get("action") and a.get("args") == b.get("args")


def pick_tier(goal: str, history: list[dict[str, Any]]) -> str:
    """Cheap heuristic: hard goals + early steps -> smart; otherwise fast."""
    g = goal.lower()
    hard = any(k in g for k in [
        "security", "vulnerab", "audit", "analyze", "compare", "review",
        "decide", "explain", "reason", "code", "captcha", "auth",
    ])
    if hard and len(history) < 3:
        return "smart"
    if history and not history[-1].get("result", {}).get("ok", True):
        return "smart"
    if _is_repeat(history):
        return "smart"
    if history and history[-1].get("action") in ("click", "press", "goto"):
        return "smart"
    return "fast"


async def next_action(
    router: ModelRouter,
    goal: str,
    snapshot_text: str,
    history: list[dict[str, Any]],
    extra: str = "",
) -> tuple[dict[str, Any], str]:
    tier = pick_tier(goal, history)
    hints = []
    if _is_repeat(history):
        hints.append(
            "WARNING: Your last action was a repeat. The page may have already "
            "changed — re-read the snapshot and pick a different action, or 'finish'."
        )
    extra_full = (extra + "\n" + "\n".join(hints)).strip()
    raw = router.call(
        tier=tier,
        system=PLANNER_SYSTEM,
        user=build_user_prompt(goal, snapshot_text, history, extra_full),
        json_mode=True,
    )
    plan = ModelRouter.extract_json(raw)
    return plan, tier


JUDGE_SYSTEM = """You are a security analyst reviewing a browser agent's findings.
Given a goal, the captured page artifacts, and the security probe data,
produce a concise judgement: severity, key risks, and recommended next steps.
Be specific and avoid hand-waving."""


def judge_prompt(goal: str, probe: dict[str, Any], notes: str) -> str:
    import json as _j
    return (
        f"GOAL: {goal}\n\n"
        f"SECURITY PROBE:\n{_j.dumps(probe, indent=2)[:4000]}\n\n"
        f"AGENT NOTES:\n{notes[:3000]}\n\n"
        "Produce a short report: 1) Findings 2) Risk rating (low/med/high) 3) Recommendations."
    )
