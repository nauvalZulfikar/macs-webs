<script>
  import { createMission, planMission } from './missionsStore.svelte.js'

  let { projects = [], onClose, onLaunched } = $props()

  const MAX_AGENTS = 5

  let mode = $state('manual') // 'manual' | 'ai'

  // AI planner state
  let aiGoal = $state('')
  let aiMaxAgents = $state(3)
  let aiPlanning = $state(false)
  let aiPlan = $state(null) // {mission_name, rationale, agents}

  let name = $state('')
  let sharedPrompt = $state('')
  let selectedPids = $state(new Set())
  let perAgentPrompt = $state({}) // pid -> override prompt
  let elevated = $state(false)
  let useSharedPrompt = $state(true)
  let runMode = $state('parallel') // 'parallel' | 'sequential'
  let launching = $state(false)
  let error = $state(null)

  async function runPlanner() {
    if (!aiGoal.trim()) return
    aiPlanning = true
    error = null
    aiPlan = null
    try {
      aiPlan = await planMission({ goal: aiGoal.trim(), maxAgents: aiMaxAgents })
      // Pre-fill manual form so user can review/edit then click Launch
      name = aiPlan.mission_name || 'AI mission'
      const newPids = new Set()
      const overrides = {}
      for (const a of aiPlan.agents) {
        newPids.add(a.project_id)
        overrides[a.project_id] = a.message
      }
      selectedPids = newPids
      perAgentPrompt = overrides
      useSharedPrompt = false
      sharedPrompt = aiGoal.trim()
      // Auto-switch to manual review pane
      mode = 'manual'
    } catch (e) {
      error = e?.message || String(e)
    } finally {
      aiPlanning = false
    }
  }

  function toggle(pid) {
    const n = new Set(selectedPids)
    if (n.has(pid)) n.delete(pid)
    else if (n.size < MAX_AGENTS) n.add(pid)
    selectedPids = n
  }

  let selectedList = $derived(
    projects.filter((p) => selectedPids.has(p.id))
  )

  let canLaunch = $derived(
    !launching &&
    name.trim().length > 0 &&
    selectedList.length >= 1 &&
    (useSharedPrompt ? sharedPrompt.trim().length > 0 : selectedList.every(p => (perAgentPrompt[p.id] || '').trim().length > 0))
  )

  async function launch() {
    if (!canLaunch) return
    launching = true
    error = null
    try {
      const agents = selectedList.map((p) => ({
        project_id: p.id,
        message: useSharedPrompt ? null : (perAgentPrompt[p.id] || '').trim(),
        label: p.display_name || p.name,
        elevated,
        new_conversation: true,
      }))
      const data = await createMission({
        name: name.trim(),
        sharedPrompt: useSharedPrompt ? sharedPrompt.trim() : null,
        agents,
        mode: runMode,
      })
      onLaunched?.(data)
      onClose?.()
    } catch (e) {
      error = e?.message || String(e)
    } finally {
      launching = false
    }
  }
</script>

<div class="fixed inset-0 z-[70] flex items-center justify-center bg-black/70 p-4" data-testid="mission-launcher">
  <div class="w-full max-w-lg rounded-2xl border border-emerald-500/40 bg-neutral-950 p-4 shadow-xl max-h-[90vh] flex flex-col">
    <div class="mb-3 flex items-center justify-between">
      <div class="flex items-center gap-2">
        <span class="text-lg">🚀</span>
        <span class="font-medium">New Mission</span>
      </div>
      <button class="text-neutral-400 hover:text-neutral-100" onclick={onClose} data-testid="mission-close">✕</button>
    </div>

    <!-- Mode toggle -->
    <div class="mb-3 flex gap-1 rounded-lg border border-neutral-800 bg-neutral-900 p-1">
      <button
        class="flex-1 rounded-md px-2 py-1.5 text-xs transition {mode === 'ai' ? 'bg-emerald-600/30 text-emerald-200' : 'text-neutral-400 hover:text-neutral-200'}"
        onclick={() => mode = 'ai'}
        data-testid="mission-mode-ai"
      >✨ AI Plan</button>
      <button
        class="flex-1 rounded-md px-2 py-1.5 text-xs transition {mode === 'manual' ? 'bg-emerald-600/30 text-emerald-200' : 'text-neutral-400 hover:text-neutral-200'}"
        onclick={() => mode = 'manual'}
        data-testid="mission-mode-manual"
      >✋ Manual</button>
    </div>

    {#if mode === 'ai'}
      <!-- AI planner pane -->
      <div class="space-y-3 overflow-y-auto pr-1">
        <div>
          <label class="block text-[10px] uppercase tracking-wide text-neutral-500">Mission goal (1 sentence)</label>
          <textarea
            bind:value={aiGoal}
            rows="4"
            placeholder="e.g. audit all repos for outdated dependencies and propose updates"
            class="mt-1 w-full resize-none rounded-lg border border-emerald-500/30 bg-neutral-900 px-3 py-2 text-sm focus:border-emerald-600/60 focus:outline-none"
            data-testid="mission-ai-goal"
          ></textarea>
        </div>
        <div>
          <label class="block text-[10px] uppercase tracking-wide text-neutral-500">Max agents</label>
          <input type="range" min="1" max="5" bind:value={aiMaxAgents}
            class="mt-1 w-full" data-testid="mission-ai-max" />
          <div class="text-[10px] text-neutral-500">up to {aiMaxAgents}</div>
        </div>
        {#if aiPlan}
          <div class="rounded-lg border border-emerald-500/30 bg-emerald-500/5 p-2">
            <div class="text-xs font-medium text-emerald-300">Proposed plan</div>
            <div class="mt-1 text-[10px] text-neutral-400">{aiPlan.rationale}</div>
            <ul class="mt-1.5 space-y-1">
              {#each aiPlan.agents as a}
                {@const p = projects.find((x) => x.id === a.project_id)}
                <li class="text-[10px]">
                  <span class="rounded bg-neutral-800 px-1.5 py-0.5 text-emerald-300">{a.label || (p?.display_name || p?.name || a.project_id)}</span>
                  <span class="ml-1 text-neutral-400">{a.message.slice(0, 100)}</span>
                </li>
              {/each}
            </ul>
            <div class="mt-2 text-[10px] text-neutral-500">→ form pre-filled in Manual tab. Review &amp; Launch.</div>
          </div>
        {/if}
        {#if error}
          <div class="rounded-md border border-red-500/40 bg-red-500/10 p-2 text-xs text-red-300">{error}</div>
        {/if}
      </div>
      <div class="mt-3 flex gap-2 border-t border-neutral-800 pt-3">
        <button class="flex-1 rounded-lg bg-neutral-800 px-3 py-2 text-sm text-neutral-200 hover:bg-neutral-700" onclick={onClose} disabled={aiPlanning}>Cancel</button>
        <button
          class="flex-1 rounded-lg bg-emerald-600 px-3 py-2 text-sm font-medium text-white hover:bg-emerald-500 disabled:bg-neutral-700"
          onclick={runPlanner}
          disabled={aiPlanning || !aiGoal.trim()}
          data-testid="mission-ai-plan"
        >{aiPlanning ? 'Planning… (≤90s)' : '✨ Plan'}</button>
      </div>
    {:else}
    <!-- Manual pane -->
    <div class="space-y-3 overflow-y-auto pr-1">
      <div>
        <label class="block text-[10px] uppercase tracking-wide text-neutral-500">Mission name</label>
        <input
          bind:value={name}
          placeholder="audit deps across services"
          class="mt-1 w-full rounded-lg border border-neutral-800 bg-neutral-900 px-3 py-2 text-sm focus:border-emerald-600/60 focus:outline-none"
          data-testid="mission-name"
        />
      </div>

      <div>
        <label class="block text-[10px] uppercase tracking-wide text-neutral-500">Projects ({selectedList.length}/{MAX_AGENTS})</label>
        <div class="mt-1 grid grid-cols-2 gap-1.5">
          {#each projects as p (p.id)}
            {@const checked = selectedPids.has(p.id)}
            <button
              type="button"
              class="flex items-center gap-2 rounded-lg border px-2 py-1.5 text-left text-xs transition {checked ? 'border-emerald-500/60 bg-emerald-500/10' : 'border-neutral-800 bg-neutral-900 hover:border-neutral-700'}"
              onclick={() => toggle(p.id)}
              data-testid="mission-project-{p.id}"
              disabled={!checked && selectedList.length >= MAX_AGENTS}
            >
              <span class="h-4 w-4 shrink-0 rounded-sm border {checked ? 'border-emerald-500 bg-emerald-500/30' : 'border-neutral-700'}"></span>
              <span class="truncate">{p.display_name || p.name}</span>
            </button>
          {/each}
        </div>
      </div>

      <div>
        <div class="flex items-center justify-between">
          <label class="block text-[10px] uppercase tracking-wide text-neutral-500">Prompt</label>
          <label class="flex items-center gap-1.5 text-[10px] text-neutral-400">
            <input type="checkbox" bind:checked={useSharedPrompt} />
            shared
          </label>
        </div>
        {#if useSharedPrompt}
          <textarea
            bind:value={sharedPrompt}
            rows="3"
            placeholder="Same prompt sent to each agent…"
            class="mt-1 w-full resize-none rounded-lg border border-neutral-800 bg-neutral-900 px-3 py-2 text-sm focus:border-emerald-600/60 focus:outline-none"
            data-testid="mission-shared-prompt"
          ></textarea>
        {:else}
          <div class="mt-1 space-y-1.5">
            {#each selectedList as p (p.id)}
              <div>
                <div class="text-[10px] text-neutral-500">{p.display_name || p.name}</div>
                <textarea
                  rows="2"
                  bind:value={perAgentPrompt[p.id]}
                  placeholder="prompt for {p.name}"
                  class="mt-0.5 w-full resize-none rounded-lg border border-neutral-800 bg-neutral-900 px-2 py-1.5 text-xs focus:border-emerald-600/60 focus:outline-none"
                ></textarea>
              </div>
            {/each}
          </div>
        {/if}
      </div>

      <div>
        <label class="block text-[10px] uppercase tracking-wide text-neutral-500">Run mode</label>
        <div class="mt-1 grid grid-cols-2 gap-1.5">
          <button type="button"
            class="rounded-lg border px-2 py-1.5 text-xs {runMode === 'parallel' ? 'border-emerald-500/60 bg-emerald-500/10 text-emerald-300' : 'border-neutral-800 bg-neutral-900 text-neutral-400'}"
            onclick={() => runMode = 'parallel'}
            data-testid="mode-parallel">⚡ Parallel</button>
          <button type="button"
            class="rounded-lg border px-2 py-1.5 text-xs {runMode === 'sequential' ? 'border-emerald-500/60 bg-emerald-500/10 text-emerald-300' : 'border-neutral-800 bg-neutral-900 text-neutral-400'}"
            onclick={() => runMode = 'sequential'}
            data-testid="mode-sequential">🔗 Sequential (handoff)</button>
        </div>
        {#if runMode === 'sequential'}
          <div class="mt-1 text-[10px] text-neutral-500">Agents run in order. Each sees previous agents' findings via shared scratchpad.</div>
        {/if}
      </div>

      <label class="flex items-center gap-2 text-xs text-neutral-400">
        <input type="checkbox" bind:checked={elevated} />
        Elevated permissions (bypass auto-mode classifier)
      </label>

      {#if error}
        <div class="rounded-md border border-red-500/40 bg-red-500/10 p-2 text-xs text-red-300">{error}</div>
      {/if}
    </div>

    <div class="mt-3 flex gap-2 border-t border-neutral-800 pt-3">
      <button
        class="flex-1 rounded-lg bg-neutral-800 px-3 py-2 text-sm text-neutral-200 hover:bg-neutral-700"
        onclick={onClose}
        disabled={launching}
      >Cancel</button>
      <button
        class="flex-1 rounded-lg bg-emerald-600 px-3 py-2 text-sm font-medium text-white hover:bg-emerald-500 disabled:bg-neutral-700"
        onclick={launch}
        disabled={!canLaunch}
        data-testid="mission-launch"
      >{launching ? 'Launching…' : `Launch (${selectedList.length})`}</button>
    </div>
    {/if}
  </div>
</div>
