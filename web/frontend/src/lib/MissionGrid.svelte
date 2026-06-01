<script>
  import { onMount, onDestroy } from 'svelte'
  import { missions as missionsStore, startPolling, stopPolling, abortMission, archiveMission, getMission } from './missionsStore.svelte.js'
  import { streams as streamsStore } from './streamsStore.svelte.js'

  let { missionId = null, onClose, onFocusAgent, onPickProject } = $props()

  let detail = $state(null)
  let storeSnap = $state(new Map())
  let missionsSnap = $state([])
  let loading = $state(true)
  let error = $state(null)
  let tab = $state('grid') // 'grid' | 'scratchpad'
  let scratchpad = $state([])

  async function refreshScratchpad() {
    if (!missionId) return
    try {
      const r = await fetch(`/api/missions/${missionId}/scratchpad`)
      if (r.ok) scratchpad = await r.json()
    } catch {}
  }

  $effect(() => {
    const unsub = streamsStore.subscribe((m) => { storeSnap = m })
    return unsub
  })
  $effect(() => {
    const unsub = missionsStore.subscribe((v) => { missionsSnap = v })
    return unsub
  })

  let nowMs = $state(Date.now())
  $effect(() => {
    const t = setInterval(() => { nowMs = Date.now() }, 1000)
    return () => clearInterval(t)
  })

  async function refresh() {
    if (!missionId) return
    try {
      detail = await getMission(missionId)
    } catch (e) {
      error = e?.message || String(e)
    } finally {
      loading = false
    }
  }

  onMount(() => {
    startPolling()
    refresh()
    refreshScratchpad()
    const pollDetail = setInterval(() => { refresh(); refreshScratchpad() }, 4000)
    return () => clearInterval(pollDetail)
  })
  onDestroy(() => stopPolling())

  function streamFor(agent) {
    // Match by stream_id across the streams Map
    for (const s of storeSnap.values()) {
      if (s.streamId === agent.stream_id) return s
    }
    return null
  }

  function lastAssistantText(stream) {
    if (!stream) return ''
    for (let i = stream.events.length - 1; i >= 0; i--) {
      const e = stream.events[i]
      if (e.type === 'assistant' && e.message?.content) {
        const text = e.message.content
          .filter((b) => b.type === 'text')
          .map((b) => b.text)
          .join(' ')
        if (text) return text.slice(0, 200)
      }
    }
    return ''
  }

  function toolCount(stream) {
    if (!stream) return 0
    let n = 0
    for (const e of stream.events) {
      if (e.type === 'assistant' && e.message?.content) {
        for (const b of e.message.content) {
          if (b.type === 'tool_use') n++
        }
      }
    }
    return n
  }

  function statusColor(status, stream) {
    if (status === 'done') return 'bg-emerald-500'
    if (status === 'error') return 'bg-red-500'
    if (status === 'cancelled') return 'bg-neutral-500'
    if (stream?.reconnecting) return 'bg-amber-400'
    return 'bg-emerald-400 animate-pulse'
  }

  function elapsedSec(stream, agent) {
    if (stream) return Math.max(0, Math.floor((nowMs - stream.startedAt) / 1000))
    if (!agent.started_at) return 0
    const t = new Date(agent.started_at).getTime()
    return Math.max(0, Math.floor((nowMs - t) / 1000))
  }
  function fmtSec(s) {
    if (s < 60) return `${s}s`
    const m = Math.floor(s / 60), rem = s % 60
    return `${m}:${String(rem).padStart(2, '0')}`
  }

  function avatarColor(label) {
    let h = 0
    for (const ch of label || '') h = (h * 31 + ch.charCodeAt(0)) % 360
    return `hsl(${h}, 45%, 35%)`
  }

  async function onAbort() {
    if (!detail) return
    if (!confirm(`Abort mission "${detail.name}"? This will kill ${detail.counts.running || 0} running agents.`)) return
    await abortMission(detail.mission_id)
    await refresh()
  }
  async function onArchive() {
    if (!detail) return
    await archiveMission(detail.mission_id)
    onClose?.()
  }

  function focusAgent(agent) {
    onFocusAgent?.(agent)
  }
</script>

<div class="flex h-dvh flex-col bg-neutral-950">
  <header class="flex items-center gap-2 border-b border-neutral-800 bg-neutral-950/80 px-3 py-3 backdrop-blur">
    <button
      class="rounded-md px-2 py-1 text-sm text-neutral-400 hover:bg-neutral-800 hover:text-neutral-100"
      onclick={onClose}
      data-testid="mission-back"
    >← Back</button>
    <div class="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-emerald-600/30 text-lg">🚀</div>
    <div class="min-w-0 flex-1">
      <div class="flex items-center gap-2">
        <div class="truncate font-medium" data-testid="mission-title">{detail?.name || '...'}</div>
        {#if detail}
          <span class="rounded-full bg-emerald-500/20 px-2 py-0.5 text-[10px] text-emerald-300">
            {detail.counts.done}/{detail.total} done
          </span>
          {#if detail.counts.running > 0}
            <span class="rounded-full bg-emerald-500/20 px-2 py-0.5 text-[10px] text-emerald-300">{detail.counts.running} running</span>
          {/if}
          {#if detail.counts.error > 0}
            <span class="rounded-full bg-red-500/20 px-2 py-0.5 text-[10px] text-red-300">{detail.counts.error} error</span>
          {/if}
        {/if}
      </div>
      {#if detail?.shared_prompt}
        <div class="truncate text-xs text-neutral-500" data-testid="mission-prompt">{detail.shared_prompt}</div>
      {/if}
    </div>
    {#if detail && detail.counts.running > 0}
      <button class="rounded-md px-2 py-1 text-xs text-red-400 hover:bg-red-500/10" onclick={onAbort} data-testid="mission-abort">Abort</button>
    {/if}
    {#if detail && detail.counts.running === 0}
      <button class="rounded-md px-2 py-1 text-xs text-neutral-400 hover:bg-neutral-800 hover:text-neutral-100" onclick={onArchive} data-testid="mission-archive">Archive</button>
    {/if}
  </header>

  <!-- Tabs -->
  <div class="flex gap-1 border-b border-neutral-800 bg-neutral-950 px-3 py-1.5">
    <button class="rounded-md px-3 py-1 text-xs transition {tab === 'grid' ? 'bg-neutral-800 text-neutral-100' : 'text-neutral-500 hover:text-neutral-300'}"
      onclick={() => tab = 'grid'} data-testid="mission-tab-grid">⊞ Agents</button>
    <button class="rounded-md px-3 py-1 text-xs transition {tab === 'scratchpad' ? 'bg-neutral-800 text-neutral-100' : 'text-neutral-500 hover:text-neutral-300'}"
      onclick={() => tab = 'scratchpad'} data-testid="mission-tab-scratchpad">📝 Scratchpad {scratchpad.length > 0 ? `(${scratchpad.length})` : ''}</button>
    {#if detail?.mode === 'sequential'}
      <span class="ml-auto rounded-full bg-amber-500/15 px-2 py-0.5 text-[10px] text-amber-300">🔗 sequential</span>
    {/if}
  </div>

  <div class="flex-1 overflow-y-auto p-3">
    {#if loading}
      <div class="text-center text-sm text-neutral-500">Loading mission…</div>
    {:else if error}
      <div class="rounded-md border border-red-500/40 bg-red-500/10 p-3 text-xs text-red-300">{error}</div>
    {:else if detail && tab === 'scratchpad'}
      <div class="mx-auto max-w-3xl">
        {#if scratchpad.length === 0}
          <div class="rounded-lg border border-neutral-800 bg-neutral-900/60 p-4 text-center text-xs text-neutral-500">
            No scratchpad entries yet. {detail.mode === 'sequential' ? 'Each agent will post its findings here automatically as it completes.' : 'Run a sequential mission to see agents handoff context here.'}
          </div>
        {:else}
          <ul class="space-y-2">
            {#each scratchpad as n (n.id)}
              {@const agent = detail.agents.find((a) => a.agent_id === n.agent_id)}
              <li class="rounded-lg border border-neutral-800 bg-neutral-900/60 p-3" data-testid="scratchpad-entry-{n.id}">
                <div class="mb-1 flex items-center gap-2 text-[10px] text-neutral-500">
                  <span class="rounded bg-neutral-800 px-1.5 py-0.5 text-emerald-300">{agent?.label || n.author}</span>
                  <span>{new Date(n.created_at).toLocaleString()}</span>
                </div>
                <div class="whitespace-pre-wrap text-xs text-neutral-200">{n.text}</div>
              </li>
            {/each}
          </ul>
        {/if}
      </div>
    {:else if detail}
      <div class="mx-auto grid max-w-5xl gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {#each detail.agents as a (a.agent_id)}
          {@const stream = streamFor(a)}
          {@const txt = lastAssistantText(stream)}
          {@const tc = toolCount(stream)}
          <button
            type="button"
            class="text-left rounded-2xl border border-neutral-800 bg-neutral-900/60 p-3 transition hover:border-neutral-700 hover:bg-neutral-900"
            onclick={() => focusAgent(a)}
            data-testid="mission-tile-{a.agent_id}"
          >
            <div class="mb-2 flex items-center justify-between gap-2">
              <div class="flex min-w-0 items-center gap-2">
                <div
                  class="grid h-7 w-7 shrink-0 place-items-center rounded-full text-xs font-semibold text-white"
                  style="background:{avatarColor(a.label)}"
                >{(a.label || '?').charAt(0).toUpperCase()}</div>
                <div class="min-w-0">
                  <div class="truncate text-sm font-medium">{a.label}</div>
                  <div class="text-[10px] text-neutral-500">
                    {fmtSec(elapsedSec(stream, a))} · {a.events_count} evt · {tc} tools
                  </div>
                </div>
              </div>
              <span class="h-2.5 w-2.5 shrink-0 rounded-full {statusColor(a.status, stream)}" title={a.status}></span>
            </div>
            <div class="line-clamp-3 text-xs text-neutral-300" data-testid="mission-tile-{a.agent_id}-out">
              {#if txt}
                {txt}
              {:else if a.status === 'done'}
                <span class="text-neutral-500">(no response captured — re-open to load)</span>
              {:else}
                <span class="text-neutral-500">{a.message?.slice(0, 200) || '…'}</span>
              {/if}
            </div>
          </button>
        {/each}
      </div>
    {/if}
  </div>
</div>
