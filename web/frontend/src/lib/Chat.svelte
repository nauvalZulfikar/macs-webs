<script>
  import { listSessions, loadSession, switchSession } from './api.js'
  import {
    streams as streamsStore,
    startStream,
    streamKeyOf,
    abortStream,
    detachClient,
  } from './streamsStore.svelte.js'
  import { tick, onMount } from 'svelte'
  import { marked } from 'marked'
  import DOMPurify from 'dompurify'
  import hljs from 'highlight.js/lib/common'
  import { pushToast } from './toastStore.svelte.js'
  import { settings, toggleStar, isStarred, playChime } from './settingsStore.svelte.js'

  let uiPrefs = $state({ toastsEnabled: true, savedPrompts: [], audioCues: false, starred: {} })
  $effect(() => {
    const unsub = settings.subscribe((v) => { uiPrefs = v })
    return unsub
  })
  function toast(opts) {
    if (uiPrefs.toastsEnabled) pushToast(opts)
  }

  // Live cost accumulator across this session
  let sessionCost = $state(0)
  let sessionTurns = $state(0)
  let editingMsgIdx = $state(-1)
  let editingText = $state('')
  let promptPickerOpen = $state(false)

  // Safe markdown render: marked → HTML → DOMPurify scrub. Strips
  // <script>, on* handlers, javascript: URLs, srcdoc, etc. Required because
  // user/tool input can include literal HTML and we render via @html.
  function safeMarked(text) {
    const dirty = marked.parse(text || '')
    return DOMPurify.sanitize(dirty, {
      ADD_ATTR: ['target'],
      FORBID_TAGS: ['style'],
    })
  }

  // Svelte action: post-process every <pre><code> inside .chat-md to add (a)
  // a language chip + copy button at the top, and (b) syntax highlighting via
  // highlight.js. Idempotent — safe to re-run as markdown streams in.
  function withCopyButtons(node) {
    function decorate() {
      node.querySelectorAll('pre').forEach((pre) => {
        if (pre.dataset.decorated) return
        pre.dataset.decorated = '1'
        pre.style.position = 'relative'

        const code = pre.querySelector('code')
        // Detect language from class="language-xxx"
        let lang = ''
        if (code) {
          const m = (code.className || '').match(/language-(\w+)/)
          if (m) lang = m[1]
        }

        // Header chip
        const header = document.createElement('div')
        header.className = 'code-head'
        header.innerHTML = `<span class="code-lang">${lang || 'text'}</span>`
        const btn = document.createElement('button')
        btn.type = 'button'
        btn.className = 'copy-btn'
        btn.textContent = 'Copy'
        btn.setAttribute('aria-label', 'Copy code')
        btn.addEventListener('click', async (e) => {
          e.stopPropagation()
          const txt = code?.innerText ?? pre.innerText ?? ''
          try {
            await navigator.clipboard.writeText(txt)
            btn.textContent = 'Copied ✓'
            btn.classList.add('copied')
            toast({ kind: 'success', title: 'Code copied', body: `${txt.length} chars`, duration: 1800 })
            setTimeout(() => { btn.textContent = 'Copy'; btn.classList.remove('copied') }, 1500)
          } catch {
            btn.textContent = 'Failed'
            toast({ kind: 'error', title: 'Copy failed', body: 'Clipboard not available' })
            setTimeout(() => { btn.textContent = 'Copy' }, 1500)
          }
        })
        header.appendChild(btn)
        pre.prepend(header)

        // Syntax highlight (skip if no language hint or unknown)
        if (code && lang && hljs.getLanguage(lang)) {
          try {
            const out = hljs.highlight(code.innerText, { language: lang, ignoreIllegals: true })
            code.innerHTML = out.value
            code.classList.add('hljs')
          } catch {}
        } else if (code) {
          try {
            const out = hljs.highlightAuto(code.innerText)
            if (out.relevance > 5) {
              code.innerHTML = out.value
              code.classList.add('hljs')
            }
          } catch {}
        }
      })
    }
    decorate()
    const mo = new MutationObserver(decorate)
    mo.observe(node, { childList: true, subtree: true })
    return { destroy() { mo.disconnect() } }
  }
  import ArtifactsPanel from './ArtifactsPanel.svelte'
  import BrowserViewer from './BrowserViewer.svelte'
  import StatePanel from './StatePanel.svelte'
  import VoiceInput from './VoiceInput.svelte'
  import EditorPane from './EditorPane.svelte'
  import CheckpointTimeline from './CheckpointTimeline.svelte'

  let { project, onBack, onChanged } = $props()
  let projectDisplayName = $derived(project.display_name || project.name)

  let messages = $state([])
  let input = $state('')
  let error = $state(null)
  let activeSessionId = $state(project.last_session_id)
  let pendingNewConvo = $state(false)
  let historyOpen = $state(false)
  let history = $state([])
  let historyLoading = $state(false)
  let loadingMessages = $state(true)
  let approval = $state(null)
  let scroller
  let artifactsOpen = $state(false)
  let artifactsCount = $state(0)
  let editorOpen = $state(false)
let statePanelOpen = $state(false)
  let editorPath = $state(null)
  let editedFiles = $state([]) // file paths claude touched in this stream

  function trackEditedFile(toolName, input) {
    const p = input?.file_path || input?.path
    if (!p) return
    if (!['Edit','Write','Read','NotebookEdit'].includes(toolName)) return
    if (editedFiles.includes(p)) return
    editedFiles = [p, ...editedFiles].slice(0, 10)
  }

  // ─── Store subscription (drives streaming events) ──────────────────────
  let storeSnap = $state(new Map())
  $effect(() => {
    const unsub = streamsStore.subscribe((m) => { storeSnap = m })
    return unsub
  })

  let activeKey = $derived(streamKeyOf(project.id, activeSessionId))
  let myStream = $derived(storeSnap.get(activeKey) || null)
  let pending = $derived(!!(myStream && !myStream.done))

  let replayedUpTo = $state(0)
  $effect(() => {
    if (!myStream) return
    if (loadingMessages) return // wait until history populated
    while (replayedUpTo < myStream.events.length) {
      handleEvent(myStream.events[replayedUpTo])
      replayedUpTo++
    }
    if (pending) scrollDown()
  })

  // ─── Wall-clock ticker for send timer & countdown ──────────────────────
  let nowMs = $state(Date.now())
  $effect(() => {
    const t = setInterval(() => { nowMs = Date.now() }, 1000)
    return () => clearInterval(t)
  })

  let sendElapsedS = $derived(
    pending && myStream ? Math.max(0, Math.floor((nowMs - myStream.startedAt) / 1000)) : 0
  )
  let sinceLastEvtS = $derived(
    pending && myStream ? Math.max(0, Math.floor((nowMs - myStream.lastEventAt) / 1000)) : 0
  )
  let lastUserIdx = $derived.by(() => {
    for (let j = messages.length - 1; j >= 0; j--) {
      if (messages[j].role === 'user') return j
    }
    return -1
  })

  function fmtSec(s) {
    if (s < 60) return `${s}s`
    const m = Math.floor(s / 60), rem = s % 60
    return `${m}:${String(rem).padStart(2, '0')}`
  }

  const TOOL_COLORS = {
    Bash: 'text-amber-300', Edit: 'text-blue-300', Write: 'text-blue-300',
    Read: 'text-neutral-300', Glob: 'text-neutral-300', Grep: 'text-neutral-300',
    Task: 'text-purple-300', TaskCreate: 'text-purple-300', TaskUpdate: 'text-purple-300',
    Skill: 'text-emerald-300', WebFetch: 'text-cyan-300', WebSearch: 'text-cyan-300',
  }

  function toolColor(name) {
    if (TOOL_COLORS[name]) return TOOL_COLORS[name]
    if (name?.startsWith('mcp__')) return 'text-emerald-300'
    return 'text-neutral-300'
  }

  function toolDisplay(name) {
    if (!name) return ''
    if (name.startsWith('mcp__')) {
      const parts = name.split('__')
      if (parts.length >= 3) return `${parts[1].toUpperCase()} · ${parts.slice(2).join('__')}`
    }
    return name
  }

  marked.setOptions({ breaks: true, gfm: true })

  onMount(async () => {
    if (activeSessionId) {
      try {
        const data = await loadSession(project.id, activeSessionId)
        messages = data.messages || []
      } catch (e) {
        // ignore — session file may not exist locally yet
      }
    }
    // If a live stream already exists for this chat (from a prior navigate),
    // surface the user msg + replay buffered events.
    const existing = storeSnap.get(streamKeyOf(project.id, activeSessionId))
    if (existing && existing.userMessage) {
      const alreadyHas = messages.some(
        (m) => m.role === 'user' && m.text === existing.userMessage
      )
      if (!alreadyHas) messages = [...messages, { role: 'user', text: existing.userMessage }]
    }
    loadingMessages = false
    scrollDown()
    if (import.meta.env.DEV) {
      window.__chatTest = { inject: handleEvent }
    }
  })

  async function scrollDown() {
    await tick()
    if (scroller) scroller.scrollTop = scroller.scrollHeight
  }

  function handleEvent(evt) {
    if (evt.type === 'system' && evt.subtype === 'init') {
      if (evt.session_id) activeSessionId = evt.session_id
      return
    }
    if (evt.type === 'assistant' && evt.message?.content) {
      const last = messages.at(-1)
      const assistantMsg =
        last && last.role === 'assistant' && last.streaming
          ? last
          : (() => {
              const m = { role: 'assistant', text: '', toolUses: [], streaming: true }
              messages = [...messages, m]
              return m
            })()
      for (const block of evt.message.content) {
        if (block.type === 'text') {
          assistantMsg.text += block.text
        } else if (block.type === 'tool_use') {
          assistantMsg.toolUses = [
            ...assistantMsg.toolUses,
            { name: block.name, input: block.input, id: block.id, result: null },
          ]
          trackEditedFile(block.name, block.input)
          // Auto-open editor on first Edit/Write of stream + jump to that file
          const filePath = block.input?.file_path || block.input?.path
          if (filePath && ['Edit','Write','NotebookEdit'].includes(block.name)) {
            editorPath = filePath.startsWith(project.path)
              ? filePath.slice(project.path.length + 1)
              : filePath
          }
        }
      }
      messages = [...messages]
      return
    }
    if (evt.type === 'user' && evt.message?.content) {
      for (const block of evt.message.content) {
        if (block.type === 'tool_result') {
          const last = messages.at(-1)
          if (last && last.role === 'assistant') {
            const t = last.toolUses.find((t) => t.id === block.tool_use_id)
            if (t) {
              const c = block.content
              t.result = typeof c === 'string' ? c : Array.isArray(c) ? c.map((p) => p.text || '').join('') : JSON.stringify(c)
              messages = [...messages]
            }
          }
        }
      }
      return
    }
    if (evt.type === 'retry') {
      messages = [
        ...messages,
        {
          role: 'system_note',
          text: `retry ${evt.attempt}/${evt.max_attempts}: ${evt.reason}`,
        },
      ]
      return
    }
    if (evt.type === 'result') {
      const last = messages.at(-1)
      if (last && last.role === 'assistant') {
        last.streaming = false
        last.cost = evt.total_cost_usd
        last.durationMs = evt.duration_ms
        messages = [...messages]
      }
      if (evt.session_id) activeSessionId = evt.session_id
      // Accumulate live counters
      if (evt.total_cost_usd != null) sessionCost += evt.total_cost_usd
      sessionTurns += 1
      // Toast on successful turn complete
      if (!evt.is_error) {
        const dur = evt.duration_ms ? ` · ${(evt.duration_ms / 1000).toFixed(1)}s` : ''
        const cost = evt.total_cost_usd != null ? ` · $${evt.total_cost_usd.toFixed(4)}` : ''
        toast({ kind: 'success', title: 'Reply selesai', body: `${projectDisplayName}${dur}${cost}`, duration: 3000 })
      }
      return
    }
    if (evt.type === 'session_saved' && evt.session_id) {
      activeSessionId = evt.session_id
      return
    }
    if (evt.type === 'stream_done') {
      const last = messages.at(-1)
      if (last && last.role === 'assistant' && last.streaming) {
        last.streaming = false
        messages = [...messages]
      }
      // Audio cue if user opted in + tab was not focused (or always if focused)
      if (uiPrefs.audioCues) playChime()
      try { onChanged?.() } catch {}
      // Safety reload: the SSE delivery may have skipped events while the tab
      // was backgrounded. Refresh from the jsonl source of truth (debounced).
      queueMicrotask(refreshFromDisk)
      return
    }
    if (evt.type === 'approval_request') {
      approval = {
        denials: evt.denials || [],
        originalMessage: evt.original_message,
      }
      return
    }
    if (evt.type === 'error') {
      error = evt.error || 'unknown error'
      toast({ kind: 'error', title: 'Stream error', body: String(error).slice(0, 120), duration: 5000 })
      return
    }
  }

  async function send(opts = {}) {
    const { elevated = false, retryMessage = null } = opts
    let msg = retryMessage ?? input.trim()
    if (!msg && uploads.length === 0) return
    // Anti-footgun: clicking Send while a stream is still running used to be a
    // silent no-op — user thought it sent. Now we show a toast + flash the Stop
    // button so they know what to do.
    if (pending) {
      error = 'Chat masih streaming. Tap Stop dulu kalau mau kirim baru, atau tunggu selesai.'
      setTimeout(() => { if (error?.startsWith('Chat masih streaming')) error = null }, 4000)
      return
    }
    error = null
    const useNew = pendingNewConvo
    pendingNewConvo = false
    // Attach uploaded images: append Read instruction + path to the prompt so
    // claude pulls them in. Uses project-relative path when available.
    const attachedUploads = uploads.slice()
    if (attachedUploads.length && !retryMessage) {
      const refs = attachedUploads
        .map((u) => u.project_relative || u.project_path)
        .map((p) => `Read ${p}`)
        .join(' and ')
      msg = msg ? `${msg}\n\n(attached images: ${refs})` : `Look at the attached images: ${refs}. Describe what you see.`
    }
    // Snapshot of what we cleared so we can restore on failure
    const savedInput = input
    const savedUploads = uploads.slice()
    if (!retryMessage) {
      const m = { role: 'user', text: msg }
      if (attachedUploads.length) m.uploads = attachedUploads
      messages = [...messages, m]
      input = ''
      uploads = []
    } else {
      messages = [...messages, { role: 'user', text: msg, retry: true }]
    }
    // Placeholder assistant bubble so the agent-side countdown shows immediately,
    // even before claude streams its first chunk. handleEvent's first 'assistant'
    // event will reuse it (it's the last streaming assistant msg).
    messages = [
      ...messages,
      { role: 'assistant', text: '', toolUses: [], streaming: true, placeholder: true },
    ]
    scrollDown()
    try {
      await startStream({
        projectId: project.id,
        sessionId: activeSessionId,
        message: msg,
        newConversation: useNew,
        elevated,
      })
    } catch (e) {
      // Restore the input + drop the optimistic user/placeholder bubbles so the
      // user can retry without retyping. Surface a clear toast.
      if (e?.code === "stream_busy") {
        const busy = e.busyMessage ? `"${e.busyMessage}"` : "pesan sebelumnya"
        error = `⏳ Stream lagi sibuk dgn ${busy}. Tunggu selesai, lalu kirim lagi.`
      } else {
        error = `❌ Gagal kirim: ${e.message}. Tap kirim lagi untuk retry.`
      }
      if (!retryMessage) {
        input = savedInput
        uploads = savedUploads
      }
      // Strip the trailing 2 bubbles we optimistically pushed (user + placeholder)
      messages = messages.slice(0, -2)
      scrollDown()
    }
  }

  // Stale-stream detection — pending=true but no events for too long
  // means claude likely crashed or SSE went into a reconnect storm.
  // Surface this as a banner with explicit Retry/Abort so user is never stuck
  // staring at a silent "thinking" bubble for 10 minutes.
  let streamStuck = $derived(pending && sinceLastEvtS > 90)
  let staleMessage = $state(null) // saved msg to retry from stuck banner

  // Silent-stop detection — claude's last "turn" (all assistant messages
  // since the most recent user message) had tool use(s) but the final
  // assistant text has no STATUS closure block per CLAUDE.md contract.
  //
  // Important: the session loader splits a single Claude API turn into
  // multiple assistant `messages` (one per content block / tool_result
  // boundary). So we must walk backwards across ALL assistant messages until
  // the most recent user message to evaluate the WHOLE turn, not just the
  // last bubble.
  const STATUS_RE = /STATUS:\s*\n/i
  let silentlyStopped = $derived.by(() => {
    if (pending) return false
    const n = messages.length
    if (!n) return false
    let hadTools = false
    let finalText = null // latest non-empty assistant text in this turn
    for (let i = n - 1; i >= 0; i--) {
      const m = messages[i]
      if (m.role === 'user') break
      if (m.role !== 'assistant') continue
      if (Array.isArray(m.toolUses) && m.toolUses.length > 0) hadTools = true
      if (finalText === null && (m.text || '').trim()) finalText = m.text
    }
    if (!hadTools) return false
    if (finalText === null) return true  // tool calls + zero text → silently stopped
    return !STATUS_RE.test(finalText)
  })

  function requestRecap() {
    input = "Lo berhenti tanpa STATUS blok yg diwajibkan CLAUDE.md. " +
            "Recap dulu: apa yg udah lo ubah (file + ringkasan perubahan), " +
            "apa next step kalau task belum kelar, apa blocked. " +
            "Lalu tutup dengan blok STATUS + PERSISTED sesuai format CLAUDE.md."
  }

  async function abortStuck() {
    if (!myStream?.streamId) return
    try { await abortStream(myStream.streamId) } catch {}
    // Capture last user message for "retry" button
    const lastUser = [...messages].reverse().find((m) => m.role === 'user')
    staleMessage = lastUser?.text || null
  }
  async function retryStuck() {
    if (!staleMessage) return
    const msg = staleMessage
    staleMessage = null
    // wait until pending=false so send() doesn't bounce
    if (myStream?.streamId) {
      try { await abortStream(myStream.streamId) } catch {}
    }
    await new Promise((r) => setTimeout(r, 400))
    await send({ retryMessage: msg })
  }

  function approveAndRetry() {
    const original = approval?.originalMessage
    approval = null
    if (original) send({ elevated: true, retryMessage: original })
  }

  function denyApproval() { approval = null }

  function newConvo() {
    if (pending) return
    messages = []
    error = null
    pendingNewConvo = true
    activeSessionId = null
    replayedUpTo = 0
  }

  async function stop() {
    if (myStream?.streamId) {
      try {
        await abortStream(myStream.streamId)
        toast({ kind: 'warn', title: 'Stream dihentikan', body: 'User abort', duration: 2500 })
      } catch (e) {
        toast({ kind: 'error', title: 'Abort gagal', body: String(e).slice(0, 120) })
      }
    }
  }

  function onKey(e) {
    if (slashOpen) {
      if (e.key === 'ArrowDown') { e.preventDefault(); slashIdx = Math.min(slashIdx + 1, slashMatches.length - 1); return }
      if (e.key === 'ArrowUp')   { e.preventDefault(); slashIdx = Math.max(slashIdx - 1, 0); return }
      if (e.key === 'Tab' || (e.key === 'Enter' && !e.shiftKey)) {
        e.preventDefault()
        pickSlash(slashMatches[slashIdx])
        return
      }
      if (e.key === 'Escape') { e.preventDefault(); slashOpen = false; return }
    }
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() }
  }

  function appendVoice(t) {
    if (!t) return
    input = input ? `${input.trimEnd()} ${t}` : t
  }

  function startEditMessage(idx, m) {
    if (pending) return
    editingMsgIdx = idx
    editingText = m.text || ''
  }
  function cancelEditMessage() {
    editingMsgIdx = -1
    editingText = ''
  }
  async function saveEditAndResend() {
    if (editingMsgIdx < 0) return
    const newText = editingText.trim()
    cancelEditMessage()
    if (!newText) return
    // Truncate history to before this user message, then send as fresh turn
    messages = messages.slice(0, editingMsgIdx)
    input = newText
    await send({ retryMessage: newText })
  }

  function pickSavedPrompt(p) {
    promptPickerOpen = false
    input = input ? `${input}\n${p.text}` : p.text
  }

  // Export conversation as markdown or JSON
  function downloadBlob(name, mime, content) {
    const blob = new Blob([content], { type: mime })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = name
    document.body.appendChild(a)
    a.click()
    setTimeout(() => { document.body.removeChild(a); URL.revokeObjectURL(url) }, 100)
  }
  function exportMarkdown() {
    const lines = []
    lines.push(`# ${projectDisplayName}`)
    if (activeSessionId) lines.push(`\nSession \`${activeSessionId}\``)
    lines.push(`\n_Exported ${new Date().toISOString()}_\n`)
    for (const m of messages) {
      if (m.role === 'user') {
        lines.push(`\n---\n\n**User**\n\n${m.text || ''}`)
      } else if (m.role === 'assistant') {
        const tools = (m.toolUses || []).map((t) => `- ${t.name}(${JSON.stringify(t.input).slice(0, 200)})`).join('\n')
        lines.push(`\n**Assistant**${m.cost ? ` _(${m.durationMs}ms · $${m.cost.toFixed(4)})_` : ''}\n`)
        if (tools) lines.push(`<details><summary>Tools used (${m.toolUses.length})</summary>\n\n${tools}\n\n</details>\n`)
        lines.push(m.text || '')
      } else if (m.role === 'system_note') {
        lines.push(`\n> ↻ ${m.text}\n`)
      }
    }
    const safeName = (projectDisplayName || 'chat').replace(/[^a-z0-9-_]/gi, '_')
    const ts = new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')
    downloadBlob(`${safeName}-${ts}.md`, 'text/markdown', lines.join('\n'))
    toast({ kind: 'success', title: 'Exported markdown', body: `${messages.length} messages` })
  }
  function exportJson() {
    const payload = {
      project: { id: project.id, name: project.name, display_name: project.display_name, path: project.path },
      session_id: activeSessionId,
      exported_at: new Date().toISOString(),
      messages,
    }
    const safeName = (projectDisplayName || 'chat').replace(/[^a-z0-9-_]/gi, '_')
    const ts = new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')
    downloadBlob(`${safeName}-${ts}.json`, 'application/json', JSON.stringify(payload, null, 2))
    toast({ kind: 'success', title: 'Exported JSON', body: `${messages.length} messages` })
  }
  let exportMenuOpen = $state(false)

  // Slash-command autocomplete. Triggers when input starts with "/" — show
  // a dropdown of built-in commands; selection replaces the slash with the
  // command's expanded text.
  const SLASH_COMMANDS = [
    { cmd: '/files',    label: 'List project files',    text: 'List the top-level files in this project, with one-line descriptions.' },
    { cmd: '/test',     label: 'Run tests',             text: 'Run the project test suite and report pass/fail counts.' },
    { cmd: '/lint',     label: 'Run linter',            text: 'Run the project linter and report all issues, grouped by file.' },
    { cmd: '/build',    label: 'Build project',         text: 'Build the project and surface any compilation/typecheck errors.' },
    { cmd: '/diff',     label: 'Show git diff',         text: 'Run `git diff` and `git status` and summarize the working-tree changes.' },
    { cmd: '/readme',   label: 'Summarize README',      text: 'Read README.md and give me a one-paragraph summary of what this project does.' },
    { cmd: '/state',    label: 'Show STATE.md',         text: 'Read .macs/STATE.md (if present) and summarize the latest 3 entries.' },
    { cmd: '/explain',  label: 'Explain a file',        text: 'Explain the purpose, key functions, and external dependencies of: ' },
    { cmd: '/fix',      label: 'Find & fix a bug',      text: 'Hunt for bugs in the recent changes. Adversarially verify findings. Then propose fixes.' },
    { cmd: '/review',   label: 'Code review the diff',  text: 'Review the current diff for correctness, performance, and readability. Be specific with file:line refs.' },
  ]
  let slashOpen = $state(false)
  let slashIdx = $state(0)
  let slashMatches = $derived.by(() => {
    const t = (input || '').trim()
    if (!t.startsWith('/')) return []
    const q = t.slice(1).toLowerCase().split(/\s/)[0]
    return SLASH_COMMANDS.filter((c) => c.cmd.slice(1).startsWith(q) || c.label.toLowerCase().includes(q)).slice(0, 6)
  })
  $effect(() => {
    slashOpen = slashMatches.length > 0
    if (slashIdx >= slashMatches.length) slashIdx = 0
  })
  function pickSlash(c) {
    slashOpen = false
    input = c.text
  }

  async function onPaste(e) {
    const items = Array.from(e.clipboardData?.items || [])
    const img = items.find((it) => it.type?.startsWith('image/'))
    if (!img) return
    e.preventDefault()
    const file = img.getAsFile()
    if (!file) return
    await uploadImage(file)
  }

  let uploads = $state([]) // {filename, project_relative, url, dataUrl}
  async function uploadImage(file) {
    try {
      const r = await fetch(`/api/uploads/image?pid=${project.id}`, {
        method: 'POST',
        headers: { 'Content-Type': file.type },
        body: file,
      })
      if (!r.ok) throw new Error(`upload ${r.status}`)
      const data = await r.json()
      const dataUrl = await new Promise((res) => {
        const fr = new FileReader()
        fr.onload = () => res(fr.result)
        fr.readAsDataURL(file)
      })
      uploads = [...uploads, { ...data, dataUrl }]
    } catch (e) {
      error = `image upload failed: ${e.message}`
    }
  }

  async function onFilePick(e) {
    const f = e.target.files?.[0]
    if (f) await uploadImage(f)
    e.target.value = ''
  }

  function removeUpload(i) {
    uploads = uploads.filter((_, idx) => idx !== i)
  }

  async function openHistory() {
    historyOpen = true
    historyLoading = true
    try { history = await listSessions(project.id) }
    catch (e) { error = e.message }
    finally { historyLoading = false }
  }

  async function pickSession(sid) {
    if (pending) return
    historyOpen = false
    loadingMessages = true
    try {
      await switchSession(project.id, sid)
      const data = await loadSession(project.id, sid)
      messages = data.messages || []
      activeSessionId = sid
      pendingNewConvo = false
      replayedUpTo = 0
    } catch (e) { error = e.message }
    finally { loadingMessages = false; scrollDown() }
  }

  function fmtTime(ts) { return new Date(ts * 1000).toLocaleString() }

  let refreshing = false
  async function refreshFromDisk() {
    if (!activeSessionId || refreshing) return
    refreshing = true
    try {
      const data = await loadSession(project.id, activeSessionId)
      const fresh = data.messages || []
      // Only replace if disk has at least as many messages as our local state
      // (avoid overwriting in-progress stream with stale snapshot)
      if (fresh.length >= messages.filter(m => m.role !== 'system_note').length) {
        messages = fresh
      }
    } catch (e) {
      // ignore
    } finally {
      refreshing = false
      scrollDown()
    }
  }

  // Detect stuck state: pending=true but no events for >75s (idle 60s + retry 15s).
  // When that fires, refresh from disk in case SSE missed the final events.
  $effect(() => {
    if (!pending) return
    if (sinceLastEvtS > 75) refreshFromDisk()
  })

  // A3 recovery: if the server-side stream expired (poll 404 — typically a
  // backend restart mid-flight), the in-memory buffer is gone but the reply
  // may already be persisted to the session jsonl by claude. Drop the empty
  // placeholder bubble and refresh from disk so the user sees the reply
  // instead of an indefinite "thinking" state.
  $effect(() => {
    if (myStream?.error === 'stream expired') {
      messages = messages.filter(m => !(m.role === 'assistant' && m.placeholder && !m.text))
      refreshFromDisk()
    }
  })

  // Poll artifacts count on a stable streamId, not the whole myStream — the
  // store patches the stream object on every event, which would otherwise
  // tear down and re-create the interval before it ever ticks.
  let myStreamId = $derived(myStream?.streamId || null)
  $effect(() => {
    const sid = myStreamId
    if (!sid) { artifactsCount = 0; return }
    let cancelled = false
    const pull = async () => {
      try {
        const r = await fetch(`/api/streams/${sid}/artifacts`)
        if (!r.ok || cancelled) return
        const data = await r.json()
        artifactsCount = (data.files || []).length
      } catch {}
    }
    pull()
    const int = setInterval(pull, 5000)
    return () => { cancelled = true; clearInterval(int) }
  })

  // Scroll-to-latest button: visible when user has scrolled up >300px from bottom
  let scrolledUp = $state(false)
  function onScroll() {
    if (!scroller) return
    const dist = scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight
    scrolledUp = dist > 300
  }
  function jumpToLatest() {
    if (!scroller) return
    scroller.scrollTo({ top: scroller.scrollHeight, behavior: 'smooth' })
  }

  // Keyboard shortcuts overlay (`?` to toggle when not typing)
  let shortcutsOpen = $state(false)
  function onGlobalKey(ev) {
    const t = ev.target
    const typing = t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)
    if (typing) return
    if (ev.key === '?' || (ev.shiftKey && ev.key === '/')) {
      ev.preventDefault()
      shortcutsOpen = !shortcutsOpen
    } else if (ev.key === 'Escape' && shortcutsOpen) {
      shortcutsOpen = false
    }
    // ⌘P toggles saved prompts picker (when there are any)
    if ((ev.key === 'p' || ev.key === 'P') && (ev.metaKey || ev.ctrlKey) && uiPrefs.savedPrompts.length > 0) {
      ev.preventDefault()
      promptPickerOpen = !promptPickerOpen
    }
  }
  $effect(() => {
    window.addEventListener('keydown', onGlobalKey)
    return () => window.removeEventListener('keydown', onGlobalKey)
  })

  // Suggested prompts on empty chat — surfaced when no messages yet.
  // Smart: try to read CLAUDE.md / README.md and extract first 3 H1/H2/bullet
  // items as project-aware suggestions. Fallback to generic if not found.
  const GENERIC_PROMPTS = [
    { label: '📖 Read README', text: 'Read the README and give me a one-paragraph summary of what this project does.' },
    { label: '🗂 List files', text: 'List the top-level files and folders in this project, with a short note on what each is for.' },
    { label: '🩺 Health check', text: 'Run the project tests / linter / build if available, and report what passes vs what fails.' },
  ]
  let smartPrompts = $state(null)
  let SUGGESTED_PROMPTS = $derived(smartPrompts || GENERIC_PROMPTS)

  async function loadSmartPrompts() {
    smartPrompts = null
    for (const path of ['CLAUDE.md', 'README.md', 'AGENTS.md']) {
      try {
        const r = await fetch(`/api/projects/${project.id}/files/read?path=${encodeURIComponent(path)}`)
        if (!r.ok) continue
        const data = await r.json()
        const body = (data.content || '').slice(0, 8000)
        const items = []
        // Extract headings + first sentence after each
        const lines = body.split('\n')
        for (let i = 0; i < lines.length && items.length < 3; i++) {
          const ln = lines[i].trim()
          const m = ln.match(/^#{1,3}\s+(.+)/)
          if (m && m[1].length < 60 && !/^(table of contents|toc|installation|license)/i.test(m[1])) {
            // Skip first H1 (usually the project name)
            if (items.length === 0 && m[1].toLowerCase() === project.name.toLowerCase()) continue
            items.push({
              label: '✨ ' + m[1],
              text: `Tell me about "${m[1]}" in this project. Reference the relevant files.`,
            })
          }
        }
        if (items.length > 0) {
          smartPrompts = items
          return
        }
      } catch {}
    }
  }
  $effect(() => {
    if (project?.id && messages.length === 0 && !loadingMessages) {
      loadSmartPrompts()
    }
  })

  function applySuggestion(text) {
    input = text
  }
</script>

<div class="view-in flex h-dvh flex-col bg-neutral-950">
  <!-- header -->
  <header class="flex items-center gap-2 border-b border-neutral-800 bg-neutral-950/70 px-3 py-3 backdrop-blur-md">
    <button
      class="rounded-md px-2 py-1 text-sm text-neutral-400 transition hover:bg-neutral-800 hover:text-neutral-100 md:hidden"
      onclick={onBack}
      data-testid="back-btn"
    >← Back</button>
    <div
      class="grid h-9 w-9 shrink-0 place-items-center rounded-xl text-sm font-semibold text-white shadow-md ring-1 ring-white/10"
      style="background: linear-gradient(135deg, #10b981 0%, #047857 100%);"
    >
      {(projectDisplayName || '?').trim().charAt(0).toUpperCase()}
    </div>
    <div class="min-w-0 flex-1">
      <div class="flex items-center gap-2">
        <div class="truncate font-medium" data-testid="project-name">{projectDisplayName}</div>
        {#if pending}
          <span class="inline-flex items-center gap-1 rounded-full bg-emerald-500/20 px-2 py-0.5 text-[10px] text-emerald-300" data-testid="chat-running-badge">
            <span class="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-400"></span>
            running · {fmtSec(sendElapsedS)}
          </span>
        {/if}
        {#if myStream?.reconnecting}
          <span class="rounded-full bg-amber-500/20 px-2 py-0.5 text-[10px] text-amber-300">reconnecting…</span>
        {/if}
      </div>
      <div class="truncate text-xs text-neutral-500">
        {project.path}
        {#if activeSessionId}
          <span class="ml-1 text-neutral-600">· {activeSessionId.slice(0, 8)}</span>
        {/if}
        {#if pendingNewConvo}
          <span class="ml-1 rounded bg-amber-500/15 px-1.5 text-[10px] text-amber-300">new</span>
        {/if}
      </div>
    </div>
    {#if artifactsCount > 0}
      <button
        class="rounded-md bg-blue-500/15 px-2 py-1 text-xs text-blue-300 hover:bg-blue-500/30"
        onclick={() => (artifactsOpen = true)}
        data-testid="artifacts-btn"
      >📝 Files {artifactsCount}</button>
    {/if}
    <button
      class="rounded-md px-2 py-1 text-xs {editorOpen ? 'bg-emerald-500/20 text-emerald-300' : 'text-neutral-400 hover:bg-neutral-800 hover:text-neutral-100'}"
      onclick={() => editorOpen = !editorOpen}
      data-testid="editor-toggle-btn"
    >📂 Code{editedFiles.length > 0 ? ` ${editedFiles.length}` : ''}</button>
    <button
      class="rounded-md px-2 py-1 text-xs {statePanelOpen ? 'bg-emerald-500/20 text-emerald-300' : 'text-neutral-400 hover:bg-neutral-800 hover:text-neutral-100'}"
      onclick={() => (statePanelOpen = !statePanelOpen)}
      data-testid="state-panel-toggle"
      title="STATE.md viewer"
    >📋 State</button>
    <div class="relative">
      <button
        class="rounded-md px-2 py-1 text-xs text-neutral-400 hover:bg-neutral-800 hover:text-neutral-100"
        onclick={() => (exportMenuOpen = !exportMenuOpen)}
        title="Export conversation"
        data-testid="export-btn"
      >⇩ Export</button>
      {#if exportMenuOpen}
        <div class="absolute right-0 top-full z-30 mt-1 w-44 rounded-lg border border-neutral-800 bg-neutral-950 p-1 shadow-xl" role="menu" data-testid="export-menu">
          <button
            class="block w-full rounded-md px-2 py-1.5 text-left text-xs text-neutral-200 hover:bg-neutral-900"
            onclick={() => { exportMenuOpen = false; exportMarkdown() }}
            data-testid="export-md"
          >📝 Markdown (.md)</button>
          <button
            class="block w-full rounded-md px-2 py-1.5 text-left text-xs text-neutral-200 hover:bg-neutral-900"
            onclick={() => { exportMenuOpen = false; exportJson() }}
            data-testid="export-json"
          >🧾 JSON (.json)</button>
        </div>
      {/if}
    </div>
    <button
      class="rounded-md px-2 py-1 text-xs text-neutral-400 hover:bg-neutral-800 hover:text-neutral-100 disabled:opacity-50"
      onclick={openHistory}
      disabled={pending}
      data-testid="history-btn"
    >History</button>
    <button
      class="rounded-md px-2 py-1 text-xs text-neutral-400 hover:bg-neutral-800 hover:text-neutral-100"
      onclick={newConvo}
      disabled={pending}
      data-testid="new-convo-btn"
    >New</button>
  </header>

  <!-- messages -->
  <div bind:this={scroller} onscroll={onScroll} class="relative flex-1 overflow-y-auto px-3 py-3" data-testid="messages">
    {#if loadingMessages}
      <ul class="mx-auto flex max-w-2xl flex-col gap-3" data-testid="loading">
        {#each Array(4) as _, i (i)}
          <li class="flex {i % 2 === 0 ? 'justify-end' : 'justify-start'}">
            <div class="max-w-[88%] space-y-1.5 rounded-2xl border border-neutral-800 bg-neutral-900/60 px-3 py-2.5">
              <div class="h-2.5 w-40 animate-pulse rounded bg-neutral-800"></div>
              <div class="h-2 w-56 animate-pulse rounded bg-neutral-800/70"></div>
              <div class="h-2 w-24 animate-pulse rounded bg-neutral-800/50"></div>
            </div>
          </li>
        {/each}
      </ul>
    {:else if messages.length === 0}
      <div class="mx-auto mt-12 max-w-2xl">
        <div class="mb-6 text-center">
          <div class="mb-2 text-4xl">💬</div>
          <div class="text-sm font-medium text-neutral-200">Mulai percakapan dengan {projectDisplayName}</div>
          <div class="mt-1 text-xs text-neutral-500">Tools aktif: 🖥️ bash · 📖 read · ✏️ edit · 🌐 fetch · 🎭 playwright</div>
        </div>
        <div class="grid gap-2 sm:grid-cols-3" data-testid="suggested-prompts">
          {#each SUGGESTED_PROMPTS as s}
            <button
              class="rounded-xl border border-neutral-800 bg-neutral-900/60 p-3 text-left text-xs text-neutral-300 transition hover:border-emerald-500/40 hover:bg-neutral-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500"
              onclick={() => applySuggestion(s.text)}
              data-testid="suggested-prompt"
            >
              <div class="mb-1 font-medium text-neutral-100">{s.label}</div>
              <div class="line-clamp-2 text-neutral-400">{s.text}</div>
            </button>
          {/each}
        </div>
        <div class="mt-4 text-center text-[11px] text-neutral-600">
          Tekan <kbd class="rounded border border-neutral-700 bg-neutral-800 px-1.5 py-0.5">?</kbd> untuk lihat shortcut keyboard
        </div>
      </div>
    {/if}
    <ul class="mx-auto flex max-w-2xl flex-col gap-3">
      {#each messages as m, i (i)}
        {@const isLast = i === messages.length - 1}
        {@const isLastUser = i === lastUserIdx}
        <li class="msg-in flex {m.role === 'user' ? 'justify-end' : m.role === 'system_note' ? 'justify-center' : 'justify-start'}">
          {#if m.role === 'system_note'}
            <div class="rounded-full border border-amber-500/30 bg-amber-500/10 px-3 py-1 text-[11px] text-amber-300">
              ↻ {m.text}
            </div>
          {:else}
            <div class="max-w-[88%] rounded-2xl px-3.5 py-2.5 text-sm shadow-sm {m.role === 'user' ? 'bg-gradient-to-br from-blue-600 to-blue-700 text-white ring-1 ring-blue-500/30' : 'border border-neutral-800 bg-neutral-900/80 backdrop-blur-sm'}">
              {#if m.role === 'user'}
                {#if m.retry}
                  <div class="mb-1 text-[10px] uppercase tracking-wide text-blue-200/70">retry (elevated)</div>
                {/if}
                {#if m.uploads?.length}
                  <div class="mb-1 flex flex-wrap gap-1">
                    {#each m.uploads as u}
                      <img src={u.dataUrl || u.url} alt="" class="h-20 w-20 rounded object-cover border border-blue-400/30" />
                    {/each}
                  </div>
                {/if}
                {#if editingMsgIdx === i}
                  <textarea
                    bind:value={editingText}
                    rows="3"
                    class="block w-full min-w-[260px] rounded-md border border-blue-300/40 bg-blue-700/40 px-2 py-1 text-sm text-white focus:outline-none"
                    onkeydown={(e) => {
                      if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); saveEditAndResend() }
                      if (e.key === 'Escape') { e.preventDefault(); cancelEditMessage() }
                    }}
                    data-testid="edit-textarea-{i}"
                  ></textarea>
                  <div class="mt-1 flex gap-1.5">
                    <button class="rounded-md bg-blue-300/20 px-2 py-0.5 text-[10px] text-blue-100 hover:bg-blue-300/30" onclick={saveEditAndResend} data-testid="edit-save-{i}">Save & resend (⌘↵)</button>
                    <button class="rounded-md px-2 py-0.5 text-[10px] text-blue-200/70 hover:text-white" onclick={cancelEditMessage}>Cancel (Esc)</button>
                  </div>
                {:else}
                  <div class="group/msg relative whitespace-pre-wrap">
                    {m.text}
                    {#if !pending}
                      <button
                        class="absolute -top-2 -left-7 opacity-0 group-hover/msg:opacity-100 transition text-blue-200 hover:text-white text-xs"
                        onclick={() => startEditMessage(i, m)}
                        title="Edit & resend"
                        aria-label="Edit message"
                        data-testid="edit-msg-{i}"
                      >✎</button>
                    {/if}
                  </div>
                {/if}
                {#if isLastUser && pending}
                  <div class="mt-1 text-[10px] text-blue-200/80" data-testid="send-timer">
                    sending · {fmtSec(sendElapsedS)}{sinceLastEvtS > 5 ? ` · idle ${fmtSec(sinceLastEvtS)}` : ''}
                  </div>
                {/if}
              {:else}
                {#if m.toolUses?.length}
                  <div class="mb-2 space-y-1.5">
                    {#each m.toolUses as t}
                      <details class="rounded-md border border-neutral-700 bg-neutral-950/60 text-xs" data-testid="tool-card">
                        <summary class="cursor-pointer select-none px-2 py-1 text-neutral-300">
                          <span class="font-medium {toolColor(t.name)}">{toolDisplay(t.name)}</span>
                          <span class="ml-1 text-neutral-500">{JSON.stringify(t.input).slice(0, 80)}</span>
                          {#if t.result !== null && t.result !== undefined}
                            <span class="ml-1 rounded bg-neutral-800 px-1 text-[10px] text-neutral-400">{t.result.length}b</span>
                          {/if}
                        </summary>
                        <div class="border-t border-neutral-800 px-2 py-1.5">
                          <div class="text-[10px] uppercase tracking-wide text-neutral-500">input</div>
                          <pre>{JSON.stringify(t.input, null, 2)}</pre>
                          {#if t.result !== null && t.result !== undefined}
                            <div class="mt-1 text-[10px] uppercase tracking-wide text-neutral-500">output</div>
                            <pre>{t.result?.slice?.(0, 4000) ?? ''}</pre>
                          {/if}
                        </div>
                      </details>
                      {#if t.name === 'mcp__browser-agent__browse_autonomous'}
                        <BrowserViewer
                          input={t.input}
                          streamStartedAtMs={myStream?.startedAt || 0}
                          streaming={m.streaming}
                        />
                      {/if}
                    {/each}
                  </div>
                {/if}
                {#if m.text}
                  <div class="chat-md" use:withCopyButtons>{@html safeMarked(m.text)}</div>
                {/if}
                {#if m.streaming}
                  {#if !m.text}
                    <div class="flex items-center gap-1.5 py-1" data-testid="typing-dots" aria-label="thinking">
                      <span class="h-2 w-2 animate-bounce rounded-full bg-emerald-400" style="animation-delay:0ms;animation-duration:1.05s"></span>
                      <span class="h-2 w-2 animate-bounce rounded-full bg-emerald-400" style="animation-delay:160ms;animation-duration:1.05s"></span>
                      <span class="h-2 w-2 animate-bounce rounded-full bg-emerald-400" style="animation-delay:320ms;animation-duration:1.05s"></span>
                    </div>
                  {:else}
                    <span class="stream-cursor" aria-hidden="true"></span>
                  {/if}
                  <div class="mt-1 flex items-center gap-1.5 text-[10px] text-emerald-400/80" data-testid="agent-timer">
                    <svg class="h-3 w-3 animate-spin" viewBox="0 0 24 24" fill="none">
                      <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
                      <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"/>
                    </svg>
                    <span>{m.text ? 'writing' : 'thinking'} · {fmtSec(sendElapsedS)}{sinceLastEvtS > 5 ? ` · idle ${fmtSec(sinceLastEvtS)}` : ''}</span>
                  </div>
                {/if}
                {#if !m.streaming && m.cost != null}
                  <div class="mt-1 flex items-center justify-between text-[10px] text-neutral-500">
                    <span>{m.durationMs}ms · ${m.cost?.toFixed(4)}</span>
                    <button
                      class="text-sm leading-none transition {isStarred(uiPrefs, activeSessionId, i) ? 'text-amber-300' : 'opacity-30 hover:opacity-100 hover:text-amber-300'}"
                      onclick={() => toggleStar(activeSessionId, i)}
                      title={isStarred(uiPrefs, activeSessionId, i) ? 'Unstar' : 'Star this reply'}
                      aria-label="Star this reply"
                      data-testid="star-msg-{i}"
                    >{isStarred(uiPrefs, activeSessionId, i) ? '★' : '☆'}</button>
                  </div>
                {/if}
              {/if}
            </div>
          {/if}
        </li>
      {/each}
    </ul>

    {#if error}
      <div class="mx-auto mt-3 max-w-2xl rounded-md border border-red-500/40 bg-red-500/10 p-2 text-xs text-red-300" data-testid="chat-error-banner">
        {error}
      </div>
    {/if}

    {#if silentlyStopped}
      <div class="mx-auto mt-3 flex max-w-2xl items-center justify-between gap-3 rounded-md border border-orange-500/40 bg-orange-500/10 p-3 text-xs text-orange-200" data-testid="silent-stop-banner">
        <div class="min-w-0">
          <div class="font-medium text-orange-100">⚠️ Berhenti tanpa closure</div>
          <div class="text-orange-300/80">
            Respons terakhir pake tools tapi gak ada STATUS blok. Kemungkinan claude berhenti tanpa kasih ringkasan akhir.
            Klik "Minta recap" → input akan diisi prompt yg force claude kasih recap + STATUS proper.
          </div>
        </div>
        <div class="flex shrink-0 gap-1.5">
          <button
            class="rounded-md border border-orange-400/40 bg-orange-500/15 px-2.5 py-1 font-medium hover:bg-orange-500/25"
            onclick={requestRecap}
            data-testid="silent-stop-recap-btn"
          >Minta recap</button>
        </div>
      </div>
    {/if}

    {#if streamStuck}
      <div class="mx-auto mt-3 flex max-w-2xl items-center justify-between gap-3 rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-xs text-amber-200" data-testid="stuck-banner">
        <div class="min-w-0">
          <div class="font-medium text-amber-100">⚠️ Looks stuck</div>
          <div class="text-amber-300/80">
            Streaming udah {sinceLastEvtS}s gak ada event baru. Mungkin koneksi putus diam-diam.
            Reply sebenernya mungkin udah ada di disk — tap Refresh.
          </div>
        </div>
        <div class="flex shrink-0 gap-1.5">
          <button
            class="rounded-md border border-amber-400/40 bg-amber-500/15 px-2.5 py-1 font-medium hover:bg-amber-500/25"
            onclick={() => refreshFromDisk()}
            data-testid="stuck-refresh-btn"
          >Refresh</button>
          <button
            class="rounded-md border border-amber-400/40 bg-amber-500/15 px-2.5 py-1 font-medium hover:bg-amber-500/25"
            onclick={abortStuck}
            data-testid="stuck-abort-btn"
          >Abort</button>
        </div>
      </div>
    {/if}

    {#if staleMessage}
      <div class="mx-auto mt-3 flex max-w-2xl items-center justify-between gap-3 rounded-md border border-emerald-500/40 bg-emerald-500/10 p-3 text-xs text-emerald-200" data-testid="stale-retry-banner">
        <div class="min-w-0">
          <div class="font-medium text-emerald-100">Pesan terakhir aborted</div>
          <div class="truncate text-emerald-300/80">"{staleMessage.slice(0, 100)}{staleMessage.length > 100 ? '…' : ''}"</div>
        </div>
        <div class="flex shrink-0 gap-1.5">
          <button
            class="rounded-md border border-emerald-400/40 bg-emerald-500/15 px-2.5 py-1 font-medium hover:bg-emerald-500/25"
            onclick={retryStuck}
            data-testid="stale-retry-btn"
          >Kirim ulang</button>
          <button
            class="rounded-md px-2.5 py-1 text-emerald-300/70 hover:text-emerald-200"
            onclick={() => (staleMessage = null)}
            data-testid="stale-dismiss-btn"
          >Dismiss</button>
        </div>
      </div>
    {/if}

    <CheckpointTimeline streamId={myStream?.streamId} onRewound={() => refreshFromDisk()} />
  </div>

  {#if scrolledUp}
    <button
      class="fixed bottom-24 right-6 z-30 grid h-10 w-10 place-items-center rounded-full border border-neutral-700 bg-neutral-900/95 text-neutral-200 shadow-lg backdrop-blur transition hover:border-emerald-500/50 hover:text-emerald-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 md:bottom-28"
      onclick={jumpToLatest}
      data-testid="scroll-to-latest"
      title="Scroll to latest (End)"
      aria-label="Scroll to latest message"
    >
      <svg viewBox="0 0 24 24" class="h-5 w-5" fill="none" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M19 14l-7 7-7-7M12 4v16"/></svg>
    </button>
  {/if}

  <!-- input -->
  <div class="border-t border-neutral-800 bg-neutral-950/80 px-3 py-2 pb-[max(0.5rem,env(safe-area-inset-bottom))] backdrop-blur-md">
    {#if slashOpen}
      <div class="mx-auto mb-2 max-w-2xl rounded-xl border border-neutral-800 bg-neutral-950 p-1.5 shadow-xl" data-testid="slash-menu">
        <div class="px-2 pb-1 text-[10px] uppercase tracking-wide text-neutral-500">Slash commands · Tab to insert</div>
        <ul>
          {#each slashMatches as c, i (c.cmd)}
            <li>
              <button
                class="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs transition {i === slashIdx ? 'bg-emerald-500/10 text-emerald-100' : 'text-neutral-300 hover:bg-neutral-900'}"
                onclick={() => pickSlash(c)}
                onmouseenter={() => (slashIdx = i)}
                data-testid="slash-{c.cmd.slice(1)}"
              >
                <span class="font-mono text-emerald-400">{c.cmd}</span>
                <span class="flex-1 truncate text-neutral-300">{c.label}</span>
                {#if i === slashIdx}
                  <kbd class="rounded border border-emerald-500/40 bg-emerald-500/10 px-1 text-[10px] text-emerald-300">⇥</kbd>
                {/if}
              </button>
            </li>
          {/each}
        </ul>
      </div>
    {/if}
    {#if uploads.length}
      <div class="mx-auto mb-2 flex max-w-2xl flex-wrap gap-2" data-testid="upload-previews">
        {#each uploads as u, i (u.filename)}
          <div class="relative">
            <img src={u.dataUrl} alt="upload" class="h-16 w-16 rounded-md object-cover border border-neutral-700" />
            <button class="absolute -right-1 -top-1 grid h-5 w-5 place-items-center rounded-full bg-red-600 text-[10px] text-white" onclick={() => removeUpload(i)} aria-label="Remove upload">✕</button>
          </div>
        {/each}
      </div>
    {/if}
    <div class="mx-auto flex max-w-2xl items-end gap-2 rounded-2xl border border-neutral-800 bg-neutral-900/70 p-1.5 transition focus-within:border-emerald-600/40 focus-within:bg-neutral-900">
      <label class="inline-flex h-9 cursor-pointer items-center rounded-lg px-2 text-sm text-neutral-400 transition hover:bg-neutral-800 hover:text-neutral-200" title="Attach image">
        <span class="text-base">📎</span>
        <input type="file" accept="image/png,image/jpeg,image/webp,image/gif" class="hidden" onchange={onFilePick} data-testid="file-input" />
      </label>
      <VoiceInput onTranscript={appendVoice} />
      <textarea
        rows="1"
        bind:value={input}
        onkeydown={onKey}
        onpaste={onPaste}
        placeholder="Message {projectDisplayName}… (⏎ kirim, ⇧⏎ baris baru)"
        class="block max-h-48 flex-1 resize-none bg-transparent px-2 py-2 text-base placeholder-neutral-500 focus:outline-none"
        disabled={pending}
        data-testid="chat-input"
      ></textarea>
      {#if pending}
        <button
          class="grid h-9 shrink-0 place-items-center rounded-lg bg-red-600 px-3 text-sm text-white transition hover:bg-red-500 focus-visible:ring-2 focus-visible:ring-red-400"
          onclick={stop}
          data-testid="stop-btn"
          aria-label="Stop generation"
        >
          <svg viewBox="0 0 24 24" class="h-4 w-4" fill="currentColor"><rect x="6" y="6" width="12" height="12" rx="2"/></svg>
        </button>
      {:else}
        <button
          class="group grid h-9 shrink-0 place-items-center rounded-lg bg-gradient-to-br from-emerald-500 to-emerald-700 px-3 text-sm font-medium text-white shadow transition hover:from-emerald-400 hover:to-emerald-600 focus-visible:ring-2 focus-visible:ring-emerald-400 disabled:from-neutral-800 disabled:to-neutral-800 disabled:text-neutral-500 disabled:shadow-none"
          onclick={send}
          disabled={!input.trim()}
          data-testid="send-btn"
          aria-label="Send message"
        >
          <svg viewBox="0 0 24 24" class="h-4 w-4 transition group-hover:translate-x-0.5 group-disabled:translate-x-0" fill="none" stroke="currentColor" stroke-width="2.5">
            <path stroke-linecap="round" stroke-linejoin="round" d="M5 12h14M13 6l6 6-6 6"/>
          </svg>
        </button>
      {/if}
    </div>
    <!-- Status footer: tokens, cost, model -->
    <div class="mx-auto mt-1.5 flex max-w-2xl items-center justify-between gap-3 px-1 text-[10px] text-neutral-600" data-testid="composer-status">
      <span class="flex items-center gap-2">
        {#if pending}
          <span class="inline-flex items-center gap-1 text-emerald-400">
            <span class="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-400"></span>
            streaming · {fmtSec(sendElapsedS)}
          </span>
        {:else}
          <span>claude-opus-4-7</span>
        {/if}
        {#if sessionTurns > 0}
          <span class="rounded bg-neutral-900 px-1.5 py-0.5 text-emerald-300/80" data-testid="session-cost">
            session · {sessionTurns} turn{sessionTurns === 1 ? '' : 's'} · ${sessionCost.toFixed(4)}
          </span>
        {/if}
      </span>
      <span class="flex items-center gap-3">
        <span>{input.length} chars</span>
        {#if uiPrefs.savedPrompts.length > 0}
          <button
            class="rounded border border-neutral-800 px-1.5 py-0.5 transition hover:border-emerald-700/60 hover:text-emerald-300"
            onclick={() => (promptPickerOpen = !promptPickerOpen)}
            title="Saved prompts"
            data-testid="prompts-picker-btn"
          >📝 {uiPrefs.savedPrompts.length}</button>
        {/if}
        <span class="hidden sm:inline">⌘K palette · ? shortcuts</span>
      </span>
    </div>
    {#if promptPickerOpen && uiPrefs.savedPrompts.length > 0}
      <div class="mx-auto mt-2 max-w-2xl rounded-xl border border-neutral-800 bg-neutral-950 p-2 shadow-xl" data-testid="prompts-picker">
        <div class="mb-1 px-1 text-[10px] uppercase tracking-wide text-neutral-500">Saved prompts</div>
        <ul class="space-y-1">
          {#each uiPrefs.savedPrompts as p (p.id)}
            <li>
              <button
                class="block w-full rounded-md px-2 py-1.5 text-left text-xs text-neutral-200 transition hover:bg-emerald-500/10 hover:text-emerald-100"
                onclick={() => pickSavedPrompt(p)}
                data-testid="saved-prompt-{p.id}"
              >
                <div class="font-medium">{p.label}</div>
                <div class="truncate text-[10px] text-neutral-500">{p.text}</div>
              </button>
            </li>
          {/each}
        </ul>
      </div>
    {/if}
  </div>
</div>

<!-- approval modal --->
{#if approval}
  <div class="fixed inset-0 z-[60] flex items-center justify-center bg-black/70 p-4" data-testid="approval-modal">
    <div class="w-full max-w-md rounded-2xl border border-amber-500/40 bg-neutral-950 p-4 shadow-xl">
      <div class="mb-2 flex items-center gap-2 text-amber-300">
        <span class="text-lg">⚠</span>
        <span class="font-medium">Permission required</span>
      </div>
      <p class="mb-3 text-sm text-neutral-300">
        Claude tried to do something that the auto-mode classifier blocked. Approve and retry with elevated permissions?
      </p>
      <div class="mb-3 max-h-48 space-y-1.5 overflow-y-auto rounded-md border border-neutral-800 bg-neutral-950/60 p-2 text-xs">
        {#each approval.denials as d}
          <div>
            <span class="font-medium text-amber-300">{d.tool_name || d.toolName || 'tool'}</span>
            {#if d.tool_input || d.toolInput}
              <pre class="mt-1">{JSON.stringify(d.tool_input || d.toolInput, null, 2).slice(0, 400)}</pre>
            {/if}
            {#if d.reason}
              <div class="mt-1 text-neutral-400">{d.reason}</div>
            {/if}
          </div>
        {/each}
        {#if approval.denials.length === 0}
          <div class="text-neutral-500">(no denial details)</div>
        {/if}
      </div>
      <div class="flex gap-2">
        <button class="flex-1 rounded-lg bg-neutral-800 px-3 py-2 text-sm text-neutral-200 hover:bg-neutral-700" onclick={denyApproval} data-testid="deny-btn">Deny</button>
        <button class="flex-1 rounded-lg bg-amber-600 px-3 py-2 text-sm font-medium text-white hover:bg-amber-500" onclick={approveAndRetry} data-testid="approve-btn">Approve & retry</button>
      </div>
    </div>
  </div>
{/if}

{#if artifactsOpen && myStream?.streamId}
  <ArtifactsPanel
    streamId={myStream.streamId}
    onClose={() => (artifactsOpen = false)}
  />
{/if}

{#if editorOpen}
  <div class="fixed inset-0 z-30 bg-black/40" onclick={() => editorOpen = false} role="presentation"></div>
  <aside class="fixed inset-y-0 right-0 z-40 w-[min(720px,95vw)]" data-testid="editor-drawer">
    <EditorPane
      projectId={project.id}
      path={editorPath}
      recentlyEditedFiles={editedFiles}
      onClose={() => editorOpen = false}
    />
  </aside>
{/if}

<StatePanel
  projectId={project.id}
  open={statePanelOpen}
  onClose={() => (statePanelOpen = false)}
/>

<!-- history drawer -->
{#if historyOpen}
  <div class="fixed inset-0 z-40 bg-black/60" onclick={() => (historyOpen = false)} role="presentation" data-testid="history-overlay"></div>
  <aside class="fixed inset-y-0 right-0 z-50 flex w-[min(420px,90vw)] flex-col border-l border-neutral-800 bg-neutral-950 shadow-xl" data-testid="history-drawer">
    <div class="flex items-center justify-between border-b border-neutral-800 px-4 py-3">
      <div class="font-medium">History · {project.name}</div>
      <button class="text-neutral-400 hover:text-neutral-100" onclick={() => (historyOpen = false)}>✕</button>
    </div>
    <div class="flex-1 overflow-y-auto p-3">
      {#if historyLoading}
        <div class="text-sm text-neutral-500">Loading…</div>
      {:else if history.length === 0}
        <div class="text-sm text-neutral-500">No saved sessions yet.</div>
      {:else}
        <ul class="space-y-2">
          {#each history as h (h.session_id)}
            <li>
              <button
                class="block w-full rounded-lg border border-neutral-800 bg-neutral-900 px-3 py-2 text-left hover:border-neutral-700 hover:bg-neutral-800/70 {h.session_id === activeSessionId ? 'border-blue-500/60' : ''}"
                onclick={() => pickSession(h.session_id)}
                data-testid="session-item-{h.session_id}"
              >
                <div class="line-clamp-2 text-sm">{h.first_user_message}</div>
                <div class="mt-1 flex items-center justify-between text-[10px] text-neutral-500">
                  <span>{fmtTime(h.last_modified)}</span>
                  <span>{h.message_count} msgs · {h.session_id.slice(0, 8)}</span>
                </div>
              </button>
            </li>
          {/each}
        </ul>
      {/if}
    </div>
  </aside>
{/if}

<!-- Keyboard shortcuts overlay (press `?`) -->
{#if shortcutsOpen}
  <div class="fixed inset-0 z-[70] flex items-center justify-center bg-black/70 p-4" onclick={() => (shortcutsOpen = false)} role="presentation" data-testid="shortcuts-overlay">
    <div class="w-full max-w-md rounded-2xl border border-neutral-800 bg-neutral-950 p-5 shadow-xl" onclick={(e) => e.stopPropagation()} role="presentation">
      <div class="mb-3 flex items-center justify-between">
        <div class="text-sm font-semibold text-neutral-100">⌨️ Keyboard shortcuts</div>
        <button class="text-neutral-500 hover:text-neutral-200" onclick={() => (shortcutsOpen = false)} aria-label="Close">✕</button>
      </div>
      <ul class="space-y-2 text-xs text-neutral-300">
        <li class="flex items-center justify-between"><span>Command palette</span><kbd class="rounded border border-neutral-700 bg-neutral-800 px-1.5 py-0.5">⌘ K</kbd></li>
        <li class="flex items-center justify-between"><span>Settings</span><kbd class="rounded border border-neutral-700 bg-neutral-800 px-1.5 py-0.5">⌘ ,</kbd></li>
        <li class="flex items-center justify-between"><span>Saved prompts picker</span><kbd class="rounded border border-neutral-700 bg-neutral-800 px-1.5 py-0.5">⌘ P</kbd></li>
        <li class="flex items-center justify-between"><span>Send message</span><kbd class="rounded border border-neutral-700 bg-neutral-800 px-1.5 py-0.5">⏎</kbd></li>
        <li class="flex items-center justify-between"><span>Save edit & resend</span><kbd class="rounded border border-neutral-700 bg-neutral-800 px-1.5 py-0.5">⌘ ⏎</kbd></li>
        <li class="flex items-center justify-between"><span>New line in composer</span><kbd class="rounded border border-neutral-700 bg-neutral-800 px-1.5 py-0.5">⇧ ⏎</kbd></li>
        <li class="flex items-center justify-between"><span>Toggle this dialog</span><kbd class="rounded border border-neutral-700 bg-neutral-800 px-1.5 py-0.5">?</kbd></li>
        <li class="flex items-center justify-between"><span>Close dialog / cancel edit</span><kbd class="rounded border border-neutral-700 bg-neutral-800 px-1.5 py-0.5">Esc</kbd></li>
        <li class="flex items-center justify-between"><span>Paste image</span><kbd class="rounded border border-neutral-700 bg-neutral-800 px-1.5 py-0.5">⌘ V</kbd></li>
      </ul>
      <div class="mt-3 text-[11px] text-neutral-500">Voice input: tap mic icon. Drag-paste images directly into composer.</div>
    </div>
  </div>
{/if}
