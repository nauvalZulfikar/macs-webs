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
  import ArtifactsPanel from './ArtifactsPanel.svelte'
  import BrowserViewer from './BrowserViewer.svelte'
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
      error = `❌ Gagal kirim: ${e.message}. Tap kirim lagi untuk retry.`
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
    if (myStream?.streamId) await abortStream(myStream.streamId)
  }

  function onKey(e) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() }
  }

  function appendVoice(t) {
    if (!t) return
    input = input ? `${input.trimEnd()} ${t}` : t
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
</script>

<div class="flex h-dvh flex-col bg-neutral-950">
  <!-- header -->
  <header class="flex items-center gap-2 border-b border-neutral-800 bg-neutral-950/80 px-3 py-3 backdrop-blur">
    <button
      class="rounded-md px-2 py-1 text-sm text-neutral-400 hover:bg-neutral-800 hover:text-neutral-100 md:hidden"
      onclick={onBack}
      data-testid="back-btn"
    >← Back</button>
    <div class="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-emerald-600/30 text-sm font-semibold text-emerald-200">
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
  <div bind:this={scroller} class="flex-1 overflow-y-auto px-3 py-3" data-testid="messages">
    {#if loadingMessages}
      <div class="mt-8 text-center text-sm text-neutral-500" data-testid="loading">Loading conversation…</div>
    {:else if messages.length === 0}
      <div class="mt-8 text-center text-sm text-neutral-500">Start a conversation. Hooks (RTK, MACS, route-prompt) are active.</div>
    {/if}
    <ul class="mx-auto flex max-w-2xl flex-col gap-3">
      {#each messages as m, i (i)}
        {@const isLast = i === messages.length - 1}
        {@const isLastUser = i === lastUserIdx}
        <li class="flex {m.role === 'user' ? 'justify-end' : m.role === 'system_note' ? 'justify-center' : 'justify-start'}">
          {#if m.role === 'system_note'}
            <div class="rounded-full border border-amber-500/30 bg-amber-500/10 px-3 py-1 text-[11px] text-amber-300">
              ↻ {m.text}
            </div>
          {:else}
            <div class="max-w-[88%] rounded-2xl px-3 py-2 text-sm {m.role === 'user' ? 'bg-blue-600 text-white' : 'border border-neutral-800 bg-neutral-900'}">
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
                <div class="whitespace-pre-wrap">{m.text}</div>
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
                  <div class="chat-md">{@html marked.parse(m.text)}</div>
                {/if}
                {#if m.streaming}
                  {#if !m.text}
                    <div class="flex items-center gap-1.5 py-1" data-testid="typing-dots" aria-label="thinking">
                      <span class="h-2 w-2 animate-bounce rounded-full bg-emerald-400" style="animation-delay:0ms;animation-duration:1s"></span>
                      <span class="h-2 w-2 animate-bounce rounded-full bg-emerald-400" style="animation-delay:150ms;animation-duration:1s"></span>
                      <span class="h-2 w-2 animate-bounce rounded-full bg-emerald-400" style="animation-delay:300ms;animation-duration:1s"></span>
                    </div>
                  {:else}
                    <span class="inline-block animate-pulse">▍</span>
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
                  <div class="mt-1 text-[10px] text-neutral-500">
                    {m.durationMs}ms · ${m.cost?.toFixed(4)}
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

  <!-- input -->
  <div class="border-t border-neutral-800 bg-neutral-950 px-3 py-2 pb-[max(0.5rem,env(safe-area-inset-bottom))]">
    {#if uploads.length}
      <div class="mx-auto mb-2 flex max-w-2xl flex-wrap gap-2" data-testid="upload-previews">
        {#each uploads as u, i (u.filename)}
          <div class="relative">
            <img src={u.dataUrl} alt="upload" class="h-16 w-16 rounded-md object-cover border border-neutral-700" />
            <button class="absolute -right-1 -top-1 grid h-5 w-5 place-items-center rounded-full bg-red-600 text-[10px] text-white" onclick={() => removeUpload(i)}>✕</button>
          </div>
        {/each}
      </div>
    {/if}
    <div class="mx-auto flex max-w-2xl items-end gap-2">
      <label class="inline-flex h-9 cursor-pointer items-center rounded-xl bg-neutral-800 px-2 text-sm text-neutral-300 hover:bg-neutral-700" title="Attach image">
        <span class="text-base">📎</span>
        <input type="file" accept="image/png,image/jpeg,image/webp,image/gif" class="hidden" onchange={onFilePick} data-testid="file-input" />
      </label>
      <VoiceInput onTranscript={appendVoice} />
      <textarea
        rows="1"
        bind:value={input}
        onkeydown={onKey}
        onpaste={onPaste}
        placeholder="Message {projectDisplayName}… (paste images, mic for voice)"
        class="block flex-1 resize-none rounded-xl border border-neutral-800 bg-neutral-900 px-3 py-2 text-base focus:border-neutral-600 focus:outline-none"
        disabled={pending}
        data-testid="chat-input"
      ></textarea>
      {#if pending}
        <button class="rounded-xl bg-red-600 px-3 py-2 text-sm text-white" onclick={stop} data-testid="stop-btn">Stop</button>
      {:else}
        <button
          class="rounded-xl bg-blue-600 px-3 py-2 text-sm text-white disabled:bg-neutral-700"
          onclick={send}
          disabled={!input.trim()}
          data-testid="send-btn"
        >Send</button>
      {/if}
    </div>
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
