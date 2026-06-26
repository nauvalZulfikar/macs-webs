# Browser Agent

Autonomous browser agent: perception → planner → executor loop.

## captcha-solver integration (auto-on)

When the local `captcha-solver` server is up at `http://127.0.0.1:8901` (run via
launchd `com.shaka.captcha-solver`), this agent automatically:

1. Prepends a CAPTCHA-awareness preamble to every task so qwen3 doesn't waste
   steps trying to defeat CAPTCHAs visually — it just reports + stops.
2. On any non-`ok` finish, checks the last URL the agent visited and POSTs to
   `captcha-solver`'s `/solve` endpoint as a fallback. The returned token is
   stashed in `final["captcha_solve"]` for downstream consumers.

Override the solver location with `CAPTCHA_SOLVER_URL=http://...`.
Disable the integration by stopping the launchd job: `_captcha_solver_up()`
turns false and both behaviors no-op.


- **Perception** — Playwright snapshot of page (tags every interactive element with `[refN]` + body excerpt + security probe).
- **Planner** — LLM picks the next action. Router tiers: `fast` (Gemma 3 4B), `smart` (Qwen3 8B), `judge` (Claude Opus 4.7).
- **Executor** — Playwright actions: `goto`, `click`, `fill`, `press`, `scroll`, `wait`, `extract_text`, `screenshot`, `finish`.
- **Memory** — SQLite. Stores runs, steps, learned facts per domain. Run artifacts (screenshots, network logs, security reports) saved to `runs/run-XXXXX/`.
- **Safety** — Domain allow/block list, repeat-action detection (escalates to smart tier), passive-only security probe.

## Usage

```bash
# Basic
./run.sh "Open the page and report what you see" --url https://example.com

# Specific profile (persistent cookies / login)
./run.sh "Check inbox for new messages" --url https://mail.foo --profile work

# Security audit at the end (needs ANTHROPIC_API_KEY for Claude judge tier)
export ANTHROPIC_API_KEY=sk-...
./run.sh "Analyze the login form" --url https://target.com/login --security
```

## Files

| File | Purpose |
|------|---------|
| `agent.py` | Main loop |
| `cli.py` | CLI entry |
| `config.yaml` | Models, browser, safety config |
| `memory.py` | SQLite session store |
| `models.py` | Ollama + Claude router |
| `perception.py` | DOM snapshot + security probe |
| `executor.py` | Playwright action dispatch |
| `planner.py` | LLM action selection + tier picker |
| `runs/` | Per-run artifacts (screenshots, network.json, reports) |

## How tier-picking works

- Goal contains words like `security|audit|analyze|review|captcha|auth` → **smart** for first 3 steps
- Previous action failed → **smart**
- Last two actions identical → **smart** (with hint)
- Otherwise → **fast**

## Extending

Add a new action: implement in `executor.py:BrowserSession`, register in `dispatch()`, document in `planner.py:PLANNER_SYSTEM`.

Add a new model: add to `config.yaml:models.router` and ensure the provider has a method in `models.py:ModelRouter`.
