# MACS — Multi-Agent Orchestration System

Claude Code + local LLMs (Ollama) + multi-project chat UI.

## Apa ini

Web app (FastAPI + Svelte 5) yang jadi **single pane of glass** untuk semua project di `~/coding-projects/`. Buka chat di tiap project lewat browser (HP atau desktop) — chatnya pakai `claude -p` (logged-in OAuth, bukan API key).

## Capability

- **Multi-project chat** — sidebar list semua project, klik = chat. Auto-resume last session.
- **Missions** — spawn N agents parallel atau sequential dgn shared scratchpad.
- **Watchers** — file-change / cron / test-loop triggers yg auto-spawn claude.
- **Browser-agent** — sub-agent di `agents/browser-agent/` (Playwright + Ollama + Claude judge) untuk drive browser autonomously.
- **Local LLM delegation** — MCP tools (`code_gen`, `quick`, `summarize`, `transform`, `chain`) yg route ke Qwen3/Gemma via Ollama.
- **+ New Project** UI — scaffold (empty/python/node/git) + auto-register + welcome chat.
- **Autonomous onboarding** — FS observer di `~/coding-projects/` deteksi folder baru → auto-register.
- **Checkpoint / rewind** via `git stash`.
- **Cost dashboard**, **push notif (ntfy)**, **image upload**, **voice input**.

## Stack

- Backend: FastAPI + SQLModel + SQLite (`web/data/projects-web.db`)
- Frontend: Svelte 5 + Vite + Tailwind 4 + marked
- MCP server: `@modelcontextprotocol/sdk` (Node, `build/`)
- Bridges: `claude -p` (subprocess), Ollama (HTTP)
- Auth: HMAC cookie

## Run

Production: managed by launchd (`com.projects-web` → `web/scripts/start-prod.sh`), listens on Tailscale `100.81.47.91:8101`.
- Lokal: http://127.0.0.1:8101/
- HP: http://100.81.47.91:8101/
- Login: `shaka` / `pisang`

Dev: `cd web/backend && uvicorn main:app --reload` + `cd web/frontend && npm run dev`.

## Layout

```
macs/
├── build/                 MCP server TS build
├── src/                   MCP server source
├── agents/
│   └── browser-agent/     Autonomous browser agent (Python)
├── web/
│   ├── backend/           FastAPI app
│   ├── frontend/          Svelte 5 SPA
│   ├── data/              SQLite DB + uploads
│   └── scripts/           launchd start, deploy
└── CLAUDE.md              Global orchestrator guide (loaded by claude session here)
```

## Lihat juga

- `CLAUDE.md` — global orchestrator guide untuk claude session di project ini
- `web/backend/main.py` — semua API endpoint
