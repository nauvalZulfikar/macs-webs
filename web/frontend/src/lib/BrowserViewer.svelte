<script>
  /** Embed inside Chat.svelte's tool_use card when the tool is browser-agent
   *  browse_autonomous. Polls the run manifest live and shows what the agent
   *  is doing. Correlates the matching run by mtime within stream lifetime. */
  import { onMount, onDestroy } from 'svelte'

  let { input = {}, streamStartedAtMs = 0, streaming = false } = $props()

  let runId = $state(null)
  let manifest = $state(null)
  let error = $state(null)
  let interval = null
  let aborted = false

  async function findMatchingRun() {
    // List runs with mtime ≥ stream start − 60s, pick newest still-running or
    // most recent if all done.
    const since = Math.max(0, Math.floor((streamStartedAtMs || Date.now()) / 1000) - 60)
    try {
      const r = await fetch(`/api/browser-runs?since=${since}`)
      if (!r.ok) return null
      const runs = await r.json()
      if (!runs?.length) return null
      // Prefer the one without a result.json (still running)
      const live = runs.find((x) => !x.has_result)
      return (live || runs[0])?.run_id || null
    } catch { return null }
  }

  async function refreshManifest() {
    if (!runId) {
      const found = await findMatchingRun()
      if (found) runId = found
      else return
    }
    try {
      const r = await fetch(`/api/browser-runs/${runId}/manifest`)
      if (!r.ok) {
        if (r.status === 404) runId = null
        return
      }
      manifest = await r.json()
    } catch (e) { error = e?.message || String(e) }
  }

  onMount(() => {
    refreshManifest()
    interval = setInterval(refreshManifest, streaming ? 2000 : 6000)
  })

  onDestroy(() => {
    aborted = true
    if (interval) clearInterval(interval)
  })

  let goal = $derived(input?.goal || input?.task || input?.instruction || '')
</script>

<div class="mt-2 rounded-lg border border-cyan-500/30 bg-neutral-950/80 text-xs" data-testid="browser-viewer">
  <div class="flex items-center gap-2 border-b border-cyan-500/20 px-2 py-1.5">
    <span class="text-base">🌐</span>
    <div class="min-w-0 flex-1">
      <div class="truncate text-cyan-300">browser-agent · {manifest?.status || 'starting'}</div>
      {#if manifest?.current_url}
        <div class="truncate text-[10px] text-neutral-500" data-testid="browser-url">{manifest.current_url}</div>
      {/if}
    </div>
    {#if runId}
      <span class="text-[10px] text-neutral-600">{runId.slice(0, 13)}</span>
    {/if}
  </div>
  {#if goal}
    <div class="px-2 py-1 text-[10px] text-neutral-400">
      <span class="text-neutral-500">goal:</span> {goal.slice(0, 200)}
    </div>
  {/if}
  {#if manifest?.latest_screenshot}
    <div class="border-b border-cyan-500/20 bg-neutral-950" data-testid="browser-screenshot">
      <a href={manifest.latest_screenshot} target="_blank" rel="noreferrer">
        <img
          src={`${manifest.latest_screenshot}?t=${Math.floor(Date.now() / 2000)}`}
          alt="browser viewport"
          class="block w-full"
          loading="lazy"
        />
      </a>
    </div>
  {/if}
  {#if !manifest}
    <div class="px-2 py-1.5 text-neutral-500">Finding run…</div>
  {:else if !manifest.steps?.length}
    <div class="px-2 py-1.5 text-neutral-500">Initializing browser…</div>
  {:else}
    <div class="max-h-48 overflow-y-auto px-2 py-1.5">
      {#each manifest.steps.slice(-8) as s (s.index)}
        <div class="flex gap-2 border-b border-neutral-900 py-1 last:border-b-0">
          <span class="shrink-0 text-[10px] text-neutral-600">#{s.index}</span>
          <div class="min-w-0 flex-1">
            {#if s.action}
              <div class="truncate text-[11px] text-cyan-300">{s.action}</div>
            {/if}
            {#if s.extracted}
              <div class="truncate text-[10px] text-neutral-400">{s.extracted}</div>
            {/if}
            {#if s.next_goal}
              <div class="truncate text-[10px] text-neutral-500">→ {s.next_goal}</div>
            {/if}
          </div>
        </div>
      {/each}
    </div>
    <div class="border-t border-neutral-900 px-2 py-1 text-[10px] text-neutral-500" data-testid="browser-step-count">
      {manifest.steps_taken} steps
      {#if manifest.status === 'done' && manifest.answer}
        · answer: <span class="text-emerald-300">{manifest.answer.slice(0, 200)}</span>
      {/if}
    </div>
  {/if}
</div>
