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

  onMount(checkAuth)

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
  <div class="grid h-dvh md:grid-cols-[340px_1fr]">
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
        {#key chatKey}
          <Chat
            project={chatProject}
            onBack={backToList}
            onChanged={refreshProjects}
          />
        {/key}
      {:else}
        <div class="grid h-dvh place-items-center text-neutral-500">
          <div class="text-center">
            <div class="mb-2 text-2xl">💬</div>
            <div class="text-sm">Pick a project from the left to start chatting</div>
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
{/if}
