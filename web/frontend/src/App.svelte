<script>
  import { onMount } from 'svelte'
  import { authMe, authLogout, listProjects } from './lib/api.js'
  import { resumeActiveStreams } from './lib/streamsStore.svelte.js'
  import Sidebar from './lib/Sidebar.svelte'
  import Chat from './lib/Chat.svelte'
  import Login from './lib/Login.svelte'
  import MissionLauncher from './lib/MissionLauncher.svelte'
  import MissionGrid from './lib/MissionGrid.svelte'
  import WatchersPanel from './lib/WatchersPanel.svelte'
  import NotifyPanel from './lib/NotifyPanel.svelte'
  import CostDashboard from './lib/CostDashboard.svelte'
  import CommandPalette from './lib/CommandPalette.svelte'
  import ToastHost from './lib/ToastHost.svelte'
  import SettingsPanel from './lib/SettingsPanel.svelte'
  import { pushToast } from './lib/toastStore.svelte.js'
  import { settings, applyTheme } from './lib/settingsStore.svelte.js'

  // Apply theme on boot + on settings change + on OS scheme change
  let currentTheme = $state('auto')
  $effect(() => {
    const unsub = settings.subscribe((v) => { currentTheme = v.theme; applyTheme(v.theme) })
    return unsub
  })
  $effect(() => {
    if (currentTheme !== 'auto' || typeof window === 'undefined') return
    const mq = window.matchMedia('(prefers-color-scheme: light)')
    const handler = () => applyTheme('auto')
    mq.addEventListener('change', handler)
    return () => mq.removeEventListener('change', handler)
  })

  let authed = $state(null)
  let projects = $state([])
  let selectedProject = $state(null)
  let selectedSessionId = $state(null)
  let mobileChatOpen = $state(false)
  let view = $state('projects') // 'projects' | 'mission'
  let activeMissionId = $state(null)
  let launcherOpen = $state(false)
  let watchersOpen = $state(false)
  let notifyOpen = $state(false)
  let costOpen = $state(false)
  let paletteOpen = $state(false)
  let settingsOpen = $state(false)
  let compareProject = $state(null) // second pane project
  let compareSessionId = $state(null)

  // ⌘K / Ctrl+K opens command palette globally; ⌘, opens settings; ⌘\ toggles compare
  function onGlobalKey(e) {
    const meta = e.metaKey || e.ctrlKey
    if ((e.key === 'k' || e.key === 'K') && meta) {
      e.preventDefault(); paletteOpen = true; return
    }
    if (e.key === '/' && meta) {
      e.preventDefault(); paletteOpen = true; return
    }
    if (e.key === ',' && meta) {
      e.preventDefault(); settingsOpen = true; return
    }
    if (e.key === '\\' && meta) {
      e.preventDefault()
      if (compareProject) { compareProject = null; compareSessionId = null }
      else if (selectedProject) {
        // Default 2nd pane = next project after selected, or self
        const idx = projects.findIndex((x) => x.id === selectedProject.id)
        const next = projects[(idx + 1) % Math.max(projects.length, 1)] || selectedProject
        compareProject = next
        compareSessionId = next.last_session_id || null
      }
    }
  }

  async function checkAuth() {
    const r = await authMe()
    authed = !!r.authenticated
    if (authed) {
      await refreshProjects()
      resumeActiveStreams()
    }
  }

  async function refreshProjects() {
    try { projects = await listProjects() }
    catch (e) { console.error('list projects', e) }
  }

  onMount(() => {
    checkAuth()
    window.addEventListener('keydown', onGlobalKey)
    return () => window.removeEventListener('keydown', onGlobalKey)
  })

  function onPickProject(p, latestSession) {
    selectedProject = p
    selectedSessionId = latestSession?.session_id || null
    mobileChatOpen = true
    view = 'projects'
  }

  function onPickSession(p, s) {
    selectedProject = p
    selectedSessionId = s.session_id
    mobileChatOpen = true
    view = 'projects'
  }

  function onProjectRenamed(pid, newName) {
    projects = projects.map((x) => x.id === pid ? { ...x, display_name: newName } : x)
    if (selectedProject?.id === pid) selectedProject = { ...selectedProject, display_name: newName }
  }
  function onSessionRenamed() {}

  async function onProjectCreated(res) {
    await refreshProjects()
    const fresh = projects.find((x) => x.id === res.id)
    if (fresh) {
      selectedProject = fresh
      selectedSessionId = null
      mobileChatOpen = true
      view = 'projects'
    }
    pushToast({ kind: 'success', title: 'Project dibuat', body: res.name || 'unnamed' })
  }

  async function logout() {
    await authLogout()
    selectedProject = null; selectedSessionId = null; projects = []; authed = false
    view = 'projects'; activeMissionId = null
  }
  function backToList() { mobileChatOpen = false }

  function openMissionLauncher() { launcherOpen = true }
  function onMissionLaunched(data) {
    activeMissionId = data.mission_id
    view = 'mission'
    mobileChatOpen = true
  }
  function openMission(mid) {
    activeMissionId = mid
    view = 'mission'
    mobileChatOpen = true
  }
  function closeMission() {
    view = 'projects'
    activeMissionId = null
    mobileChatOpen = false
  }
  function focusMissionAgent(agent) {
    const p = projects.find((x) => x.id === agent.project_id)
    if (!p) return
    selectedProject = p
    selectedSessionId = null // session_id will sync via stream events
    view = 'projects'
  }

  let chatProject = $derived(
    selectedProject ? { ...selectedProject, last_session_id: selectedSessionId } : null
  )
  let chatKey = $derived(
    selectedProject ? `${selectedProject.id}:${selectedSessionId || 'new'}` : 'none'
  )
</script>

{#if authed === null}
  <div class="flex min-h-dvh items-center justify-center text-neutral-500">Loading…</div>
{:else if !authed}
  <Login onSuccess={() => { authed = true; refreshProjects() }} />
{:else}
  <div class="grid h-dvh md:grid-cols-[clamp(260px,22vw,380px)_1fr]">
    <div class="{mobileChatOpen ? 'hidden md:block' : 'block'}">
      <Sidebar
        {projects}
        selectedProjectId={selectedProject?.id || null}
        {selectedSessionId}
        {onPickProject}
        {onPickSession}
        {onProjectRenamed}
        {onSessionRenamed}
        {onProjectCreated}
        onLogout={logout}
        onOpenMissionLauncher={openMissionLauncher}
        onOpenMission={openMission}
        onOpenWatchers={() => (watchersOpen = true)}
        onOpenNotify={() => (notifyOpen = true)}
        onOpenCost={() => (costOpen = true)}
        onOpenSettings={() => (settingsOpen = true)}
        activeView={view}
        activeMissionId={activeMissionId}
      />
    </div>

    <div class="{mobileChatOpen ? 'block' : 'hidden md:block'} min-w-0">
      {#if view === 'mission' && activeMissionId}
        {#key activeMissionId}
          <MissionGrid
            missionId={activeMissionId}
            onClose={closeMission}
            onFocusAgent={focusMissionAgent}
          />
        {/key}
      {:else if chatProject}
        {#if compareProject}
          <div class="grid h-dvh grid-cols-2 divide-x divide-neutral-800" data-testid="compare-mode">
            {#key chatKey}
              <Chat
                project={chatProject}
                onBack={backToList}
                onChanged={refreshProjects}
              />
            {/key}
            {#key `cmp:${compareProject.id}:${compareSessionId || 'new'}`}
              <Chat
                project={{ ...compareProject, last_session_id: compareSessionId }}
                onBack={() => { compareProject = null; compareSessionId = null }}
                onChanged={refreshProjects}
              />
            {/key}
          </div>
        {:else}
          {#key chatKey}
            <Chat
              project={chatProject}
              onBack={backToList}
              onChanged={refreshProjects}
            />
          {/key}
        {/if}
      {:else}
        <div class="grid h-dvh place-items-center px-6 text-neutral-400">
          <div class="w-full max-w-2xl">
            <div class="mb-8 text-center">
              <div class="mb-3 text-5xl">🛰️</div>
              <div class="text-lg font-semibold text-neutral-100">Welcome to MACS</div>
              <div class="mt-1 text-sm text-neutral-500">
                Multi-Agent Orchestration System · {projects.length} project{projects.length === 1 ? '' : 's'} on disk
              </div>
            </div>
            <div class="grid gap-3 sm:grid-cols-3">
              <button
                class="group rounded-2xl border border-neutral-800 bg-neutral-950 p-5 text-left transition hover:border-emerald-500/40 hover:bg-neutral-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500"
                onclick={() => {
                  // surface sidebar event to open NewProjectModal
                  document.querySelector('[data-testid=newproj-open]')?.click()
                }}
                data-testid="home-card-newproj"
              >
                <div class="mb-2 text-2xl">📦</div>
                <div class="font-medium text-neutral-100">Mulai project baru</div>
                <div class="mt-1 text-xs text-neutral-500">Scaffold folder + chat khusus dgn welcome message.</div>
              </button>
              <button
                class="group rounded-2xl border border-neutral-800 bg-neutral-950 p-5 text-left transition hover:border-emerald-500/40 hover:bg-neutral-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 disabled:opacity-40"
                disabled={projects.length === 0}
                onclick={() => {
                  const sorted = [...projects].filter(p => p.last_modified).sort((a,b) => (b.last_modified||0) - (a.last_modified||0))
                  const top = sorted[0]
                  if (top) onPickProject(top, top.last_session_id ? { session_id: top.last_session_id } : null)
                }}
                data-testid="home-card-resume"
              >
                <div class="mb-2 text-2xl">↩️</div>
                <div class="font-medium text-neutral-100">Lanjut chat terakhir</div>
                <div class="mt-1 text-xs text-neutral-500">
                  {#if projects.length > 0}
                    Jump ke project paling baru disentuh.
                  {:else}
                    Belum ada session.
                  {/if}
                </div>
              </button>
              <button
                class="group rounded-2xl border border-neutral-800 bg-neutral-950 p-5 text-left transition hover:border-emerald-500/40 hover:bg-neutral-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500"
                onclick={openMissionLauncher}
                data-testid="home-card-mission"
              >
                <div class="mb-2 text-2xl">🚀</div>
                <div class="font-medium text-neutral-100">Jalankan mission</div>
                <div class="mt-1 text-xs text-neutral-500">Satu prompt → spawn ke beberapa project paralel.</div>
              </button>
            </div>
            <div class="mt-6 text-center text-[11px] text-neutral-600">
              Atau pilih project dari sidebar kiri.
            </div>
          </div>
        </div>
      {/if}
    </div>
  </div>

  {#if launcherOpen}
    <MissionLauncher
      {projects}
      onClose={() => (launcherOpen = false)}
      onLaunched={onMissionLaunched}
    />
  {/if}

  {#if watchersOpen}
    <WatchersPanel
      {projects}
      onClose={() => (watchersOpen = false)}
    />
  {/if}

  {#if notifyOpen}
    <NotifyPanel onClose={() => (notifyOpen = false)} />
  {/if}

  {#if costOpen}
    <CostDashboard onClose={() => (costOpen = false)} />
  {/if}

  <CommandPalette
    open={paletteOpen}
    {projects}
    onClose={() => (paletteOpen = false)}
    onPickProject={(p) => { onPickProject(p, null); paletteOpen = false }}
    onPickSession={(p, s) => { onPickSession(p, s); paletteOpen = false }}
    onOpenMissionLauncher={() => { launcherOpen = true }}
    onOpenWatchers={() => { watchersOpen = true }}
    onOpenCost={() => { costOpen = true }}
    onOpenNotify={() => { notifyOpen = true }}
    onNewProject={() => { document.querySelector('[data-testid=newproj-open]')?.click() }}
    onOpenSettings={() => { settingsOpen = true }}
    onLogout={logout}
  />

  <SettingsPanel
    open={settingsOpen}
    onClose={() => (settingsOpen = false)}
  />

  <ToastHost />
{/if}
