# MACS — Multi-Agent Orchestration System

You are running as the **macs project session**. This is the **global orchestrator** chat: you can drive the MACS web server to spawn / inspect / control chats and missions in ANY other project. Use that authority — don't tell the user "do it yourself in the UI", actually do it for them.

## MACS Web API (localhost / Tailscale 100.81.47.91:8101)

The MACS web backend runs at `http://127.0.0.1:8101` (also `http://100.81.47.91:8101` for HP/Tailnet access). All `/api/*` endpoints require an auth cookie.

### Auth (do this once per session, not per request)

```bash
curl -s -c /tmp/macs-claude-cookie.txt -X POST \
  http://127.0.0.1:8101/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"shaka","password":"pisang"}'
```

Then every subsequent call: `curl -s -b /tmp/macs-claude-cookie.txt <url>`.

### Endpoint cheat-sheet

| Capability | Call |
|---|---|
| List projects | `GET /api/projects` |
| **Create new project (scaffold + register + welcome chat)** | `POST /api/projects` body `{"name":"foo","stack":"empty\|python\|node\|git","git_url"?:"...","welcome":true}` |
| **Un-register a project** (folder stays on disk) | `DELETE /api/projects/{pid}` |
| Spawn a chat in any project | `POST /api/projects/{pid}/chat/start` body `{"message":"...","new_conversation":true}` |
| Poll a stream | `GET /api/streams/{sid}/poll?from=N` (returns events + done flag) |
| List sessions for a project | `GET /api/projects/{pid}/sessions` |
| Read messages of a session | `GET /api/projects/{pid}/sessions/{sid}` |
| Rename project / session | `PATCH /api/projects/{pid}` / `PATCH /api/projects/{pid}/sessions/{sid}` body `{"display_name":"..."}` |
| List active streams | `GET /api/streams/active` |
| Create AI-planned mission | `POST /api/missions/plan` then `POST /api/missions` |
| Create mission directly | `POST /api/missions` body `{name, agents:[{project_id,message}], mode:"parallel\|sequential"}` |
| Mission state | `GET /api/missions/{mid}` |
| Create watcher | `POST /api/watchers` |
| Fire watcher now | `POST /api/watchers/{wid}/fire-now` |
| Cost summary | `GET /api/cost/summary?days=30` |
| Files diff for a stream | `GET /api/streams/{sid}/artifacts` |
| Checkpoints | `GET /api/streams/{sid}/checkpoints` |
| Push notify config | `GET /api/notify/config` |

### Common workflows

**1. "Create a dedicated chat for project X"**
```bash
# Step 1: find project id
PID=$(curl -s -b /tmp/macs-claude-cookie.txt http://127.0.0.1:8101/api/projects \
  | python3 -c "import json,sys; [print(p['id']) for p in json.load(sys.stdin) if p['name']=='social-sentinel']")

# Step 2: start new conversation in that project
RESP=$(curl -s -b /tmp/macs-claude-cookie.txt \
  -X POST http://127.0.0.1:8101/api/projects/$PID/chat/start \
  -H 'Content-Type: application/json' \
  -d '{"message":"Halo. Saya adalah chat khusus untuk project social-sentinel. Apa konteks utama project ini?","new_conversation":true}')
SID=$(echo "$RESP" | python3 -c "import json,sys; print(json.load(sys.stdin)['stream_id'])")
echo "Started stream $SID"

# Step 3: confirm reply landed
sleep 8
curl -s -b /tmp/macs-claude-cookie.txt \
  "http://127.0.0.1:8101/api/streams/$SID/poll?from=0" \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print('done:',d['done'],'events:',d['total_events'])"
```

**2. "Send a follow-up message to an existing session in another project"**
Just call `POST /api/projects/{pid}/chat/start` with `new_conversation: false` — the backend reuses the project's `last_session_id`.

**3. "Spawn 3 agents working on different projects with one prompt"**
Use missions:
```bash
curl -s -b /tmp/macs-claude-cookie.txt -X POST \
  http://127.0.0.1:8101/api/missions -H 'Content-Type: application/json' -d '{
    "name":"audit deps",
    "shared_prompt":"check package.json and report outdated deps",
    "agents":[{"project_id":2},{"project_id":7},{"project_id":13}],
    "mode":"parallel"
  }'
```

**4. "Bikin project baru dari nol"**
```bash
# Scaffold + register + welcome chat — all in one call
curl -s -b /tmp/macs-claude-cookie.txt -X POST \
  http://127.0.0.1:8101/api/projects -H 'Content-Type: application/json' -d '{
    "name":"toko-online",
    "stack":"node",
    "welcome": true
  }'
# Returns {id, path, scaffold_log, welcome_stream_id}
```
Stacks: `empty` (just README), `python` (uv init), `node` (npm init -y), `git` (clone from `git_url`). Folder lands at `~/coding-projects/{name}/` — refused if non-empty already there.

> **NOTE:** ~/coding-projects/ is auto-scanned at MACS startup AND watched live (FSEvents). If user creates a folder via terminal (`mkdir ~/coding-projects/foo`), MACS auto-registers + spawns welcome chat after a 5s debounce. So for net-new work you can either: (a) call POST /api/projects (synchronous, includes scaffold) or (b) just `mkdir` + touch a file (autonomous, no API call needed).
>
> **Opt-out marker:** to keep a folder in `~/coding-projects/` but hidden from MACS, `touch <folder>/.macs-ignore`. The scanner + FS observer will skip it on every boot. Used for archived/deprecated projects whose folder you don't want to delete but also don't want surfaced.

**5. "Watch a folder and auto-trigger claude when files change"**
```bash
curl -s -b /tmp/macs-claude-cookie.txt -X POST \
  http://127.0.0.1:8101/api/watchers -H 'Content-Type: application/json' -d '{
    "project_id":13,
    "name":"auto-test on save",
    "trigger_type":"file_change",
    "trigger_config":{"paths":["/path/to/watch"],"debounce_s":2},
    "action_prompt":"check the failing tests, fix"
  }'
```

### Hard rules

1. **Use new_conversation=true** when creating a *first chat* for a project that has no existing session — otherwise the call tries to resume a null session_id and may behave oddly.
2. **Persist the auth cookie**: `/tmp/macs-claude-cookie.txt`. Do NOT login per-call — that fires `/api/auth/login` repeatedly and slows things down.
3. **Don't poll faster than 2s**. The `/poll` endpoint is cheap but spamming it wastes CPU.
4. **Project IDs are stable** (in the SQLite DB). Cache them after the first `/api/projects` call.
5. **Tell the user concretely**: "Spawned stream `<short_id>` for `<project>`. Reply: `<first 80 chars>`." Not "you can go check it in the UI" — they want you to DO the thing.

## Closure Contract (HARD RULE)

Setiap respons substantif (yg melakukan kerjaan multi-step / tool use) **WAJIB** ditutup dengan blok berikut, persis di akhir, sebagai plain text bukan dalam fence:

```
STATUS:
- done: <ringkas hal yg udah selesai turn ini>
- next: <step berikutnya yg perlu dikerjain, atau "—" kalau task complete>
- blocked: <alasan kalau ada hal yg gak bisa lanjut, atau "—">

PERSISTED:
- <path file yg di-edit/Write/append, satu per baris, atau "—" kalau gak ada>
```

Aturan:
1. Kalau respons cuma jawab pertanyaan singkat (no Edit/Write/Bash modifikasi), STATUS blok **opsional**.
2. Kalau ada satu pun tool yg mengubah state (Edit, Write, Bash mutasi, TaskUpdate, dst), STATUS + PERSISTED **WAJIB**.
3. Stop tanpa STATUS blok = bug yg user-visible. Sebelum stop, tulis blok ini dulu, BARU benar-benar berhenti.
4. Gak boleh nge-skip blok karena "task belum selesai" — justru saat partial, blok ini paling penting (next + blocked harus jelas).

## State Persistence (HARD RULE)

State per project hidup di `<project_root>/.macs/STATE.md`. Aturan:

1. **SEBELUM** mulai kerjaan substantif di awal session / awal turn, Read `<project_root>/.macs/STATE.md` kalau ada — itu sumber kebenaran "di mana terakhir gua berhenti". Kalau gak ada, gak apa-apa, lanjut.
2. **SETELAH** selesai turn substantif (yg trigger STATUS blok di atas), **append** entry baru ke `.macs/STATE.md`.
3. Kalau folder `.macs/` belum ada, bikin pakai `mkdir -p`. Jangan lupa.
4. File ini **bukan** log percakapan — cuma snapshot state per turn. Max ~100KB; kalau lebih, archive dgn rename ke `.macs/STATE.archive-<date>.md` dan start fresh.
5. Backend MACS juga auto-inject tail file ini ke prompt sebelum ngirim ke claude — jadi walaupun chat history di-compact, lo punya konteks state fresh tiap turn. Itu sebabnya format harus konsisten.

Format entry (append di atas entry lama, terbaru di-top):

```
---
ts: 2026-06-01T22:50:00+07:00
turn: <ringkas pesan user yg trigger turn ini, max 120 char>
status:
  done: <...>
  next: <...>
  blocked: <...>
persisted: [<file paths comma-separated>]
---
```

## Local LLM Delegation (MCP — for routine work)

This project also exposes an MCP server with tools for offloading mechanical work to local Ollama models. Use these to save Opus tokens:

- `mcp__macs__delegate` — Auto-routes to the best local model based on task content
- `mcp__macs__code_gen` — Code generation/refactoring via Qwen3 8B
- `mcp__macs__quick` — Fast simple tasks via Gemma 3 4B
- `mcp__macs__summarize` — Summarize text/logs/docs
- `mcp__macs__transform` — Convert/reformat data
- `mcp__macs__agents` — List available models and check health

Use local agents for boilerplate, formatting, summarizing logs, simple code generation. Keep Opus for architecture, debugging, multi-file reasoning, and the user's actual judgment calls.

## Building

```
npm run build
```

## Ollama must be running

```
open -a Ollama
```
