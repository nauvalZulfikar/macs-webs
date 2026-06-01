<script>
  import { onMount, onDestroy } from 'svelte'
  import { listSessions, renameProject, renameSession } from './api.js'
  import { streams as streamsStore } from './streamsStore.svelte.js'
  import { missions as missionsStore, startPolling, stopPolling } from './missionsStore.svelte.js'
  import NewProjectModal from './NewProjectModal.svelte'

  let {
    projects = [],
    selectedProjectId = null,
    selectedSessionId = null,
    onPickProject,
    onPickSession,
    onProjectRenamed,
    onSessionRenamed,
    onProjectCreated,
    onLogout,
    onOpenMissionLauncher,
    onOpenMission,
    onOpenWatchers,
    onOpenNotify,
    onOpenCost,
    activeView = 'projects',
    activeMissionId = null,
  } = $props()

  let newProjectOpen = $state(false)

  onMount(() => startPolling())
  onDestroy(() => stopPolling())

  let missionsSnap = $state([])
  $effect(() => {
    const unsub = missionsStore.subscribe((v) => { missionsSnap = v })
    return unsub
  })

  let query = $state('')
  let expanded = $state(new Set())
  let sessionsByProject = $state({}) // pid -> session[]
  let loadingPid = $state(null)
  let editingProjectId = $state(null)
  let editingSessionId = $state(null) // composite "pid:sid"

  // Streams + ticker → per-project countdown
  let storeSnap = $state(new Map())
  $effect(() => {
    const unsub = streamsStore.subscribe((m) => { storeSnap = m })
    return unsub
  })
  let nowMs = $state(Date.now())
  $effect(() => {
    const t = setInterval(() => { nowMs = Date.now() }, 1000)
    return () => clearInterval(t)
  })

  let runningByProject = $derived.by(() => {
    const out = new Map()
    for (const s of storeSnap.values()) {
      if (s.done) continue
      const cur = out.get(s.projectId)
      if (!cur || s.startedAt < cur.startedAt) out.set(s.projectId, s)
    }
    return out
  })
  let totalRunning = $derived(runningByProject.size)

  function elapsedSec(stream) {
    return Math.max(0, Math.floor((nowMs - stream.startedAt) / 1000))
  }
  function fmtSec(s) {
    if (s < 60) return `${s}s`
    const m = Math.floor(s / 60), rem = s % 60
    return `${m}:${String(rem).padStart(2, '0')}`
  }

  function projectLabel(p) {
    return p.display_name || p.name
  }

  function sessionLabel(s) {
    return s.display_name || s.first_user_message || s.session_id.slice(0, 8)
  }

  function initial(label) {
    const c = (label || '?').trim().charAt(0).toUpperCase()
    return c || '?'
  }

  function avatarColor(label) {
    let h = 0
    for (const ch of label || '') h = (h * 31 + ch.charCodeAt(0)) % 360
    return `hsl(${h}, 45%, 35%)`
  }

  function relTime(ts) {
    if (!ts) return ''
    const now = Date.now() / 1000
    const d = now - ts
    if (d < 60) return 'now'
    if (d < 3600) return `${Math.floor(d / 60)}m`
    if (d < 86400) return `${Math.floor(d / 3600)}h`
    if (d < 86400 * 7) return `${Math.floor(d / 86400)}d`
    const dt = new Date(ts * 1000)
    return dt.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
  }

  async function ensureSessions(pid) {
    if (sessionsByProject[pid]) return
    loadingPid = pid
    try {
      const data = await listSessions(pid)
      sessionsByProject = { ...sessionsByProject, [pid]: data }
    } catch (e) {
      sessionsByProject = { ...sessionsByProject, [pid]: [] }
    } finally {
      loadingPid = null
    }
  }

  async function clickProject(p) {
    const isOpen = expanded.has(p.id)
    if (isOpen) {
      const next = new Set(expanded); next.delete(p.id); expanded = next
    } else {
      const next = new Set(expanded); next.add(p.id); expanded = next
      await ensureSessions(p.id)
    }
    const sessions = sessionsByProject[p.id] || []
    const top = sessions[0]
    onPickProject?.(p, top || null)
  }

  function clickSession(p, s) {
    onPickSession?.(p, s)
  }

  function startEditProject(p, e) {
    e.stopPropagation()
    editingProjectId = p.id
  }

  function startEditSession(p, s, e) {
    e.stopPropagation()
    editingSessionId = `${p.id}:${s.session_id}`
  }

  async function commitProjectRename(p, ev) {
    const value = ev.target.value.trim()
    editingProjectId = null
    const newName = value || null
    const current = p.display_name || null
    if (newName === current) return
    try {
      await renameProject(p.id, newName)
      onProjectRenamed?.(p.id, newName)
    } catch (e) {
      console.error(e)
    }
  }

  async function commitSessionRename(p, s, ev) {
    const value = ev.target.value.trim()
    editingSessionId = null
    const newName = value || null
    if (newName === (s.display_name || null)) return
    try {
      await renameSession(p.id, s.session_id, newName)
      const list = (sessionsByProject[p.id] || []).map((x) =>
        x.session_id === s.session_id ? { ...x, display_name: newName } : x
      )
      sessionsByProject = { ...sessionsByProject, [p.id]: list }
      onSessionRenamed?.(p.id, s.session_id, newName)
    } catch (e) {
      console.error(e)
    }
  }

  function onEditKey(ev) {
    if (ev.key === 'Enter') ev.target.blur()
    if (ev.key === 'Escape') {
      editingProjectId = null
      editingSessionId = null
    }
  }

  function focusInput(node) {
    node.focus()
    if (typeof node.select === 'function') node.select()
    return {}
  }

  let filteredProjects = $derived(
    query.trim()
      ? projects.filter((p) =>
          projectLabel(p).toLowerCase().includes(query.trim().toLowerCase())
        )
      : projects
  )
  let webPrtflProjects = $derived(filteredProjects.filter((p) => p.category === 'web_prtfl'))
  let otherProjects = $derived(filteredProjects.filter((p) => p.category !== 'web_prtfl'))
</script>

<aside class="flex h-dvh flex-col border-r border-neutral-800 bg-neutral-950">
  <!-- Header -->
  <div class="flex items-center justify-between border-b border-neutral-800 px-3 py-3">
    <div class="flex items-center gap-2">
      <div class="grid h-8 w-8 place-items-center rounded-full bg-emerald-600/30 text-sm font-semibold text-emerald-300">M</div>
      <div>
        <div class="text-sm font-semibold">MACS</div>
        <div class="text-[10px] text-neutral-500">Multi-Agent Orchestration</div>
      </div>
    </div>
    <div class="flex items-center gap-2">
      {#if totalRunning > 0}
        <span class="inline-flex items-center gap-1 rounded-full bg-emerald-500/15 px-2 py-0.5 text-[10px] text-emerald-300" data-testid="global-running-badge">
          <span class="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-400"></span>
          {totalRunning} running
        </span>
      {/if}
      <button class="text-base hover:opacity-70" onclick={onOpenCost} title="Cost dashboard" data-testid="open-cost">💸</button>
      <button class="text-base hover:opacity-70" onclick={onOpenNotify} title="Push notifications" data-testid="open-notify">📲</button>
      <button
        class="rounded-md px-2 py-1 text-xs text-neutral-400 hover:bg-neutral-800 hover:text-neutral-100"
        onclick={onLogout}
        data-testid="logout-btn"
      >Logout</button>
    </div>
  </div>

  <!-- Mission launcher + Watchers -->
  <div class="grid grid-cols-2 gap-2 border-b border-neutral-800 px-3 py-2">
    <button
      class="flex items-center justify-center gap-1 rounded-lg border border-emerald-500/40 bg-emerald-500/10 px-2 py-2 text-sm text-emerald-300 hover:bg-emerald-500/20"
      onclick={onOpenMissionLauncher}
      data-testid="open-mission-launcher"
    >
      <span>🚀</span>
      <span>Mission</span>
    </button>
    <button
      class="flex items-center justify-center gap-1 rounded-lg border border-amber-500/40 bg-amber-500/10 px-2 py-2 text-sm text-amber-300 hover:bg-amber-500/20"
      onclick={onOpenWatchers}
      data-testid="open-watchers"
    >
      <span>🔔</span>
      <span>Watchers</span>
    </button>
  </div>

  <!-- Active missions list -->
  {#if missionsSnap.length > 0}
    <div class="border-b border-neutral-800 bg-neutral-950/60 px-2 py-1.5">
      <div class="px-1 pb-1 text-[10px] uppercase tracking-wide text-neutral-500">Missions</div>
      {#each missionsSnap as m (m.mission_id)}
        {@const sel = activeView === 'mission' && activeMissionId === m.mission_id}
        <button
          class="mb-1 flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left transition hover:bg-neutral-900 {sel ? 'bg-neutral-900' : ''}"
          onclick={() => onOpenMission?.(m.mission_id)}
          data-testid="mission-row-{m.mission_id}"
        >
          <span class="text-base">🚀</span>
          <div class="min-w-0 flex-1">
            <div class="truncate text-xs font-medium text-neutral-200">{m.name}</div>
            <div class="text-[10px] text-neutral-500">
              {m.counts.done}/{m.total} done
              {#if m.counts.running > 0}· {m.counts.running} running{/if}
              {#if m.counts.error > 0}· <span class="text-red-400">{m.counts.error} err</span>{/if}
            </div>
          </div>
          {#if m.counts.running > 0}
            <span class="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-400"></span>
          {/if}
        </button>
      {/each}
    </div>
  {/if}

  <!-- Search + New Project -->
  <div class="flex items-center gap-2 border-b border-neutral-800 px-3 py-2">
    <input
      type="text"
      placeholder="Search project…"
      bind:value={query}
      class="flex-1 rounded-lg border border-neutral-800 bg-neutral-900 px-3 py-2 text-sm focus:border-emerald-600/60 focus:outline-none"
      data-testid="search-input"
    />
    <button
      class="shrink-0 rounded-lg border border-emerald-500/40 bg-emerald-500/10 px-3 py-2 text-sm font-medium text-emerald-300 hover:bg-emerald-500/20"
      onclick={() => (newProjectOpen = true)}
      title="Create new project"
      data-testid="newproj-open"
    >+ New</button>
  </div>

  <!-- Project list -->
  <div class="flex-1 overflow-y-auto" data-testid="project-list">
    {#snippet projectRow(p)}
      {@const isOpen = expanded.has(p.id)}
      {@const isSelected = p.id === selectedProjectId}
      {@const running = runningByProject.get(p.id)}
      <div
        class="flex w-full cursor-pointer items-center gap-3 border-b border-neutral-900 px-3 py-2.5 transition hover:bg-neutral-900/60 {isSelected ? 'bg-neutral-900/40' : ''}"
        onclick={() => clickProject(p)}
        role="button"
        tabindex="0"
        data-testid="project-item-{p.id}"
      >
        <div
          class="grid h-10 w-10 shrink-0 place-items-center rounded-full text-sm font-semibold text-white"
          style="background:{avatarColor(projectLabel(p))}"
        >{initial(projectLabel(p))}</div>
        <div class="min-w-0 flex-1">
          <div class="flex items-center justify-between gap-2">
            {#if editingProjectId === p.id}
              <input
                value={p.display_name || ''}
                placeholder={p.name}
                onblur={(e) => commitProjectRename(p, e)}
                onkeydown={onEditKey}
                onclick={(e) => e.stopPropagation()}
                class="min-w-0 flex-1 rounded bg-neutral-800 px-1.5 py-0.5 text-sm focus:outline-none"
                data-testid="project-rename-input-{p.id}"
                use:focusInput
              />
            {:else}
              <div
                class="truncate text-sm font-medium text-neutral-100"
                ondblclick={(e) => startEditProject(p, e)}
                title="Double-click to rename"
              >{projectLabel(p)}</div>
            {/if}
            {#if running}
              <span class="inline-flex shrink-0 items-center gap-1 rounded-full bg-emerald-500/15 px-1.5 py-0.5 text-[10px] text-emerald-300" data-testid="project-running-{p.id}">
                <span class="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-400"></span>
                {fmtSec(elapsedSec(running))}
              </span>
            {:else}
              <span class="shrink-0 text-[10px] text-neutral-500">{relTime(p.last_modified)}</span>
            {/if}
          </div>
          <div class="flex items-center justify-between gap-2">
            <div class="truncate text-xs text-neutral-500">
              {#if running}
                <span class="text-emerald-400/80">▶ {running.userMessage?.slice(0, 60) || 'running…'}</span>
              {:else}
                {p.last_message || p.path}
              {/if}
            </div>
            <div class="flex shrink-0 items-center gap-1">
              {#if p.session_count > 0}
                <span class="rounded bg-neutral-800 px-1.5 py-0.5 text-[10px] text-neutral-400">{p.session_count}</span>
              {/if}
              <span class="text-neutral-600 text-xs">{isOpen ? '▾' : '▸'}</span>
            </div>
          </div>
        </div>
      </div>

      {#if isOpen}
        <div class="border-b border-neutral-900 bg-neutral-950/70" data-testid="sessions-{p.id}">
          {#if loadingPid === p.id}
            <div class="px-12 py-2 text-xs text-neutral-500">Loading sessions…</div>
          {:else if (sessionsByProject[p.id] || []).length === 0}
            <div class="px-12 py-2 text-xs text-neutral-500">No sessions yet — start one</div>
          {:else}
            {#each sessionsByProject[p.id] as s (s.session_id)}
              {@const isSel = s.session_id === selectedSessionId && p.id === selectedProjectId}
              {@const editKey = `${p.id}:${s.session_id}`}
              <div
                class="flex cursor-pointer items-center gap-2 border-l-2 px-3 py-2 pl-12 transition hover:bg-neutral-900/80 {isSel ? 'border-emerald-500 bg-neutral-900' : 'border-transparent'}"
                onclick={() => clickSession(p, s)}
                role="button"
                tabindex="0"
                data-testid="session-item-{s.session_id}"
              >
                <div class="grid h-6 w-6 shrink-0 place-items-center rounded text-[10px] text-neutral-400">💬</div>
                <div class="min-w-0 flex-1">
                  {#if editingSessionId === editKey}
                    <input
                      value={s.display_name || ''}
                      placeholder={s.first_user_message?.slice(0, 50) || s.session_id.slice(0, 8)}
                      onblur={(e) => commitSessionRename(p, s, e)}
                      onkeydown={onEditKey}
                      onclick={(e) => e.stopPropagation()}
                      class="w-full rounded bg-neutral-800 px-1.5 py-0.5 text-xs focus:outline-none"
                      data-testid="session-rename-input-{s.session_id}"
                      use:focusInput
                    />
                  {:else}
                    <div
                      class="truncate text-xs text-neutral-200"
                      ondblclick={(e) => startEditSession(p, s, e)}
                      title="Double-click to rename"
                    >{sessionLabel(s)}</div>
                  {/if}
                  <div class="flex items-center justify-between gap-2 text-[10px] text-neutral-500">
                    <span class="truncate">{s.message_count} msgs</span>
                    <span>{relTime(s.last_modified)}</span>
                  </div>
                </div>
              </div>
            {/each}
          {/if}
        </div>
      {/if}
    {/snippet}

    {#if webPrtflProjects.length > 0}
      <div class="border-t border-neutral-900 bg-neutral-950/80 px-3 py-1.5 text-[10px] font-medium uppercase tracking-wider text-emerald-400/90" data-testid="group-header-web-prtfl">
        🌐 Session web_prtfl
      </div>
      {#each webPrtflProjects as p (p.id)}
        {@render projectRow(p)}
      {/each}
    {/if}

    {#if otherProjects.length > 0}
      {#if webPrtflProjects.length > 0}
        <div class="border-t border-neutral-900 bg-neutral-950/80 px-3 py-1.5 text-[10px] font-medium uppercase tracking-wider text-neutral-500" data-testid="group-header-other">
          All projects
        </div>
      {/if}
      {#each otherProjects as p (p.id)}
        {@render projectRow(p)}
      {/each}
    {/if}

    {#if filteredProjects.length === 0}
      <div class="px-3 py-6 text-center text-xs text-neutral-500">No projects match "{query}"</div>
    {/if}
  </div>

  <NewProjectModal
    open={newProjectOpen}
    onClose={() => (newProjectOpen = false)}
    onCreated={(res) => {
      newProjectOpen = false
      onProjectCreated?.(res)
    }}
  />
</aside>
